"""SYNTHETIC FIXTURES ONLY: mechanics tests, not simulator/railway evidence."""
import copy
import csv
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import pytest
from scipy.stats import poisson

from scripts import analyze_vehcom_validation as analysis
from scripts import run_vehcom_validation as runner


def fixture_csv(path, fields, rows=()):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


def fixture_output(raw, row, rx=3):
    """Write small, explicitly artificial CSVs with the actual simulator headers."""
    o = row["options"]
    active = o["appStop"] - o["appStart"]
    tx = math.floor(active * o["perUeOfferedMbps"] * 1e6 / (o["appPktSize"] * 8))
    metrics = {k: 0 for k in runner.METRICS}
    metrics.update(tx_pkts=tx, rx_pkts=rx, pdr=rx / tx, jain_fairness=1,
                   throughput_mbps=rx * (o["appPktSize"] - 12) * 8 / active / 1e6,
                   mean_lat_ms=2 if rx else "nan", p50_lat_ms=2 if rx else "nan",
                   p95_lat_ms=2 if rx else "nan")
    controls = {field: o[option] for option, field in runner.CSV_CONTROL.items()}
    record = {**controls, **metrics}
    fixture_csv(raw / "single_run.csv", record, [record])
    ue = {"ue_index": 0, "traffic_direction": o["trafficDirection"],
          **{k: metrics[k] for k in ("tx_pkts", "rx_pkts", "throughput_mbps", "pdr", "mean_lat_ms", "p95_lat_ms")}}
    fixture_csv(raw / "ue_metrics.csv", ue, [ue])
    packets = [{"ue_index": 0, "traffic_direction": o["trafficDirection"],
                "receive_time_s": o["appStart"] + active * (i + 1) / (rx + 1), "latency_ms": 2}
               for i in range(rx)]
    fixture_csv(raw / "packet_receptions.csv", ("ue_index", "traffic_direction", "receive_time_s", "latency_ms"), packets)
    fixture_csv(raw / "handover_events.csv", ("imsi", "source_cell_id", "target_cell_id", "final_cell_id", "start_time_s", "end_time_s", "protocol_duration_ms", "application_gap_ms", "success", "completed"))
    fixture_csv(raw / "ue_serving_cells.csv", ("imsi", "initial_cell_id", "final_cell_id", "changed"))
    fixture_csv(raw / "rsrp_measurements.csv", ("time_s", "imsi", "serving_cell_id", "serving_rsrp_code", "serving_rsrp_dbm", "neighbour_cell_id", "neighbour_rsrp_code", "neighbour_rsrp_dbm", "has_neighbour"))


@pytest.fixture
def synthetic_campaign(tmp_path):
    binary = tmp_path / "synthetic_fixture_binary"
    binary.write_bytes(b"SYNTHETIC FIXTURE ONLY - NEVER EXECUTE")
    source = tmp_path / "hsr_velocity_connect.cc"
    source.write_text("// SYNTHETIC FIXTURE ONLY\n", encoding="utf-8")
    sources = {source.name: runner.sha256(source)}
    supported = sorted(set(runner.build_rows("smoke")[0]["options"]) | {"outDir"})
    provenance = {"binary": str(binary), "binary_sha256": runner.sha256(binary),
                  "source_root": str(tmp_path), "source_sha256": sources,
                  "source_bundle_sha256": runner.digest(sources), "supported_options": supported,
                  "evidence_type": "synthetic fixture, not simulation"}
    out = tmp_path / "synthetic-campaign"
    plan = runner.plan_campaign(out, provenance, profile="smoke")
    rows = {r["row_id"]: r for r in plan["rows"]}

    def executor(command, cwd, stdout, stderr, timeout):
        raw = Path(next(a.split("=", 1)[1] for a in command if a.startswith("--outDir=")))
        stdout.write_text("SYNTHETIC FIXTURE ONLY\n", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        fixture_output(raw, rows[raw.name])
        return 0

    return out, plan, executor


@pytest.mark.parametrize("profile,count", [("expanded", 680), ("principal", 160), ("load", 360), ("channel-sensitivity", 160), ("smoke", 16)])
def test_fixture_design_counts_and_identity_matching(profile, count):
    rows = runner.build_rows(profile)
    assert len(rows) == count
    runner.validate_rows(rows)
    assert rows == runner.build_rows(profile)
    grouped = {}
    for r in rows:
        grouped.setdefault(r["pair_id"], []).append(r)
    for pair in grouped.values():
        assert len(pair) == 2
        assert len({(r["seed"], r["run"]) for r in pair}) == 1
    assert len({(r["seed"], r["run"]) for r in rows}) == count // 2


def test_fixture_focused_profiles_are_disjoint_exact_expanded_subsets():
    expanded = runner.build_rows("expanded")
    assert expanded == (runner.build_rows("principal") + runner.build_rows("load") + runner.build_rows("channel-sensitivity"))
    smoke = runner.build_rows("smoke")
    assert not {(r["seed"], r["run"]) for r in smoke} & {(r["seed"], r["run"]) for r in expanded}


def test_fixture_exposure_and_load_replication_contract():
    groups = {}
    for r in runner.build_rows("principal"):
        groups.setdefault((r["cell_id"], r["treatment"]), []).append(r)
        assert r["planned_active_km"] == pytest.approx(1)
    assert all(len(rows) == 40 and sum(r["planned_active_km"] for r in rows) >= 40 for rows in groups.values())
    load = runner.build_rows("load")
    assert {r["options"]["perUeOfferedMbps"] for r in load} == {4, 20, 50}
    assert {r["options"]["numUes"] for r in load} == {1, 4, 16}
    counts = runner.Counter((r["cell_id"], r["treatment"]) for r in load)
    assert set(counts.values()) == {20}
    assert all(r["options"]["trafficDirection"] == "downlink" for r in load)
    sensitivity = runner.build_rows("channel-sensitivity")
    assert {r["options"]["nrScenario"] for r in sensitivity} == {"UMi", "RMa"}
    assert "not railway-calibrated" in runner.BOUNDARY


@pytest.mark.parametrize("arg", ["--seed=7", "--perUeOfferedMbps=999", "--outDir=elsewhere", "--PrintHelp=1", "--bogus=1", "--foo", "--foo=1 --seed=2"])
def test_fixture_extra_arguments_fail_closed(arg):
    # Whitespace inside a value is passed literally, never interpreted by a shell.
    supported = ["foo"] if arg != "--foo=1 --seed=2" else []
    with pytest.raises(ValueError):
        runner.build_rows(extra_args=[arg], supported=supported)


def test_fixture_candidate_requires_explicit_mode_and_artifact():
    with pytest.raises(ValueError, match="Candidate requires"):
        runner.build_rows(candidate_args=["--passiveModel=fixture_matrix"], supported=["passiveModel"])
    rows = runner.build_rows("smoke", candidate_args=["--passiveModel=fixture_matrix", "--fixtureBridge=/a path/input.json"],
                             candidate_artifacts=["fixture-only.json"], supported=["passiveModel", "fixtureBridge"])
    assert len(rows) == 24
    assert {r["options"]["passiveModel"] for r in rows if r["treatment"] == "candidate_bridge"} == {"fixture_matrix"}
    assert all("fixtureBridge" not in r["options"] for r in rows if r["treatment"] != "candidate_bridge")


def test_fixture_current_em_bridge_cannot_enter_moving_campaign():
    kwargs = dict(candidate_args=["--passiveModel=em_complex", "--emTouchstone=fixture.s4p", "--emOperators=fixture.csv"],
                  candidate_artifacts=["fixture.s4p", "fixture.csv"], supported=["passiveModel", "emTouchstone", "emOperators"])
    with pytest.raises(ValueError, match="static single-link"):
        runner.build_rows("expanded", **kwargs)
    rows = runner.build_rows("bridge-smoke", **kwargs)
    assert len(rows) == 6
    assert all(r["planned_active_km"] == 0 and r["options"]["speed"] == 0 and r["options"]["numGnbs"] == 1 for r in rows)
    assert all(r["options"]["distance"] == 500 and r["options"]["gnbLateralOffsetM"] == 0 for r in rows)


def test_fixture_plan_is_immutable_and_all_rows_predeclared(synthetic_campaign):
    out, plan, _ = synthetic_campaign
    states = runner.read_ledger(out, plan)
    assert len(states) == 16
    assert {e["status"] for e in states.values()} == {"planned"}
    assert all(e["binary_sha256"] and e["source_bundle_sha256"] for e in states.values())
    report = analysis.analyze_campaign(out)
    assert report["statistics"] is None
    assert report["audit"]["campaign_status"] == "incomplete"
    path = out / "plan.json"
    changed = json.loads(path.read_text())
    changed["rows"][0]["seed"] += 1
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="digest"):
        runner.load_plan(out)


def test_fixture_success_and_resume_are_idempotent(synthetic_campaign):
    out, plan, executor = synthetic_campaign
    result = runner.run_campaign(out, executor=executor)
    assert result["campaign_status"] == "succeeded"
    before = (out / "ledger.jsonl").read_bytes()
    runner.run_campaign(out, executor=lambda *a: pytest.fail("must not rerun"))
    assert (out / "ledger.jsonl").read_bytes() == before
    report = analysis.analyze_campaign(out)
    assert report["statistics"] is not None
    assert len(report["statistics"]["runs"]) == 16
    assert all(g["principal_40km_exposure_met"] is None for g in report["statistics"]["groups"])
    estimate = report["statistics"]["paired_contrasts"][0]["estimates"]["throughput_mbps"]
    assert estimate["valid_pairs"] == 2
    assert estimate["resamples"] == 20000
    assert estimate["ci95_low"] == estimate["ci95_high"] == 0


@pytest.mark.parametrize("failure", ["exit", "timeout", "malformed"])
def test_fixture_failures_retained_no_retry_or_partial_statistics(synthetic_campaign, failure):
    out, plan, executor = synthetic_campaign
    count = 0

    def fail_once(*args):
        nonlocal count
        count += 1
        if count == 1:
            if failure == "timeout":
                raise subprocess.TimeoutExpired("synthetic fixture", 1)
            if failure == "malformed":
                return 0
            return 7
        return executor(*args)

    result = runner.run_campaign(out, executor=fail_once)
    assert count == 16  # fixed campaign, not result-dependent stopping
    assert result["campaign_status"] == "failed"
    before = (out / "ledger.jsonl").read_bytes()
    runner.run_campaign(out, executor=lambda *a: pytest.fail("no silent retry"))
    assert (out / "ledger.jsonl").read_bytes() == before
    report = analysis.analyze_campaign(out)
    assert report["statistics"] is None
    assert len(report["all_outcomes"]) == 16


def test_fixture_crash_recovery_explicit_never_retries(synthetic_campaign):
    out, plan, executor = synthetic_campaign
    runner.append_event(out, plan, plan["rows"][0], "running")
    with pytest.raises(ValueError, match="recover-interrupted"):
        runner.run_campaign(out, executor=executor)
    result = runner.run_campaign(out, executor=executor, recover_interrupted=True)
    assert result["status_counts"] == {"interrupted": 1, "succeeded": 15}
    assert not (out / "raw" / plan["rows"][0]["row_id"]).exists()


def test_fixture_binary_drift_prevents_execution(synthetic_campaign):
    out, plan, executor = synthetic_campaign
    Path(plan["provenance"]["binary"]).write_bytes(b"CHANGED FIXTURE")
    with pytest.raises(ValueError, match="binary changed"):
        runner.run_campaign(out, executor=executor)
    assert {e["status"] for e in runner.read_ledger(out, plan).values()} == {"planned"}


def test_fixture_ledger_rejects_deleted_failed_rows_and_retries(synthetic_campaign):
    out, plan, _ = synthetic_campaign
    row = plan["rows"][0]
    runner.append_event(out, plan, row, "running")
    runner.append_event(out, plan, row, "failed")
    runner.append_event(out, plan, row, "running")
    with pytest.raises(ValueError, match="no retries"):
        runner.read_ledger(out, plan)


def test_fixture_raw_tamper_refuses_analysis(synthetic_campaign):
    out, plan, executor = synthetic_campaign
    runner.run_campaign(out, executor=executor)
    raw = out / "raw" / plan["rows"][0]["row_id"] / "packet_receptions.csv"
    with raw.open("a") as f:
        f.write("0,downlink,0.3,2\n")
    with pytest.raises(ValueError, match="evidence changed"):
        analysis.analyze_campaign(out)


def test_fixture_zero_reception_latency_undefined_and_edges_preserved(synthetic_campaign):
    out, plan, executor = synthetic_campaign

    def zero_executor(command, cwd, stdout, stderr, timeout):
        rc = executor(command, cwd, stdout, stderr, timeout)
        raw = Path(next(a.split("=", 1)[1] for a in command if a.startswith("--outDir=")))
        fixture_output(raw, next(r for r in plan["rows"] if r["row_id"] == raw.name), rx=0)
        return rc

    runner.run_campaign(out, executor=zero_executor)
    report = analysis.analyze_campaign(out)
    record = report["statistics"]["runs"][0]
    assert record["metrics"]["p95_lat_ms"] is None
    assert record["metrics"]["maximum_receive_gap_ms"] == pytest.approx(200)
    assert record["metrics"]["unserved_edge_ms"] == pytest.approx(200)
    assert record["event_counts"]["internal_gaps_scale_1.0"] == 0
    estimate = report["statistics"]["paired_contrasts"][0]["estimates"]["p95_lat_ms"]
    assert estimate["valid_pairs"] == 0 and estimate["undefined_pairs"] == 2
    assert estimate["mean_difference"] is None and estimate["ci95_high"] is None


def test_fixture_threshold_scaling_and_per_ue_edges(tmp_path):
    path = tmp_path / "synthetic-packets.csv"
    fixture_csv(path, ("ue_index", "traffic_direction", "receive_time_s", "latency_ms"),
                [{"ue_index": 0, "traffic_direction": "downlink", "receive_time_s": t, "latency_ms": 1} for t in (1.01, 1.03, 1.10)])
    result = analysis.continuity(path, ues=2, direction="downlink", start=1, stop=1.2,
                                 threshold_ms=20, scales=[0.5, 1.0, 2.0])
    assert result["internal_gap_counts"] == {"0.5": 2, "1.0": 1, "2.0": 1}
    assert result["unserved_edge_ms"] == pytest.approx(310)
    assert result["maximum_receive_gap_ms"] == pytest.approx(200)
    assert result["zero_reception_ues"] == 1


def test_fixture_exact_poisson_zero_and_nonzero_bounds():
    result = analysis.poisson_bounds(0, 40)
    assert result["one_sided_upper"] == pytest.approx(-math.log(0.05) / 40)
    assert result["two_sided_high"] == pytest.approx(-math.log(0.025) / 40)
    assert result["two_sided_low"] == 0
    result = analysis.poisson_bounds(5, 40)
    assert poisson.cdf(5, result["two_sided_high"] * 40) == pytest.approx(0.025)
    assert poisson.sf(4, result["two_sided_low"] * 40) == pytest.approx(0.025)
    with pytest.raises(ValueError):
        analysis.poisson_bounds(1.5, 0)


def test_fixture_bootstrap_whole_run_blocks_matches_independent_reference():
    differences = [1, 2, 5, 9]
    result = analysis.paired_bootstrap(differences, seed=73)
    rng = np.random.default_rng(73)
    means = np.array(differences)[rng.integers(0, 4, size=(20000, 4))].mean(axis=1)
    assert result["ci95_low"] == pytest.approx(np.quantile(means, 0.025))
    assert result["ci95_high"] == pytest.approx(np.quantile(means, 0.975))
    missing = analysis.paired_bootstrap([1, None, 3], seed=1)
    assert missing["valid_pairs"] == 2 and missing["mean_difference"] is None


def test_fixture_pairing_uses_identifiers_not_row_order(synthetic_campaign):
    out, _, executor = synthetic_campaign
    runner.run_campaign(out, executor=executor)
    records = analysis.analyze_campaign(out)["statistics"]["runs"]
    assert analysis.paired_contrasts(records) == analysis.paired_contrasts(list(reversed(records)))
    changed = copy.deepcopy(records)
    changed[1]["run"] += 1
    with pytest.raises(ValueError, match="Unmatched"):
        analysis.paired_contrasts(changed)
    with pytest.raises(ValueError, match="Unmatched"):
        analysis.paired_contrasts(records[1:])


def test_fixture_ping_pong_requires_nonoverlapping_completed_reverse(tmp_path):
    path = tmp_path / "synthetic-handover.csv"
    fields = ("imsi", "source_cell_id", "target_cell_id", "start_time_s", "end_time_s", "success", "completed")
    data = [dict(zip(fields, values)) for values in [(1, 1, 2, 1, 1.2, 1, 1), (1, 2, 1, 1.1, 1.3, 1, 1), (1, 1, 2, 1.5, 1.6, 1, 1)]]
    fixture_csv(path, fields, data)
    result = analysis.handovers(path, start=1, stop=2, guarded=True, ping_pong_window_s=1)
    assert result["ping_pongs"] == 1


def test_fixture_path_escape_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unsafe"):
        runner.contained(tmp_path, "../outside")


@pytest.mark.parametrize("text", ["a,a\n1,2\n", "a\n1,2\n", "a,b\n1\n", "wrong\n1\n"])
def test_fixture_csv_header_and_row_width_strictness(tmp_path, text):
    path = tmp_path / "malformed-fixture.csv"
    path.write_text(text)
    with pytest.raises(ValueError, match="CSV"):
        list(runner.read_csv(path, ["a"]))


def test_fixture_throughput_includes_payload_only(synthetic_campaign):
    out, plan, executor = synthetic_campaign
    raw = out / "fixture-only-raw"
    raw.mkdir()
    row = plan["rows"][0]
    fixture_output(raw, row)
    data = list(runner.read_csv(raw / "single_run.csv", runner.METRICS))[0]
    data["throughput_mbps"] = float(data["throughput_mbps"]) * 1024 / 1012
    fixture_csv(raw / "single_run.csv", data, [data])
    with pytest.raises(ValueError, match="Payload throughput"):
        runner.validate_result(raw, row)


def test_fixture_em_artifact_binding_required():
    with pytest.raises(ValueError, match="emOperators"):
        runner.build_rows("bridge-smoke", candidate_args=["--passiveModel=em_complex", "--emTouchstone=fixture.s4p", "--emOperators=unhashed.csv"],
                          candidate_artifacts=["fixture.s4p"], supported=["passiveModel", "emTouchstone", "emOperators"])


def test_fixture_static_bridge_does_not_schedule_dynamic_channel_updates():
    rows = runner.build_rows("bridge-smoke", candidate_args=["--passiveModel=em_complex", "--emTouchstone=fixture.s4p", "--emOperators=operators.csv"],
                             candidate_artifacts=["fixture.s4p", "operators.csv"],
                             supported=["passiveModel", "emTouchstone", "emOperators"])
    assert len(rows) == 6
    for row in rows:
        assert row["options"]["speed"] == 0
        assert row["options"]["channelUpdatePeriodMs"] == 0
        assert row["options"]["enableHandover"] == 0


def test_fixture_runner_keeps_result_directory_empty_at_process_entry(synthetic_campaign):
    out, plan, executor = synthetic_campaign
    def empty_directory_executor(command, cwd, stdout, stderr, timeout):
        raw = Path(next(a.split("=", 1)[1] for a in command if a.startswith("--outDir=")))
        assert list(raw.iterdir()) == []
        assert stdout.parent != raw and stderr.parent != raw
        return executor(command, cwd, stdout, stderr, timeout)
    assert runner.run_campaign(out, executor=empty_directory_executor)["campaign_status"] == "succeeded"
    row_id = plan["rows"][0]["row_id"]
    (out / "logs" / row_id / "stderr.log").write_text("altered log")
    with pytest.raises(ValueError, match="Execution log changed"):
        analysis.analyze_campaign(out)
