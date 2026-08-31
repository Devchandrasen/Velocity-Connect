"""Compare solved Velocity Connect n78 V2 dual-port HFSS candidates.

The script consumes the controlled solve manifests and their exported
frequency-domain diversity metrics.  It writes a compact CSV/JSON evidence
table and two figures:

* separation/material/boundary candidate comparison;
* full-band traces for the selected finite-conductivity PML candidate.

This is a post-processing utility.  It does not launch or modify HFSS.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results" / "n78_v2_dualport"
OUTPUT_CSV = RESULTS / "candidate_comparison.csv"
OUTPUT_JSON = RESULTS / "candidate_comparison.json"
OUTPUT_FIGURE = RESULTS / "candidate_comparison.png"
BEST_FIGURE = RESULTS / "best_candidate_band_metrics.png"

CANDIDATES = (
    "Velocity_Connect_n78_V2_DualPort_S60",
    "Velocity_Connect_n78_V2_DualPort_S75",
    "Velocity_Connect_n78_V2_DualPort_S130",
    "Velocity_Connect_n78_V2_DualPort_S150",
    "Velocity_Connect_n78_V2_DualPort_S150_Finite",
    "Velocity_Connect_n78_V2_DualPort_S150_Finite_PML",
    "Velocity_Connect_n78_V2_DualPort_S150_PowerQA_B25_B1",
)
EXPECTED_SELECTED_CANDIDATE = (
    "Velocity_Connect_n78_V2_DualPort_S150_PowerQA_B25_B1"
)


def _safe_dbi(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return 10.0 * math.log10(value)


def _load_manifest(candidate: str) -> dict:
    path = ROOT / f"{candidate}_manifest.json"
    with path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("status") != "complete" or not manifest.get("solved"):
        raise RuntimeError(f"Candidate is not a complete solve: {path}")
    return manifest


def _candidate_row(candidate: str, manifest: dict) -> dict:
    metrics = manifest["diversity_metrics"]
    antenna = manifest.get("antenna_parameters_center", [])
    gains = [
        item.get("peak_realized_gain_dbi")
        for item in antenna
        if item.get("peak_realized_gain_dbi") is not None
    ]
    physical = [
        bool(item.get("power_balance_numerically_physical"))
        for item in antenna
        if "power_balance_numerically_physical" in item
    ]
    finite = bool(manifest.get("finite_conductivity"))
    boundary = manifest.get("open_boundary") or "Radiation"
    solver_controls = manifest.get("solver_controls") or {}
    field_evidence = None
    field_evidence_path = RESULTS / candidate / "embedded_pattern_metrics_1deg.json"
    if not field_evidence_path.exists():
        field_evidence_path = (
            RESULTS / candidate / "embedded_pattern_metrics_2p5deg.json"
        )
    if not field_evidence_path.exists():
        field_evidence_path = (
            RESULTS / candidate / "embedded_pattern_metrics_v2_dualport.json"
        )
    if field_evidence_path.exists():
        with field_evidence_path.open("r", encoding="utf-8") as stream:
            field_payload = json.load(stream)
        field_evidence = field_payload.get(
            "embedded_pattern_metrics",
            field_payload,
        )
    field_ports = (field_evidence or {}).get("per_port", [])
    angular_diagnostic = (field_evidence or {}).get(
        "upper_horizon_selection_coverage",
        {},
    )
    passes = {
        "match": bool(metrics["all_s11_s22_at_or_below_minus_10_db"]),
        "isolation": bool(metrics["all_s12_s21_at_or_below_minus_20_db"]),
        "tarc": bool(metrics["all_tarc_at_or_below_minus_10_db"]),
        "ecc": (
            float(
                metrics["maximum_ecc_s_parameter"]["ecc_s_parameter"]
            )
            <= 0.05
        ),
        "ccl": (
            float(
                metrics["maximum_channel_capacity_loss"][
                    "channel_capacity_loss_bits_s_hz"
                ]
            )
            <= 0.4
        ),
        "solve_validation": bool(manifest.get("validation_code")),
    }
    return {
        "candidate": candidate,
        "separation_mm": manifest["parameters_mm"]["separation"],
        "ground_x_mm": manifest["parameters_mm"]["ground_x"],
        "ground_y_mm": manifest["parameters_mm"]["ground_y"],
        "finite_conductivity": finite,
        "open_boundary": boundary,
        "absorbing_boundary_mesh_mm": solver_controls.get(
            "absorbing_boundary_mesh_mm"
        ),
        "basis_order": solver_controls.get("basis_order"),
        "worst_s11_db": metrics["worst_s11"]["s11_db"],
        "worst_s22_db": metrics["worst_s22"]["s22_db"],
        "worst_isolation_db": metrics["worst_s12_isolation"]["s12_db"],
        "worst_tarc_db": metrics["worst_tarc"]["tarc_worst_phase_db"],
        "maximum_ecc_s_parameter": metrics["maximum_ecc_s_parameter"][
            "ecc_s_parameter"
        ],
        "minimum_diversity_gain_db": metrics["minimum_diversity_gain"][
            "diversity_gain_db"
        ],
        "maximum_ccl_bits_s_hz": metrics["maximum_channel_capacity_loss"][
            "channel_capacity_loss_bits_s_hz"
        ],
        # Legacy source key retained; this is an S-derived accepted-power
        # imbalance proxy, not field-integrated mean effective gain.
        "maximum_s_derived_accepted_power_imbalance_db": metrics[
            "maximum_meg_imbalance"
        ][
            "meg_imbalance_db"
        ],
        "minimum_center_peak_realized_gain_dbi_preliminary": min(gains)
        if gains
        else None,
        "center_power_balance_physical_all_ports": all(physical)
        if physical
        else None,
        "embedded_field_ecc_center": (
            field_evidence.get("embedded_field_ecc")
            if field_evidence
            else None
        ),
        "minimum_field_integrated_total_efficiency_center": (
            min(
                item["total_efficiency_far_field_integral_ratio"]
                for item in field_ports
            )
            if field_ports
            else None
        ),
        "maximum_field_integrated_radiation_efficiency_center": (
            max(
                item["radiation_efficiency_far_field_integral_ratio"]
                for item in field_ports
            )
            if field_ports
            else None
        ),
        "minimum_center_peak_realized_gain_dbi_field": (
            min(
                item["peak_realized_gain_far_field_integral_dbi"]
                for item in field_ports
            )
            if field_ports
            else None
        ),
        "unweighted_ideal_selection_fraction_at_or_above_0_dbi": (
            angular_diagnostic.get(
            "fraction_at_or_above_0_dbi"
            )
        ),
        "unweighted_ideal_selection_p10_realized_gain_dbi": (
            angular_diagnostic.get(
            "p10_realized_gain_dbi"
            )
        ),
        "field_power_balance_within_one_percent_diagnostic_all_ports": (
            all(
                0.0
                <= item["radiation_efficiency_far_field_integral_ratio"]
                <= 1.01
                and 0.0
                <= item["total_efficiency_far_field_integral_ratio"]
                <= 1.01
                for item in field_ports
            )
            if field_ports
            else None
        ),
        "field_power_balance_strictly_physical_all_ports": (
            all(
                0.0
                <= item["radiation_efficiency_far_field_integral_ratio"]
                <= 1.0 + 1e-9
                and 0.0
                <= item["total_efficiency_far_field_integral_ratio"]
                <= 1.0 + 1e-9
                for item in field_ports
            )
            if field_ports
            else None
        ),
        "passes_match_gate": passes["match"],
        "passes_isolation_gate": passes["isolation"],
        "passes_tarc_gate": passes["tarc"],
        "passes_ecc_s_gate": passes["ecc"],
        "passes_ccl_gate": passes["ccl"],
        "passes_solve_validation": passes["solve_validation"],
        "passes_all_s_derived_gates": all(passes.values()),
    }


def _select_candidate(rows: list[dict]) -> dict:
    eligible = [
        row
        for row in rows
        if row["passes_all_s_derived_gates"]
        and row["finite_conductivity"]
        and row["open_boundary"] == "PML"
        and row["absorbing_boundary_mesh_mm"] is not None
    ]
    if not eligible:
        raise RuntimeError(
            "No candidate passes the declared S-derived gates with finite "
            "conductivity, PML, and explicit boundary refinement."
        )
    selected = min(
        eligible,
        key=lambda row: (
            float(row["absorbing_boundary_mesh_mm"]),
            int(row["basis_order"]),
            str(row["candidate"]),
        ),
    )
    if selected["candidate"] != EXPECTED_SELECTED_CANDIDATE:
        raise RuntimeError(
            "Deterministic candidate selection changed: "
            f"{selected['candidate']}"
        )
    return selected


def _selected_verification(candidate: str) -> dict:
    result_dir = RESULTS / candidate
    s_matrix_path = result_dir / "s_matrix_v2_dualport.csv"
    maximum_singular_value = 0.0
    with s_matrix_path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            matrix = np.array(
                [
                    [
                        complex(float(row["s11_real"]), float(row["s11_imag"])),
                        complex(float(row["s12_real"]), float(row["s12_imag"])),
                    ],
                    [
                        complex(float(row["s21_real"]), float(row["s21_imag"])),
                        complex(float(row["s22_real"]), float(row["s22_imag"])),
                    ],
                ],
                dtype=complex,
            )
            maximum_singular_value = max(
                maximum_singular_value,
                float(np.linalg.svd(matrix, compute_uv=False)[0]),
            )
    sampled_passivity_pass = maximum_singular_value <= 1.0 + 1e-9

    convergence_path = result_dir / "convergence_v2_dualport.conv"
    convergence_text = convergence_path.read_text(encoding="utf-8")
    adaptive_convergence_pass = "Converged : Yes" in convergence_text

    tolerance_path = RESULTS / "tolerance_corner_summary.json"
    tolerance = json.loads(tolerance_path.read_text(encoding="utf-8"))
    tolerance_pass = bool(tolerance["all_cases_pass_s_parameter_gates"])
    nominal_projects = {
        item["project"]
        for item in tolerance["cases"]
        if item["case"] == "nominal_powerqa"
    }
    tolerance_binds_selected = nominal_projects == {candidate}

    verification = {
        "sampled_maximum_singular_value": maximum_singular_value,
        "sampled_passivity_pass": sampled_passivity_pass,
        "adaptive_convergence_pass": adaptive_convergence_pass,
        "tolerance_s_parameter_corners_pass": tolerance_pass,
        "tolerance_summary_binds_selected_candidate": tolerance_binds_selected,
    }
    if not all(
        (
            sampled_passivity_pass,
            adaptive_convergence_pass,
            tolerance_pass,
            tolerance_binds_selected,
        )
    ):
        raise RuntimeError(
            f"Selected candidate failed verification: {verification}"
        )
    return verification


def _write_table(
    rows: list[dict],
    selected: dict,
    selected_verification: dict,
) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "evidence_class": "simulated",
        "hard_gates": {
            "worst_s11_s22_db": -10.0,
            "worst_s12_s21_db": -20.0,
            "worst_phase_tarc_db": -10.0,
            "maximum_ecc_s_parameter": 0.05,
            "maximum_ccl_bits_s_hz": 0.4,
            "maximum_sampled_singular_value": 1.0,
        },
        "selection_rule": (
            "Among candidates passing match, isolation, TARC, ECC(S), CCL, "
            "and solve validation, require finite conductivity, PML, and an "
            "explicit boundary-mesh control; choose the smallest successful "
            "boundary seed, then lower basis order and lexical name."
        ),
        "selected_screening_candidate": selected["candidate"],
        "selected_verification": selected_verification,
        "absolute_pattern_quantity_exclusion": (
            "Absolute realized gain, radiation efficiency, and angular coverage "
            "are excluded from acceptance and publication claims because the "
            "selected 1-degree result violates the strict efficiency <= 1 "
            "physical bound. A one-percent proximity diagnostic is not a pass "
            "criterion."
        ),
        "candidates": rows,
    }
    with OUTPUT_JSON.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")


def _plot_comparison(rows: list[dict]) -> None:
    labels = []
    for row in rows:
        suffix = ""
        if row["finite_conductivity"]:
            suffix += "\nfinite"
        if row["open_boundary"] == "PML":
            suffix += "+PML"
        boundary_mesh = (
            row.get("candidate", "").split("PowerQA_B", maxsplit=1)[-1]
            if "PowerQA_B" in row.get("candidate", "")
            else ""
        )
        if boundary_mesh:
            suffix += f"\nQA {boundary_mesh}"
        labels.append(f'{row["separation_mm"]:.0f} mm{suffix}')

    x = range(len(rows))
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 8.0), constrained_layout=True)
    axes[0].plot(x, [r["worst_s11_db"] for r in rows], "o-", label="Worst S11")
    axes[0].plot(x, [r["worst_s22_db"] for r in rows], "s-", label="Worst S22")
    axes[0].plot(
        x,
        [r["worst_isolation_db"] for r in rows],
        "^-",
        label="Worst S12/S21",
    )
    axes[0].axhline(-10, color="#666666", linestyle="--", linewidth=1, label="Match gate")
    axes[0].axhline(
        -20,
        color="#9d3a3a",
        linestyle=":",
        linewidth=1.2,
        label="Isolation gate",
    )
    axes[0].set_ylabel("Worst-band magnitude (dB)")
    axes[0].set_title("Velocity Connect n78 V2 candidate screening")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(ncol=2)

    axes[1].plot(
        x,
        [r["worst_tarc_db"] for r in rows],
        "D-",
        color="#7b3294",
        label="Worst-phase TARC",
    )
    axes[1].axhline(-10, color="#666666", linestyle="--", linewidth=1, label="TARC gate")
    axes[1].set_ylabel("Worst-phase TARC (dB)")
    axes[1].set_xticks(list(x), labels)
    axes[1].grid(True, alpha=0.25)
    axes[1].legend()
    fig.savefig(OUTPUT_FIGURE, dpi=180)
    plt.close(fig)


def _plot_best_candidate(candidate: str) -> None:
    metrics_path = (
        RESULTS / candidate / "diversity_metrics_v2_dualport.json"
    )
    with metrics_path.open("r", encoding="utf-8") as stream:
        points = json.load(stream)["frequency_metrics"]

    frequency = [p["frequency_ghz"] for p in points]
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 8.0), sharex=True, constrained_layout=True)
    axes[0].plot(frequency, [p["s11_db"] for p in points], label="S11")
    axes[0].plot(frequency, [p["s22_db"] for p in points], label="S22")
    axes[0].plot(frequency, [p["s12_db"] for p in points], label="S12")
    axes[0].axhline(-10, color="#666666", linestyle="--", linewidth=1)
    axes[0].axhline(-20, color="#9d3a3a", linestyle=":", linewidth=1.2)
    axes[0].set_ylabel("Magnitude (dB)")
    axes[0].set_title("Selected finite-conductivity PML candidate: full n78 sweep")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(ncol=3)

    axes[1].plot(
        frequency,
        [p["tarc_worst_phase_db"] for p in points],
        color="#7b3294",
        label="Worst-phase TARC",
    )
    axes[1].axhline(-10, color="#666666", linestyle="--", linewidth=1)
    axes[1].set_xlim(3.3, 3.8)
    axes[1].set_xticks([3.3, 3.4, 3.5, 3.6, 3.7, 3.8])
    axes[1].set_xlabel("Frequency (GHz)")
    axes[1].set_ylabel("TARC (dB)")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend()
    fig.savefig(BEST_FIGURE, dpi=180)
    plt.close(fig)


def main() -> None:
    rows = [_candidate_row(name, _load_manifest(name)) for name in CANDIDATES]
    selected = _select_candidate(rows)
    selected_verification = _selected_verification(selected["candidate"])
    _write_table(rows, selected, selected_verification)
    _plot_comparison(rows)
    _plot_best_candidate(selected["candidate"])

    passing = [
        row["candidate"] for row in rows if row["passes_all_s_derived_gates"]
    ]
    print(f"Wrote {OUTPUT_CSV}")
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_FIGURE}")
    print(f"Wrote {BEST_FIGURE}")
    print(f"Candidates passing all S-derived gates: {len(passing)}")
    for candidate in passing:
        print(f"  - {candidate}")
    print(f"Deterministically selected: {selected['candidate']}")


if __name__ == "__main__":
    main()
