"""Summarize angular-grid convergence for the selected n78 V2 HFSS model."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CANDIDATE = "Velocity_Connect_n78_V2_DualPort_S150_PowerQA_B25_B1"
RESULTS = ROOT / "results" / "n78_v2_dualport" / CANDIDATE
INPUTS = (
    RESULTS / "embedded_pattern_metrics_simpson.json",
    RESULTS / "embedded_pattern_metrics_2p5deg.json",
    RESULTS / "embedded_pattern_metrics_1deg.json",
)
OUTPUT_JSON = RESULTS / "field_angular_convergence_summary.json"
OUTPUT_CSV = RESULTS / "field_angular_convergence_summary.csv"


def _metrics(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("embedded_pattern_metrics", payload)


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if payload.get("status") not in (None, "complete"):
        raise RuntimeError(f"Incomplete field evidence: {path}")
    metrics = _metrics(payload)
    if len(metrics.get("per_port", [])) != 2:
        raise RuntimeError(f"Two embedded patterns were expected: {path}")
    return metrics


def _row(path: Path, metrics: dict[str, Any]) -> dict[str, Any]:
    grid = metrics["integration_grid"]
    ports = metrics["per_port"]
    coverage = metrics["upper_horizon_selection_coverage"]
    return {
        "evidence_file": path.name,
        "angular_step_deg": grid["theta_step_deg"],
        "theta_samples": grid["theta_samples"],
        "phi_samples": grid["phi_samples"],
        "simpson_trapezoid_difference_port1_percent": grid[
            "power_integral_difference_percent"
        ][ports[0]["source"]],
        "simpson_trapezoid_difference_port2_percent": grid[
            "power_integral_difference_percent"
        ][ports[1]["source"]],
        "embedded_field_ecc": metrics["embedded_field_ecc"],
        "diversity_gain_db": metrics["embedded_field_diversity_gain_db"],
        "radiation_efficiency_port1_ratio": ports[0][
            "radiation_efficiency_far_field_integral_ratio"
        ],
        "radiation_efficiency_port2_ratio": ports[1][
            "radiation_efficiency_far_field_integral_ratio"
        ],
        "total_efficiency_port1_ratio": ports[0][
            "total_efficiency_far_field_integral_ratio"
        ],
        "total_efficiency_port2_ratio": ports[1][
            "total_efficiency_far_field_integral_ratio"
        ],
        "peak_realized_gain_port1_dbi": ports[0][
            "peak_realized_gain_far_field_integral_dbi"
        ],
        "peak_realized_gain_port2_dbi": ports[1][
            "peak_realized_gain_far_field_integral_dbi"
        ],
        "upper_horizon_fraction_at_or_above_0_dbi": coverage[
            "fraction_at_or_above_0_dbi"
        ],
        "upper_horizon_p10_realized_gain_dbi": coverage[
            "p10_realized_gain_dbi"
        ],
    }


def _absolute_delta(a: dict[str, Any], b: dict[str, Any], key: str) -> float:
    return abs(float(a[key]) - float(b[key]))


def main() -> None:
    rows = [_row(path, _load(path)) for path in INPUTS]
    rows.sort(key=lambda item: item["angular_step_deg"], reverse=True)
    fine = next(row for row in rows if row["angular_step_deg"] == 1.0)
    medium = next(row for row in rows if row["angular_step_deg"] == 2.5)

    delta = {
        "embedded_field_ecc_absolute": _absolute_delta(
            medium, fine, "embedded_field_ecc"
        ),
        "radiation_efficiency_port1_percentage_points": 100.0
        * _absolute_delta(
            medium, fine, "radiation_efficiency_port1_ratio"
        ),
        "radiation_efficiency_port2_percentage_points": 100.0
        * _absolute_delta(
            medium, fine, "radiation_efficiency_port2_ratio"
        ),
        "peak_realized_gain_port1_db": _absolute_delta(
            medium, fine, "peak_realized_gain_port1_dbi"
        ),
        "peak_realized_gain_port2_db": _absolute_delta(
            medium, fine, "peak_realized_gain_port2_dbi"
        ),
        "upper_horizon_coverage_percentage_points": 100.0
        * _absolute_delta(
            medium,
            fine,
            "upper_horizon_fraction_at_or_above_0_dbi",
        ),
        "upper_horizon_p10_gain_db": _absolute_delta(
            medium, fine, "upper_horizon_p10_realized_gain_dbi"
        ),
    }
    angular_power_convergence_pass = (
        delta["embedded_field_ecc_absolute"] <= 1e-5
        and delta["radiation_efficiency_port1_percentage_points"] <= 0.01
        and delta["radiation_efficiency_port2_percentage_points"] <= 0.01
        and delta["peak_realized_gain_port1_db"] <= 0.05
        and delta["peak_realized_gain_port2_db"] <= 0.05
    )
    angular_grid_diagnostic_robust = all(
        row["upper_horizon_fraction_at_or_above_0_dbi"] >= 0.90
        for row in rows
    )
    one_percent_power_balance_diagnostic = all(
        0.0 <= fine[f"{metric}_efficiency_port{port}_ratio"] <= 1.01
        for port in (1, 2)
        for metric in ("radiation", "total")
    )
    strict_power_balance = all(
        0.0
        <= fine[f"{metric}_efficiency_port{port}_ratio"]
        <= 1.0 + 1e-9
        for port in (1, 2)
        for metric in ("radiation", "total")
    )

    payload = {
        "status": "complete",
        "evidence_class": "simulated",
        "candidate": CANDIDATE,
        "selected_grid_deg": 1.0,
        "declared_checks": {
            "ecc_change_max": 1e-5,
            "radiation_efficiency_change_max_percentage_points": 0.01,
            "peak_realized_gain_change_max_db": 0.05,
            "unweighted_ideal_selection_grid_fraction_at_or_above_0_dbi": 0.90,
            "radiation_efficiency_physical_upper_bound": 1.0,
            "one_percent_diagnostic_upper_bound": 1.01,
        },
        "two_point_fine_grid_delta_2p5_to_1deg": delta,
        "angular_power_convergence_pass": angular_power_convergence_pass,
        "unweighted_ideal_selection_grid_diagnostic_robust": (
            angular_grid_diagnostic_robust
        ),
        "power_balance_within_one_percent_diagnostic_all_ports": (
            one_percent_power_balance_diagnostic
        ),
        "power_balance_strictly_physical_all_ports": strict_power_balance,
        "absolute_gain_efficiency_eligible_for_claim": (
            angular_power_convergence_pass and strict_power_balance
        ),
        "selected_1deg_metrics": fine,
        "grids": rows,
        "interpretation": (
            "Angular quadrature is converged if the declared checks pass. "
            "A failed power-balance flag after angular convergence identifies "
            "a solve/boundary-level limitation rather than an angular-sampling "
            "limitation. The one-percent quantity is diagnostic only and cannot "
            "override the strict physical upper bound."
        ),
    }

    OUTPUT_JSON.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_CSV}")
    print(f"Angular power convergence pass: {angular_power_convergence_pass}")
    print(
        "Unweighted ideal-selection angular-grid diagnostic robust: "
        f"{angular_grid_diagnostic_robust}"
    )
    print(
        "Power balance within one-percent diagnostic: "
        f"{one_percent_power_balance_diagnostic}"
    )
    print(f"Power balance strictly physical: {strict_power_balance}")


if __name__ == "__main__":
    main()
