#!/usr/bin/env python3
"""Run and validate the paper-profile stability checkpoint.

The checkpoint is deliberately small but stresses the failure boundary that
previously exposed 5G-LENA issue #278: 10 UEs at 500 km/h and 500 m in each of
the metal, composite, and passive-repeater scenarios.
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


EXPECTED_SCENARIOS = {"metal", "composite", "repeater"}
ALWAYS_FINITE_FIELDS = ("throughput_mbps", "pdr")
LATENCY_FIELDS = ("mean_lat_ms", "p95_lat_ms")
UPSTREAM_FIX_REVISIONS = (
    "81892efac84f2aef0a962b9da176ea7d7b6912b0",
    "a1aa32c757e0f834a4e40654853ce56dee13eca3",
)


def validate_checkpoint(ledger_path: Path) -> dict[str, dict[str, float | None]]:
    """Validate one successful, internally consistent result per scenario."""

    with ledger_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != len(EXPECTED_SCENARIOS):
        raise ValueError(f"Expected 3 checkpoint rows, found {len(rows)}")

    actual_scenarios = {row.get("scenario", "") for row in rows}
    if actual_scenarios != EXPECTED_SCENARIOS:
        raise ValueError(
            f"Scenario mismatch: expected {sorted(EXPECTED_SCENARIOS)}, "
            f"found {sorted(actual_scenarios)}"
        )

    results: dict[str, dict[str, float | None]] = {}
    for row in rows:
        scenario = row["scenario"]
        if row.get("status") != "ok":
            error = row.get("error", "").strip()
            raise ValueError(f"{scenario} checkpoint failed: {error or 'unknown simulator error'}")

        metrics: dict[str, float | None] = {}
        for field in ALWAYS_FINITE_FIELDS:
            try:
                value = float(row[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{scenario} has invalid {field}") from exc
            if not math.isfinite(value):
                raise ValueError(f"{scenario} has non-finite {field}: {value}")
            metrics[field] = value

        if not 0.0 <= metrics["pdr"] <= 1.0:
            raise ValueError(f"{scenario} has PDR outside [0, 1]: {metrics['pdr']}")

        for field in LATENCY_FIELDS:
            try:
                value = float(row[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{scenario} has invalid {field}") from exc
            if math.isfinite(value):
                metrics[field] = value
            elif metrics["pdr"] == 0.0:
                metrics[field] = None
            else:
                raise ValueError(f"{scenario} has non-finite {field} despite nonzero PDR")

        results[scenario] = metrics

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns3", default="/home/codex/velocity-connect-ns3/ns3")
    parser.add_argument("--workdir", default="/home/codex/velocity-connect-ns3")
    parser.add_argument("--program", default="hsr_velocity_connect")
    parser.add_argument("--out", default="out/paper_checkpoint")
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
                "--profile", "paper",
                "--ns3", args.ns3,
                "--workdir", args.workdir,
                "--program", args.program,
                "--out", str(output),
                "--scenarios", "metal,composite,repeater",
                "--speeds", "500",
                "--distances", "500",
                "--num-ues", "10",
                "--seeds", "7",
                "--run-base", "7001",
                "--timeout", str(args.timeout),
                "--max-runs", "3",
            ]
        )
        status = run_campaign(campaign_args)
        if status:
            return status

    try:
        results = validate_checkpoint(ledger)
    except (OSError, ValueError) as exc:
        print(f"Paper checkpoint invalid: {exc}", file=sys.stderr)
        return 1

    report = {
        "status": "passed",
        "checkpoint": {
            "speed_kmph": 500,
            "distance_m": 500,
            "num_ues": 10,
            "seed": 7,
            "scenarios": sorted(EXPECTED_SCENARIOS),
        },
        "dependency_fix": {
            "project": "CTTC 5G-LENA",
            "upstream_revisions": list(UPSTREAM_FIX_REVISIONS),
            "patches": [
                "patches/5g-lena-v4.1.1-harq-beam-order.patch",
                "patches/5g-lena-v4.1.1-harq-symbol-budget.patch",
            ],
        },
        "results": results,
    }
    report_path = output / "paper_checkpoint_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Paper checkpoint passed: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
