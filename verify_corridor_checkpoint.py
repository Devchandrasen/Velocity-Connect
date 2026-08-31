#!/usr/bin/env python3
"""Run and validate a bounded multi-cell high-speed handover checkpoint.

This gate is intentionally stricter than a successful simulator exit. Every
seed must record at least one completed A3/X2 handover, a changed serving cell,
and a neighbour-RSRP report. The checkpoint uses ideal RRC and therefore does
not claim field or random-access interruption performance.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from research_campaign import build_parser as build_campaign_parser
from research_campaign import run_campaign


EXPECTED_MODEL = "component_budget"
EXPECTED_GNBS = 3
EXPECTED_SPACING_M = 1000.0
EXPECTED_HYSTERESIS_DB = 1.5
EXPECTED_TTT_MS = 128.0
EXPECTED_SEEDS = {21, 22, 23}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _raw_dir_for(row: dict[str, str], ledger_path: Path) -> Path:
    recorded_text = row.get("raw_dir", "").strip()
    if recorded_text:
        recorded = Path(recorded_text)
        if recorded.is_dir():
            return recorded
    local = ledger_path.parent / "raw" / row["run_id"]
    if local.is_dir():
        return local
    raise ValueError(f"{row['run_id']} raw evidence directory is missing")


def _finite_float(row: dict[str, str], field: str, run_id: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{run_id} has invalid {field}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{run_id} has non-finite {field}: {value}")
    return value


def _integer(row: dict[str, str], field: str, run_id: str) -> int:
    value = _finite_float(row, field, run_id)
    if not value.is_integer():
        raise ValueError(f"{run_id} has non-integer {field}: {value}")
    return int(value)


def validate_corridor_checkpoint(
    ledger_path: Path,
    *,
    expected_seeds: set[int] = EXPECTED_SEEDS,
) -> list[dict[str, float | int | str]]:
    """Validate successful protocol events and their per-run evidence files."""

    rows = _read_rows(ledger_path)
    if len(rows) != len(expected_seeds):
        raise ValueError(
            f"Expected {len(expected_seeds)} corridor rows, found {len(rows)}"
        )

    actual_seeds = {_integer(row, "seed", row.get("run_id", "unknown")) for row in rows}
    if actual_seeds != expected_seeds:
        raise ValueError(
            f"Seed mismatch: expected {sorted(expected_seeds)}, "
            f"found {sorted(actual_seeds)}"
        )

    results: list[dict[str, float | int | str]] = []
    for row in rows:
        run_id = row.get("run_id", "unknown")
        if row.get("status") != "ok":
            raise ValueError(
                f"{run_id} failed: {row.get('error', '').strip() or 'unknown simulator error'}"
            )
        if row.get("passive_model") != EXPECTED_MODEL:
            raise ValueError(f"{run_id} did not use {EXPECTED_MODEL}")
        if _integer(row, "enable_handover", run_id) != 1:
            raise ValueError(f"{run_id} did not enable handover")
        if _integer(row, "use_ideal_rrc", run_id) != 1:
            raise ValueError(f"{run_id} is not explicitly labelled ideal RRC")
        if _integer(row, "num_gnbs", run_id) != EXPECTED_GNBS:
            raise ValueError(f"{run_id} did not use {EXPECTED_GNBS} gNBs")

        spacing = _finite_float(row, "gnb_spacing_m", run_id)
        hysteresis = _finite_float(row, "handover_hysteresis_db", run_id)
        ttt = _finite_float(row, "handover_ttt_ms", run_id)
        if not math.isclose(spacing, EXPECTED_SPACING_M, abs_tol=1e-9):
            raise ValueError(f"{run_id} has unexpected gNB spacing {spacing}")
        if not math.isclose(hysteresis, EXPECTED_HYSTERESIS_DB, abs_tol=1e-9):
            raise ValueError(f"{run_id} has unexpected hysteresis {hysteresis}")
        if not math.isclose(ttt, EXPECTED_TTT_MS, abs_tol=1e-9):
            raise ValueError(f"{run_id} has unexpected time-to-trigger {ttt}")

        attempts = _integer(row, "handover_attempts", run_id)
        successes = _integer(row, "handover_successes", run_id)
        failures = _integer(row, "handover_failures", run_id)
        if attempts != successes + failures:
            raise ValueError(f"{run_id} has inconsistent handover accounting")
        if successes < 1:
            raise ValueError(f"{run_id} recorded no successful handover")

        raw_dir = _raw_dir_for(row, ledger_path)
        events = _read_rows(raw_dir / "handover_events.csv")
        completed = [
            event for event in events
            if event.get("success") == "1" and event.get("completed") == "1"
        ]
        if len(completed) != successes:
            raise ValueError(
                f"{run_id} ledger reports {successes} successes but "
                f"event evidence contains {len(completed)}"
            )
        for event in completed:
            start = _finite_float(event, "start_time_s", run_id)
            end = _finite_float(event, "end_time_s", run_id)
            duration = _finite_float(event, "protocol_duration_ms", run_id)
            gap = _finite_float(event, "application_gap_ms", run_id)
            if end <= start or duration <= 0.0 or gap < 0.0:
                raise ValueError(f"{run_id} contains an invalid completed event")

        cells = _read_rows(raw_dir / "ue_serving_cells.csv")
        if not cells or not any(cell.get("changed") == "1" for cell in cells):
            raise ValueError(f"{run_id} has no serving-cell transition evidence")

        measurements = _read_rows(raw_dir / "rsrp_measurements.csv")
        triggers = [
            measurement for measurement in measurements
            if measurement.get("has_neighbour") == "1"
        ]
        if not triggers:
            raise ValueError(f"{run_id} has no neighbour-RSRP trigger evidence")
        for measurement in triggers:
            _finite_float(measurement, "serving_rsrp_dbm", run_id)
            _finite_float(measurement, "neighbour_rsrp_dbm", run_id)

        results.append(
            {
                "run_id": run_id,
                "seed": _integer(row, "seed", run_id),
                "handover_attempts": attempts,
                "handover_successes": successes,
                "handover_failures": failures,
                "mean_handover_duration_ms": _finite_float(
                    row, "mean_handover_duration_ms", run_id
                ),
                "mean_application_gap_ms": _finite_float(
                    row, "mean_application_gap_ms", run_id
                ),
            }
        )

    return sorted(results, key=lambda item: int(item["seed"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns3", default="/home/codex/velocity-connect-ns3/ns3")
    parser.add_argument("--workdir", default="/home/codex/velocity-connect-ns3")
    parser.add_argument("--program", default="hsr_velocity_connect")
    parser.add_argument("--out", default="out/corridor_checkpoint")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing campaign_runs.csv without launching ns-3",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.out).resolve()
    ledger = output / "campaign_runs.csv"

    if not args.validate_only:
        campaign_args = build_campaign_parser().parse_args(
            [
                "--profile", "corridor",
                "--ns3", args.ns3,
                "--workdir", args.workdir,
                "--program", args.program,
                "--out", str(output),
                "--scenarios", "repeater",
                "--speeds", "500",
                "--distances", "100",
                "--num-ues", "1",
                "--seeds", "21,22,23",
                "--run-base", "8100",
                "--sim-time", "13",
                "--timeout", str(args.timeout),
                "--max-runs", "3",
            ]
        )
        status = run_campaign(campaign_args)
        if status:
            return status

    try:
        results = validate_corridor_checkpoint(ledger)
    except (OSError, ValueError) as exc:
        print(f"Corridor checkpoint invalid: {exc}", file=sys.stderr)
        return 1

    report = {
        "status": "passed",
        "claim_boundary": (
            "Protocol-event checkpoint under ideal RRC; not field, OTA, "
            "random-access, or hardware validation."
        ),
        "checkpoint": {
            "scenario": "repeater",
            "speed_kmph": 500,
            "initial_distance_m": 100,
            "num_ues": 1,
            "num_gnbs": EXPECTED_GNBS,
            "gnb_spacing_m": EXPECTED_SPACING_M,
            "seeds": sorted(EXPECTED_SEEDS),
            "handover_algorithm": "A3-RSRP",
            "hysteresis_db": EXPECTED_HYSTERESIS_DB,
            "time_to_trigger_ms": EXPECTED_TTT_MS,
            "ideal_rrc": True,
        },
        "dependency_patches": [
            "patches/5g-lena-v4.1.1-handover-wiring.patch",
            "patches/5g-lena-v4.1.1-handover-lifetime.patch",
        ],
        "results": results,
    }
    report_path = output / "corridor_checkpoint_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Corridor checkpoint passed: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
