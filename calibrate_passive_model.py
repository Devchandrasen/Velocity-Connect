#!/usr/bin/env python3
"""Convert measured VNA/OTA records into simulator-ready passive budgets."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from passive_feedthrough import budget_from_measurement, summarize_budgets


def calibrate(input_csv: Path, output_dir: Path) -> dict[str, object]:
    with input_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("measurement CSV contains no data rows")

    output_rows: list[dict[str, object]] = []
    budgets = []
    for index, row in enumerate(rows, start=2):
        try:
            sample_id, frequency_hz, budget = budget_from_measurement(row)
        except ValueError as exc:
            raise ValueError(f"{input_csv}:{index}: {exc}") from exc
        budgets.append(budget)
        output_rows.append(
            {
                "sample_id": sample_id,
                "frequency_hz": frequency_hz,
                "sim_feeder_loss_db": budget.feeder_loss_db,
                "sim_coupling_loss_db": budget.coupling_loss_db,
                "sim_indoor_path_loss_db": budget.indoor_path_loss_db,
                "donor_gain_dbi": budget.donor_gain_dbi,
                "service_gain_dbi": budget.service_gain_dbi,
                "network_loss_db": budget.network_loss_db,
                "aperture_gain_db": budget.aperture_gain_db,
                "equivalent_loss_db": budget.equivalent_loss_db,
                "campaign_arguments": (
                    f"--feeder-cable-loss-db={budget.feeder_loss_db:g} "
                    f"--coupling-loss-db={budget.coupling_loss_db:g} "
                    f"--indoor-distrib-loss-db={budget.indoor_path_loss_db:g} "
                    f"--donor-gain-dbi={budget.donor_gain_dbi:g} "
                    f"--service-gain-dbi={budget.service_gain_dbi:g}"
                ),
            }
        )

    summary: dict[str, object] = summarize_budgets(budgets)
    summary.update(
        {
            "source_csv": str(input_csv.resolve()),
            "synthetic_measurements_used": False,
            "simulator_mapping": {
                "feederCableLossDb": "sim_feeder_loss_db",
                "couplingLossDb": "sim_coupling_loss_db",
                "indoorDistribLossDb": "sim_indoor_path_loss_db",
                "donorGainDbi": "donor_gain_dbi",
                "serviceGainDbi": "service_gain_dbi",
            },
        }
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    calibrated_csv = output_dir / "calibrated_component_samples.csv"
    with calibrated_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    (output_dir / "calibration_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurement_csv", type=Path)
    parser.add_argument("--out", type=Path, default=Path("out/passive_calibration"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = calibrate(args.measurement_csv, args.out)
    except (OSError, ValueError) as exc:
        print(f"Calibration failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
