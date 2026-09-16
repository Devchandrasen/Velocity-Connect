#!/usr/bin/env python3
"""Predeclare and execute pinned VehCom validation; never build the simulator.

Run this driver in the binary's environment (WSL for the repository Linux pin).
The JSONL ledger is append-only; a failed or interrupted row is never retried.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1
TERMINAL = {"succeeded", "failed", "timeout", "interrupted"}
RAW_FILES = ("single_run.csv", "ue_metrics.csv", "packet_receptions.csv",
             "handover_events.csv", "ue_serving_cells.csv", "rsrp_measurements.csv")
BOUNDARY = ("Simulation sensitivity only; UMi and RMa LOS are not railway-calibrated. "
            "RMa alone is not railway validation. Matched seed/run identifiers do not "
            "prove common-random-number matched channels; stream-state evidence is absent. "
            "Scalar passive is a legacy reference, not a calibrated physical candidate.")
CSV_CONTROL = {
    "scenario": "scenario", "passiveModel": "passive_model",
    "trafficDirection": "traffic_direction", "nrScenario": "nr_scenario",
    "nrCondition": "nr_condition", "shadowing": "shadowing", "speed": "speed_kmph",
    "distance": "distance_m", "numUes": "num_ues", "numGnbs": "num_gnbs",
    "gnbSpacingM": "gnb_spacing_m", "gnbHeightM": "gnb_height_m",
    "gnbLateralOffsetM": "gnb_lateral_offset_m", "ueHeightM": "ue_height_m",
    "guardedCorridor": "guarded_corridor", "simTime": "sim_time_s",
    "appStart": "app_start_s", "appStop": "app_stop_s", "enableSrs": "enable_srs",
    "channelUpdatePeriodMs": "channel_update_period_ms", "enableHandover": "enable_handover",
    "useIdealRrc": "use_ideal_rrc", "handoverHysteresisDb": "handover_hysteresis_db",
    "handoverTimeToTriggerMs": "handover_ttt_ms", "seed": "seed", "run": "run",
    "declaredPassiveLossDb": "declared_passive_loss_db", "numerology": "numerology",
    "gnbTxPowerDbm": "gnb_tx_power_dbm", "ueTxPowerDbm": "ue_tx_power_dbm",
}
METRICS = ("throughput_mbps", "p05_ue_throughput_mbps", "median_ue_throughput_mbps",
           "pdr", "tx_pkts", "rx_pkts", "mean_lat_ms", "p50_lat_ms", "p95_lat_ms",
           "jain_fairness", "handover_attempts", "handover_successes", "handover_failures",
           "mean_handover_duration_ms", "max_handover_duration_ms",
           "mean_application_gap_ms", "max_application_gap_ms",
           "bad_ipv4_length_drops", "short_transport_header_hash_events")
LATENCY = {"mean_lat_ms", "p50_lat_ms", "p95_lat_ms"}
REFERENCE_SCALES = {"packet_loss": 0.05, "tail_latency_ms": 20.0,
                    "receive_gap_ms": 200.0, "ping_pongs_per_ue_km": 0.5,
                    "handover_failures_per_ue_km": 0.1}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json_new(path, value):
    with Path(path).open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def contained(root, relative):
    path = (Path(root) / relative).resolve()
    if path == Path(root).resolve() or not path.is_relative_to(Path(root).resolve()):
        raise ValueError(f"Unsafe relative path: {relative}")
    return path


def inspect_binary(binary, pin_file, source_root):
    """Verify the supplied build provenance, then inspect help without simulation."""
    binary, source_root = Path(binary).resolve(), Path(source_root).resolve()
    pin = json.loads(Path(pin_file).read_text(encoding="utf-8"))
    binary_hash = sha256(binary)
    if binary_hash != pin["binary"]["sha256"]:
        raise ValueError("Binary differs from supplied provenance pin; no execution allowed")
    sources = pin.get("synced_source_sha256", {})
    if not sources or not any(p.endswith("hsr_velocity_connect.cc") for p in sources):
        raise ValueError("Pin requires synced_source_sha256 including hsr_velocity_connect.cc")
    for relative, expected in sources.items():
        if sha256(contained(source_root, relative)) != expected:
            raise ValueError(f"Source differs from build provenance: {relative}")
    proc = subprocess.run([str(binary), "--PrintHelp"], capture_output=True, text=True,
                          timeout=30, check=True)
    help_text = proc.stdout + proc.stderr
    return {"binary": str(binary), "binary_sha256": binary_hash,
            "source_root": str(source_root), "source_sha256": dict(sources),
            "source_bundle_sha256": digest(sources), "pin_sha256": sha256(pin_file),
            "pin": pin, "help": help_text,
            "supported_options": sorted(set(re.findall(r"--([A-Za-z][A-Za-z0-9]*):", help_text)))}


def parse_extra(items, protected, supported):
    parsed = {}
    for arg in items:
        match = re.fullmatch(r"--([A-Za-z][A-Za-z0-9]*)=(.+)", arg)
        if not match:
            raise ValueError(f"Extra arguments must each be one --key=value token: {arg!r}")
        key, value = match.groups()
        if key in protected or key in parsed or key.startswith("Print"):
            raise ValueError(f"Extra argument overrides a protected/duplicate control: {key}")
        if key not in supported:
            raise ValueError(f"Pinned binary does not advertise candidate option: {key}")
        parsed[key] = value
    return parsed


PROFILES = ("expanded", "principal", "load", "channel-sensitivity", "smoke", "bridge-smoke")


def build_rows(profile="expanded", seed_base=None, run_base=None, extra_args=(),
               candidate_args=(), supported=(), candidate_artifacts=()):
    """Deterministic fixed design; treatments share identifiers within each cell only."""
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
    default_seed = 790001 if profile == "bridge-smoke" else 780001 if profile == "smoke" else 760001
    default_run = 79000001 if profile == "bridge-smoke" else 78000001 if profile == "smoke" else 76000001
    seed_base = seed_base if seed_base is not None else default_seed
    run_base = run_base if run_base is not None else default_run
    if seed_base <= 0 or run_base <= 0:
        raise ValueError("Seed and run bases must be positive")
    fixed = {"singleRun": 1, "doSpeed": 0, "doDistance": 0, "doScalability": 0,
             "paperProfile": 0, "speed": 500, "distance": 0, "numGnbs": 6,
             "gnbSpacingM": 500, "gnbHeightM": 10, "gnbLateralOffsetM": 10,
             "ueHeightM": 1.5, "guardedCorridor": 1, "channelUpdatePeriodMs": 5,
             "simTime": 14.4, "appStart": 6.3, "appStop": 13.5,
             "enableHandover": 1, "useIdealRrc": 0, "handoverHysteresisDb": 1.5,
             "handoverTimeToTriggerMs": 128, "nrCondition": "LOS", "nrChannelModel": "ThreeGpp",
             "shadowing": 1, "numerology": 1, "enableSrs": 0, "appPktSize": 1024,
             "saturatingLoad": 0, "gnbTxPowerDbm": 40, "ueTxPowerDbm": 23,
             "ueNoiseFigureDb": 7, "scheduler": "ns3::NrMacSchedulerOfdmaPF",
             "compositeVplDb": 20, "declaredPassiveLossDb": 6.5,
             "passiveModel": "declared_scalar"}
    if profile in {"smoke", "bridge-smoke"}:
        fixed.update(numGnbs=1, guardedCorridor=0, enableHandover=0, distance=100,
                     simTime=0.4, appStart=0.2, appStop=0.4)
    if profile == "bridge-smoke":
        fixed.update(speed=0, distance=500, gnbLateralOffsetM=0, channelUpdatePeriodMs=0)
    protected = set(fixed) | {"outDir", "seed", "run", "scenario", "nrScenario",
                              "trafficDirection", "numUes", "perUeOfferedMbps"}
    common = parse_extra(extra_args, protected, set(supported))
    # A candidate must explicitly select its own passive model (e.g. the new matrix bridge).
    candidate = parse_extra(candidate_args, protected - {"passiveModel"}, set(supported))
    if candidate_args and (not candidate_artifacts or "passiveModel" not in candidate):
        raise ValueError("Candidate requires explicit passiveModel and hashed --candidate-artifact")
    if candidate_artifacts and not candidate_args:
        raise ValueError("Candidate artifacts supplied without candidate arguments")
    if profile == "bridge-smoke" and not candidate:
        raise ValueError("bridge-smoke requires a candidate treatment")
    if candidate.get("passiveModel") == "em_complex" and profile != "bridge-smoke":
        raise ValueError("Current em_complex contract is static single-link only; use bridge-smoke, not a moving validation campaign")
    if candidate.get("passiveModel") == "em_complex":
        artifact_paths = {str(Path(p).resolve()) for p in candidate_artifacts}
        for key in ("emTouchstone", "emOperators"):
            if key not in candidate or str(Path(candidate[key]).resolve()) not in artifact_paths:
                raise ValueError(f"em_complex requires {key} explicitly bound by --candidate-artifact")
    if set(common) & set(candidate):
        raise ValueError("Common/candidate extra controls overlap")
    cells = []
    if profile == "bridge-smoke":
        cells.append(("bridge-smoke", "UMi", "downlink", 1, 4, 2))
    if profile in {"expanded", "principal"}:
        for direction in ("downlink", "uplink"):
            cells.append(("principal", "UMi", direction, 1, 4, 40))
    if profile in {"expanded", "load"}:
        for ues in (1, 4, 16):
            for offered in (4, 20, 50):
                cells.append(("load", "UMi", "downlink", ues, offered, 20))
    if profile in {"expanded", "channel-sensitivity", "smoke"}:
        for channel in ("UMi", "RMa"):
            for direction in ("downlink", "uplink"):
                cells.append(("smoke" if profile == "smoke" else "channel-sensitivity",
                              channel, direction, 1, 4, 2 if profile == "smoke" else 20))
    treatments = [("direct_composite", "composite", {}),
                  ("scalar_passive_legacy_reference", "repeater", {})]
    if candidate:
        treatments.append(("candidate_bridge", "repeater", candidate))
    rows = []
    # Family offsets make focused plans identical to their expanded-plan subset.
    # Focused and expanded plans overlap intentionally; never execute both.
    offsets = {"principal": 0, "load": 1000, "channel-sensitivity": 2000, "smoke": 0, "bridge-smoke": 0}
    indices = Counter()
    for family, channel, direction, ues, offered, reps in cells:
        cell = f"{family}-{channel}-LOS-{direction}-u{ues}-mbps{offered}"
        for rep in range(reps):
            pair_index = offsets[family] + indices[family]
            seed, run = seed_base + pair_index, run_base + pair_index
            if seed >= 2**31 or run >= 2**63:
                raise ValueError("Seed/run range exceeds conservative ns-3 RNG limits")
            for treatment, scenario, changes in treatments:
                options = {**fixed, **common, "nrScenario": channel,
                           "trafficDirection": direction, "numUes": ues,
                           "perUeOfferedMbps": offered, "seed": seed, "run": run,
                           "scenario": scenario, **changes}
                pair_id = f"{cell}-p{rep + 1:03d}"
                rows.append({"row_id": f"{pair_id}-{treatment}", "pair_id": pair_id,
                             "cell_id": cell, "family": family, "replicate": rep + 1,
                             "treatment": treatment, "seed": seed, "run": run,
                             "planned_active_km": (options["appStop"] - options["appStart"])
                             * options["speed"] / 3600, "options": options})
            indices[family] += 1
    return rows


def validate_rows(rows):
    seen, groups, random_ids = set(), {}, {}
    for row in rows:
        if row["row_id"] in seen or not re.fullmatch(r"[A-Za-z0-9_.-]+", row["row_id"]):
            raise ValueError("Duplicate or unsafe row identity")
        seen.add(row["row_id"])
        key = (row["cell_id"], row["pair_id"])
        identity = (row["seed"], row["run"])
        if identity in random_ids and random_ids[identity] != key:
            raise ValueError("Seed/run reused across independent cells or replicates")
        random_ids[identity] = key
        if identity != (row["options"]["seed"], row["options"]["run"]):
            raise ValueError("RNG identifier differs from command")
        group = groups.setdefault(key, {})
        if row["treatment"] in group:
            raise ValueError("Duplicate treatment within pair")
        if group and identity != next(iter(group.values())):
            raise ValueError("Unmatched seed/run within pair")
        group[row["treatment"]] = identity
    treatment_sets = {tuple(sorted(g)) for g in groups.values()}
    if len(treatment_sets) != 1 or not {"direct_composite", "scalar_passive_legacy_reference"} <= set(next(iter(treatment_sets), ())):
        raise ValueError("Incomplete treatment pairs")


def plan_campaign(out, provenance, **design):
    out = Path(out).resolve()
    rows = build_rows(supported=provenance["supported_options"], **design)
    validate_rows(rows)
    for row in rows:
        unknown = set(row["options"]) - set(provenance["supported_options"])
        if unknown:
            raise ValueError(f"Pinned CLI missing controls: {sorted(unknown)}")
    artifacts = {str(Path(p).resolve()): sha256(p) for p in design.get("candidate_artifacts", ())}
    plan = {"schema": SCHEMA, "created_utc": utc(), "profile": design.get("profile", "expanded"),
            "evidence_boundary": BOUNDARY, "provenance": provenance, "design": design,
            "candidate_artifact_sha256": artifacts, "rows": rows,
            "driver_sha256": sha256(__file__),
            "analysis": {"bootstrap_resamples": 20000, "bootstrap_seed": 20260907,
                         "threshold_multipliers": [0.5, 1.0, 2.0], "gap_threshold_ms": 20.0,
                         "saturation_fraction": 0.95, "reference_scales": REFERENCE_SCALES,
                         "ping_pong_window_s": 1.0, "no_result_based_stopping": True}}
    plan["plan_sha256"] = digest(plan)
    out.mkdir(parents=True, exist_ok=False)
    write_json_new(out / "plan.json", plan)
    # Full predetermined row identities are present before the first execution.
    for row in rows:
        append_event(out, plan, row, "planned")
    return plan


def load_plan(out):
    plan = json.loads((Path(out) / "plan.json").read_text(encoding="utf-8"))
    expected = plan.pop("plan_sha256")
    if digest(plan) != expected or plan["schema"] != SCHEMA:
        raise ValueError("Plan digest/schema mismatch")
    plan["plan_sha256"] = expected
    validate_rows(plan["rows"])
    return plan


def append_event(out, plan, row, status, **details):
    event = {"utc": utc(), "plan_sha256": plan["plan_sha256"],
             "binary_sha256": plan["provenance"]["binary_sha256"],
             "source_bundle_sha256": plan["provenance"]["source_bundle_sha256"],
             **{k: row[k] for k in ("row_id", "cell_id", "pair_id", "treatment", "seed", "run")},
             "status": status, **details}
    with (Path(out) / "ledger.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_ledger(out, plan):
    expected = {r["row_id"]: r for r in plan["rows"]}
    states = {}
    with (Path(out) / "ledger.jsonl").open(encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            try:
                event = json.loads(line)
                row = expected[event["row_id"]]
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Invalid ledger line {number}; never truncate or repair silently") from exc
            for key in ("cell_id", "pair_id", "treatment", "seed", "run"):
                if event[key] != row[key]:
                    raise ValueError(f"Ledger identity mismatch at line {number}: {key}")
            for key, value in (("plan_sha256", plan["plan_sha256"]),
                               ("binary_sha256", plan["provenance"]["binary_sha256"]),
                               ("source_bundle_sha256", plan["provenance"]["source_bundle_sha256"])):
                if event[key] != value:
                    raise ValueError(f"Ledger provenance mismatch: {key}")
            previous = states.get(row["row_id"], {}).get("status")
            status = event["status"]
            valid = ((previous is None and status == "planned") or
                     (previous == "planned" and status == "running") or
                     (previous == "running" and status in TERMINAL))
            if not valid:
                raise ValueError(f"Illegal ledger transition {previous} -> {status}; no retries")
            states[row["row_id"]] = event
    if set(states) != set(expected):
        raise ValueError("Predetermined ledger incomplete; no partial analysis or execution")
    return states


def status_report(plan, states):
    counts = dict(Counter(e["status"] for e in states.values()))
    terminal = all(e["status"] in TERMINAL for e in states.values())
    return {"plan_sha256": plan["plan_sha256"], "expected_rows": len(plan["rows"]),
            "status_counts": counts, "all_terminal": terminal,
            "campaign_status": ("succeeded" if counts.get("succeeded") == len(plan["rows"])
                                else "failed" if terminal else "incomplete"),
            "evidence_boundary": BOUNDARY}


@contextmanager
def campaign_lock(out):
    """OS-held exclusive lock: released on crash; the file is never deleted."""
    with (Path(out) / ".runner.lock").open("a+b") as f:
        f.seek(0, 2)
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_csv(path, required):
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not set(required) <= set(reader.fieldnames):
            raise ValueError(f"CSV contract mismatch: {path}")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV row: {path}")
            yield row


def number(value, label, *, integer=False):
    x = float(value)
    if not math.isfinite(x) or x < 0 or (integer and not x.is_integer()):
        raise ValueError(f"Invalid nonnegative {'integer' if integer else 'number'}: {label}")
    return int(x) if integer else x


def validate_result(raw_dir, row):
    rows = list(read_csv(Path(raw_dir) / "single_run.csv", set(CSV_CONTROL.values()) | set(METRICS)))
    if len(rows) != 1:
        raise ValueError("single_run.csv must have exactly one result")
    record = rows[0]
    optional_controls = {"emMapping": "em_mapping", "emTouchstone": "em_touchstone",
                         "emOperators": "em_operators", "nrRngStream": "nr_rng_stream",
                         "channelRngStream": "channel_rng_stream"}
    for option, field in optional_controls.items():
        if option in row["options"] and record.get(field) != str(row["options"][option]):
            raise ValueError(f"Candidate/stream result differs from plan: {field}")
    if record.get("common_channel_realizations_verified", "0") != "0":
        raise ValueError("A channel-realization claim requires separately reviewed stream-state evidence")
    for option, field in CSV_CONTROL.items():
        expected = row["options"][option]
        actual = record[field]
        if isinstance(expected, (int, float)):
            if not math.isclose(float(actual), expected, rel_tol=1e-5, abs_tol=1e-7):
                raise ValueError(f"Result control differs from plan: {field}")
        elif actual != expected:
            raise ValueError(f"Result control differs from plan: {field}")
    numeric = {}
    rx = number(record["rx_pkts"], "rx_pkts", integer=True)
    for metric in METRICS:
        value = float(record[metric])
        # All conditional latency fields are undefined with zero receptions, even
        # if an older serializer wrote 0. Undefined HO durations remain null too.
        if (metric in LATENCY and rx == 0) or (math.isnan(value) and metric not in LATENCY and ("duration" in metric or "application_gap" in metric)):
            numeric[metric] = None
        else:
            numeric[metric] = number(value, metric, integer=metric in {
                "tx_pkts", "rx_pkts", "handover_attempts", "handover_successes",
                "handover_failures", "bad_ipv4_length_drops", "short_transport_header_hash_events"})
    tx = numeric["tx_pkts"]
    if tx <= 0 or rx > tx or not math.isclose(numeric["pdr"], rx / tx, abs_tol=2e-9):
        raise ValueError("Packet count/PDR inconsistency or no transmitted load")
    if numeric["jain_fairness"] > 1 + 1e-9:
        raise ValueError("Invalid Jain fairness")
    if numeric["handover_attempts"] != numeric["handover_successes"] + numeric["handover_failures"]:
        raise ValueError("Handover counters do not reconcile")
    active = row["options"]["appStop"] - row["options"]["appStart"]
    payload = row["options"]["appPktSize"] - 12
    if not math.isclose(numeric["throughput_mbps"], rx * payload * 8 / active / 1e6, rel_tol=1e-7, abs_tol=2e-9):
        raise ValueError("Payload throughput/count inconsistency")
    return numeric


def verify_inputs(plan):
    if sha256(__file__) != plan["driver_sha256"]:
        raise ValueError("Campaign driver changed after planning; use the original pinned driver")
    p = plan["provenance"]
    if sha256(p["binary"]) != p["binary_sha256"]:
        raise ValueError("Pinned binary changed after planning")
    for relative, expected in p["source_sha256"].items():
        if sha256(contained(p["source_root"], relative)) != expected:
            raise ValueError(f"Pinned source changed after planning: {relative}")
    for path, expected in plan["candidate_artifact_sha256"].items():
        if sha256(path) != expected:
            raise ValueError(f"Candidate artifact changed: {path}")


def execute(command, cwd, stdout, stderr, timeout):
    with stdout.open("xb") as out, stderr.open("xb") as err:
        proc = subprocess.Popen(command, cwd=cwd, stdout=out, stderr=err,
                                start_new_session=os.name != "nt")
        try:
            return proc.wait(timeout=timeout)
        except BaseException:
            if proc.poll() is None:
                if os.name == "nt":
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise


def run_campaign(out, *, timeout=1800, recover_interrupted=False, executor=execute):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be finite and positive")
    out = Path(out).resolve()
    with campaign_lock(out):
        plan = load_plan(out)
        states = read_ledger(out, plan)
        running = [r for r in plan["rows"] if states[r["row_id"]]["status"] == "running"]
        if running and not recover_interrupted:
            raise ValueError("Interrupted running row exists; use --recover-interrupted after confirming no orphan simulator remains. It will NOT be retried.")
        for row in running:
            append_event(out, plan, row, "interrupted", error="Explicit crash recovery; original evidence retained")
            states[row["row_id"]]["status"] = "interrupted"
        for row in plan["rows"]:
            if states[row["row_id"]]["status"] != "planned":
                continue
            verify_inputs(plan)
            raw = contained(out, "raw/" + row["row_id"])
            logs = contained(out, "logs/" + row["row_id"])
            command = [plan["provenance"]["binary"]] + [f"--{k}={v}" for k, v in row["options"].items()] + [f"--outDir={raw}"]
            append_event(out, plan, row, "running", command=command, timeout_s=timeout)
            started = time.monotonic()
            status, details, interrupted = "failed", {}, False
            try:
                raw.mkdir(parents=True, exist_ok=False)
                # The EM executable requires an empty result directory at entry.
                # Keep runner-owned logs outside that directory for every treatment.
                logs.mkdir(parents=True, exist_ok=False)
                rc = executor(command, plan["provenance"]["source_root"], logs / "stdout.log", logs / "stderr.log", timeout)
                details["returncode"] = rc
                if rc != 0:
                    raise ValueError(f"Binary exited with code {rc}")
                validate_result(raw, row)
                for name in RAW_FILES:
                    if not (raw / name).is_file():
                        raise ValueError(f"Required raw output absent: {name}")
                details["raw_sha256"] = {p.relative_to(raw).as_posix(): sha256(contained(raw, p.relative_to(raw)))
                                         for p in sorted(raw.rglob("*")) if p.is_file()}
                verify_inputs(plan)
                status = "succeeded"
            except subprocess.TimeoutExpired as exc:
                status, details["error"] = "timeout", str(exc)
            except KeyboardInterrupt:
                status, details["error"], interrupted = "interrupted", "Operator interrupt; no retry", True
            except (OSError, ValueError, KeyError) as exc:
                details["error"] = f"{type(exc).__name__}: {exc}"
            details["log_sha256"] = {p.relative_to(out).as_posix(): sha256(p)
                                     for p in sorted(logs.glob("*.log")) if p.is_file()}
            details["elapsed_wall_s"] = time.monotonic() - started
            append_event(out, plan, row, status, **details)
            if interrupted:
                break
        return status_report(plan, read_ledger(out, plan))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("inspect", "plan"):
        p = sub.add_parser(name)
        p.add_argument("--binary", type=Path, required=True)
        p.add_argument("--source-root", type=Path, required=True)
        p.add_argument("--pin-file", type=Path, default=ROOT / "environment/v3_campaign_source_provenance.json")
        if name == "plan":
            p.add_argument("--out", type=Path, required=True)
            p.add_argument("--profile", choices=PROFILES, default="expanded")
            p.add_argument("--seed-base", type=int)
            p.add_argument("--run-base", type=int)
            p.add_argument("--extra-arg", action="append", default=[])
            p.add_argument("--candidate-arg", action="append", default=[])
            p.add_argument("--candidate-artifact", action="append", default=[])
            p.add_argument("--prior-plan", type=Path, action="append", default=[])
    for name in ("run", "status"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, required=True)
        if name == "run":
            p.add_argument("--timeout", type=float, default=1800)
            p.add_argument("--recover-interrupted", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action in {"inspect", "plan"}:
            provenance = inspect_binary(args.binary, args.pin_file, args.source_root)
            if args.action == "inspect":
                print(json.dumps(provenance, indent=2))
                return 0
            design = dict(profile=args.profile, seed_base=args.seed_base, run_base=args.run_base,
                          extra_args=args.extra_arg, candidate_args=args.candidate_arg,
                          candidate_artifacts=args.candidate_artifact)
            preview = build_rows(supported=provenance["supported_options"], **design)
            new_ids = {(r["seed"], r["run"]) for r in preview}
            for previous in args.prior_plan:
                prior = load_plan(previous.parent if previous.is_file() else previous)
                if new_ids & {(r["seed"], r["run"]) for r in prior["rows"]}:
                    raise ValueError("Seed/run overlap with --prior-plan; choose fresh bases before planning")
            provenance["prior_plans_checked"] = [str(p.resolve()) for p in args.prior_plan]
            plan = plan_campaign(args.out, provenance, **design)
            print(json.dumps({"planned_rows": len(plan["rows"]), "plan_sha256": plan["plan_sha256"],
                              "profile": plan["profile"], "execution_started": False}))
        elif args.action == "run":
            report = run_campaign(args.out, timeout=args.timeout, recover_interrupted=args.recover_interrupted)
            print(json.dumps(report, indent=2))
            return 0 if report["campaign_status"] == "succeeded" else 2
        else:
            plan = load_plan(args.out)
            print(json.dumps(status_report(plan, read_ledger(args.out, plan)), indent=2))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"vehcom: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
