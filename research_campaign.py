#!/usr/bin/env python3
"""Run reproducible multi-seed Velocity Connect experiments.

The NS-3 application exposes a machine-readable ``single_run.csv`` endpoint.
This driver owns the experiment matrix, process isolation, failure ledger, and
confidence-interval summary so a partial campaign is still auditable.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
from itertools import product
from pathlib import Path
from typing import Iterable, Mapping, Sequence


METRICS = (
    "throughput_mbps",
    "pdr",
    "mean_lat_ms",
    "p95_lat_ms",
    "jain_fairness",
)
REQUIRED_RESULT_FIELDS = {
    "scenario",
    "speed_kmph",
    "distance_m",
    "num_ues",
    "seed",
    "run",
    "eff_loss_db",
    "numerology",
    "scs_khz",
    "throughput_mbps",
    "pdr",
    "tx_pkts",
    "rx_pkts",
    "mean_lat_ms",
    "p50_lat_ms",
    "p95_lat_ms",
    "jain_fairness",
}


PROFILE_DEFAULTS: dict[str, dict[str, object]] = {
    "dev": {
        "num_ues": 1,
        "numerology": 0,
        "sim_time": 2.0,
        "app_start": 0.2,
        "app_pkt_size": 1024,
        "saturating_load": True,
        "per_ue_offered_mbps": 8.19,
        "saturating_interval_us": 100.0,
        "paper_profile": False,
    },
    "paper": {
        "num_ues": 10,
        "numerology": 1,
        "sim_time": 2.0,
        "app_start": 0.2,
        "app_pkt_size": 1024,
        "saturating_load": False,
        "per_ue_offered_mbps": 8.19,
        "saturating_interval_us": 100.0,
        "paper_profile": True,
    },
}


def parse_csv_list(raw: str, cast):
    """Parse a comma-separated CLI value while rejecting empty entries."""

    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            raise ValueError(f"Invalid empty value in list: {raw!r}")
        values.append(cast(item))
    if not values:
        raise ValueError("At least one value is required")
    return values


def build_simulation_command(
    ns3: str,
    program: str,
    scenario: str,
    speed_kmph: float,
    distance_m: float,
    num_ues: int,
    seed: int,
    run: int,
    out_dir: Path,
    *,
    sim_time: float = 2.0,
    app_start: float = 0.2,
    app_pkt_size: int = 1024,
    saturating_load: bool = True,
    per_ue_offered_mbps: float = 8.19,
    saturating_interval_us: float = 100.0,
    paper_profile: bool = False,
    numerology: int = 0,
) -> list[str]:
    """Build an argv-safe NS-3 wrapper command without invoking a shell."""

    run_arguments = (
        f"{program} --singleRun=1 --scenario={scenario} "
        f"--speed={speed_kmph:g} --distance={distance_m:g} "
        f"--numUes={num_ues} --seed={seed} --run={run} "
        f"--simTime={sim_time:g} --appStart={app_start:g} "
        f"--appPktSize={app_pkt_size} --saturatingLoad={int(saturating_load)} "
        f"--perUeOfferedMbps={per_ue_offered_mbps:g} "
        f"--saturatingIntervalUs={saturating_interval_us:g} "
        f"--numerology={numerology} "
        f"--paperProfile={int(paper_profile)} "
        f"--outDir={out_dir.as_posix()}"
    )
    return [ns3, "run", run_arguments]


def resolve_profile(args: argparse.Namespace) -> dict[str, object]:
    """Resolve profile defaults while preserving explicit CLI overrides."""

    values = dict(PROFILE_DEFAULTS[args.profile])
    overrides = {
        "num_ues": args.num_ues,
        "numerology": args.numerology,
        "sim_time": args.sim_time,
        "app_start": args.app_start,
        "app_pkt_size": args.app_pkt_size,
        "saturating_load": args.saturating_load,
        "per_ue_offered_mbps": args.per_ue_offered_mbps,
        "saturating_interval_us": args.saturating_interval_us,
    }
    for key, value in overrides.items():
        if value is not None:
            values[key] = value
    return values


def read_single_result(path: Path) -> dict[str, str]:
    """Read and validate exactly one simulator result row."""

    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != 1:
        raise ValueError(f"Expected one result row in {path}, found {len(rows)}")

    row = rows[0]
    missing = REQUIRED_RESULT_FIELDS.difference(row)
    if missing:
        raise ValueError(f"Missing result fields in {path}: {sorted(missing)}")
    return row


def _finite_values(rows: Iterable[Mapping[str, str]], field: str) -> list[float]:
    values = []
    for row in rows:
        try:
            value = float(row[field])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def aggregate_rows(rows: Sequence[Mapping[str, str]]) -> list[dict[str, object]]:
    """Aggregate successful single-run rows with sample SD and 95% CI."""

    groups: dict[tuple[str, float, float, int], list[Mapping[str, str]]] = {}
    for row in rows:
        key = (
            str(row["scenario"]),
            float(row["speed_kmph"]),
            float(row["distance_m"]),
            int(float(row["num_ues"])),
        )
        groups.setdefault(key, []).append(row)

    summaries: list[dict[str, object]] = []
    for (scenario, speed, distance, num_ues), group in sorted(groups.items()):
        summary: dict[str, object] = {
            "scenario": scenario,
            "speed_kmph": speed,
            "distance_m": distance,
            "num_ues": num_ues,
            "n_runs": len(group),
        }
        for metric in METRICS:
            values = _finite_values(group, metric)
            mean = statistics.fmean(values) if values else math.nan
            std = statistics.stdev(values) if len(values) > 1 else 0.0
            ci95 = 1.96 * std / math.sqrt(len(values)) if len(values) > 1 else 0.0
            summary[f"{metric}_n"] = len(values)
            summary[f"{metric}_mean"] = mean
            summary[f"{metric}_std"] = std
            summary[f"{metric}_ci95"] = ci95
        summaries.append(summary)
    return summaries


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_summary(path: Path, summaries: Sequence[Mapping[str, object]]) -> None:
    fields = ["scenario", "speed_kmph", "distance_m", "num_ues", "n_runs"]
    for metric in METRICS:
        fields.extend(
            [f"{metric}_n", f"{metric}_mean", f"{metric}_std", f"{metric}_ci95"]
        )
    _write_csv(path, summaries, fields)


def _tail(text: str, limit: int = 4000) -> str:
    text = text.strip()
    return text[-limit:] if text else ""


def run_campaign(args: argparse.Namespace) -> int:
    output_dir = Path(args.out)
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    profile = resolve_profile(args)
    scenarios = parse_csv_list(args.scenarios, str)
    unknown_scenarios = sorted(set(scenarios) - {"metal", "composite", "repeater"})
    if unknown_scenarios:
        raise ValueError(
            f"Unknown scenario(s): {', '.join(unknown_scenarios)}; "
            "expected metal, composite, or repeater"
        )
    speeds = parse_csv_list(args.speeds, float)
    distances = parse_csv_list(args.distances, float)
    seeds = parse_csv_list(args.seeds, int)
    if args.num_ues_list.strip():
        num_ues_values = parse_csv_list(args.num_ues_list, int)
    else:
        num_ues_values = [int(profile["num_ues"])]
    if any(value < 1 for value in num_ues_values):
        raise ValueError("All UE counts must be at least 1")
    runs = list(product(scenarios, speeds, distances, num_ues_values, seeds))
    if args.max_runs and len(runs) > args.max_runs:
        raise ValueError(
            f"Campaign contains {len(runs)} runs, exceeding --max-runs={args.max_runs}"
        )

    config = {
        "program": args.program,
        "ns3": args.ns3,
        "scenarios": scenarios,
        "speeds_kmph": speeds,
        "distances_m": distances,
        "seeds": seeds,
        "num_ues": profile["num_ues"],
        "num_ues_values": num_ues_values,
        "numerology": profile["numerology"],
        "subcarrier_spacing_khz": 15 * (2 ** int(profile["numerology"])),
        "profile": args.profile,
        "sim_time": profile["sim_time"],
        "app_start": profile["app_start"],
        "app_pkt_size": profile["app_pkt_size"],
        "saturating_load": profile["saturating_load"],
        "per_ue_offered_mbps": profile["per_ue_offered_mbps"],
        "saturating_interval_us": profile["saturating_interval_us"],
        "run_base": args.run_base,
        "timeout_s": args.timeout,
        "dry_run": args.dry_run,
    }
    (output_dir / "campaign_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    ledger_rows: list[dict[str, object]] = []
    successful_rows: list[dict[str, str]] = []
    for index, (scenario, speed, distance, num_ues, seed) in enumerate(runs):
        run_number = args.run_base + index
        run_id = f"run_{index + 1:04d}_{scenario}_{speed:g}kmh_{distance:g}m_n{num_ues}_seed{seed}"
        run_output = raw_dir / run_id
        run_output.mkdir(parents=True, exist_ok=True)
        command = build_simulation_command(
            args.ns3,
            args.program,
            scenario,
            speed,
            distance,
            num_ues,
            seed,
            run_number,
            run_output,
            sim_time=float(profile["sim_time"]),
            app_start=float(profile["app_start"]),
            app_pkt_size=int(profile["app_pkt_size"]),
            saturating_load=bool(profile["saturating_load"]),
            per_ue_offered_mbps=float(profile["per_ue_offered_mbps"]),
            saturating_interval_us=float(profile["saturating_interval_us"]),
            paper_profile=bool(profile["paper_profile"]),
            numerology=int(profile["numerology"]),
        )
        print(f"[{index + 1}/{len(runs)}] {run_id}")

        ledger: dict[str, object] = {
            "run_id": run_id,
            "scenario": scenario,
            "speed_kmph": speed,
            "distance_m": distance,
            "num_ues": num_ues,
            "seed": seed,
            "run": run_number,
            "status": "dry_run" if args.dry_run else "failed",
            "return_code": "",
            "raw_dir": str(run_output),
            "error": "",
        }

        if args.dry_run:
            print("  " + " ".join(command))
            ledger_rows.append(ledger)
            continue

        try:
            completed = subprocess.run(
                command,
                cwd=args.workdir,
                capture_output=True,
                text=True,
                timeout=args.timeout,
                check=False,
            )
            ledger["return_code"] = completed.returncode
            result_path = run_output / "single_run.csv"
            if completed.returncode != 0:
                ledger["error"] = _tail(completed.stderr or completed.stdout)
            elif not result_path.exists():
                ledger["error"] = "Simulator exited successfully but single_run.csv is missing"
            else:
                result = read_single_result(result_path)
                if result["scenario"] != scenario:
                    raise ValueError(
                        f"Result scenario {result['scenario']!r} does not match {scenario!r}"
                    )
                result_numerology_raw = float(result["numerology"])
                if not result_numerology_raw.is_integer():
                    raise ValueError(
                        f"Result numerology {result_numerology_raw} is not an integer"
                    )
                result_numerology = int(result_numerology_raw)
                expected_numerology = int(profile["numerology"])
                if result_numerology != expected_numerology:
                    raise ValueError(
                        f"Result numerology {result_numerology} does not match "
                        f"campaign numerology {expected_numerology}"
                    )
                result_scs_khz = float(result["scs_khz"])
                expected_scs_khz = 15.0 * (2 ** expected_numerology)
                if not math.isfinite(result_scs_khz) or not math.isclose(
                    result_scs_khz, expected_scs_khz, rel_tol=0.0, abs_tol=1e-9
                ):
                    raise ValueError(
                        f"Result SCS {result_scs_khz:g} kHz does not match "
                        f"campaign SCS {expected_scs_khz:g} kHz"
                    )
                result.update(
                    {
                        "run_id": run_id,
                        "status": "ok",
                        "return_code": completed.returncode,
                        "raw_dir": str(run_output),
                        "error": "",
                    }
                )
                successful_rows.append(result)
                ledger.update(result)
                ledger["status"] = "ok"
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            ledger["error"] = str(exc)

        ledger_rows.append(ledger)

    # Keep the ledger column order deterministic.
    ledger_fields = [
        "run_id", "status", "return_code", "scenario", "speed_kmph", "distance_m",
        "num_ues", "seed", "run", "raw_dir", "error", "eff_loss_db",
        "numerology", "scs_khz",
        "throughput_mbps", "pdr", "tx_pkts", "rx_pkts", "mean_lat_ms", "p50_lat_ms",
        "p95_lat_ms", "jain_fairness",
    ]
    for row in ledger_rows:
        for field in ledger_fields:
            row.setdefault(field, "")
    _write_csv(output_dir / "campaign_runs.csv", ledger_rows, ledger_fields)

    summaries = aggregate_rows(successful_rows)
    _write_summary(output_dir / "campaign_summary.csv", summaries)
    failed = sum(1 for row in ledger_rows if row["status"] == "failed")
    print(f"Campaign complete: {len(successful_rows)} succeeded, {failed} failed.")
    print(f"Run ledger: {output_dir / 'campaign_runs.csv'}")
    print(f"Summary:    {output_dir / 'campaign_summary.csv'}")
    return 1 if failed and not args.allow_failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns3", default="./ns3", help="Path to the ns-3 wrapper")
    parser.add_argument("--program", default="hsr_velocity_connect", help="Built ns-3 program name")
    parser.add_argument("--workdir", default=".", help="Working directory for the ns-3 wrapper")
    parser.add_argument("--out", default="out/campaign", help="Campaign output directory")
    parser.add_argument("--profile", choices=sorted(PROFILE_DEFAULTS), default="dev")
    parser.add_argument("--scenarios", default="metal,composite,repeater")
    parser.add_argument("--speeds", default="0,100,200,300,400,500")
    parser.add_argument("--distances", default="500")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--num-ues", type=int, default=None)
    parser.add_argument("--num-ues-list", default="", help="Optional comma-separated UE counts")
    parser.add_argument("--numerology", type=int, default=None)
    parser.add_argument("--sim-time", type=float, default=None)
    parser.add_argument("--app-start", type=float, default=None)
    parser.add_argument("--app-pkt-size", type=int, default=None)
    parser.add_argument("--saturating-load", type=lambda value: bool(int(value)), default=None)
    parser.add_argument("--per-ue-offered-mbps", type=float, default=None)
    parser.add_argument("--saturating-interval-us", type=float, default=None)
    parser.add_argument("--run-base", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--max-runs", type=int, default=0, help="Guardrail; 0 means unlimited")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running NS-3")
    parser.add_argument("--allow-failures", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.num_ues is not None and args.num_ues < 1:
        parser.error("--num-ues must be at least 1")
    if args.numerology is not None and not 0 <= args.numerology <= 5:
        parser.error("--numerology must be between 0 and 5")
    if args.max_runs < 0:
        parser.error("--max-runs cannot be negative")
    try:
        return run_campaign(args)
    except ValueError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
