"""Summarize the solved nominal and fabrication-corner V2 candidates."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results" / "n78_v2_dualport"
CASES = (
    ("nominal_powerqa", "Velocity_Connect_n78_V2_DualPort_S150_PowerQA_B25_B1"),
    ("short_blade_wide_gap", "Velocity_Connect_n78_V2_DualPort_Tol_H20p5_G1p2"),
    ("tall_blade_narrow_gap", "Velocity_Connect_n78_V2_DualPort_Tol_H21p5_G0p8"),
)


def main() -> None:
    rows = []
    for label, stem in CASES:
        manifest_path = ROOT / f"{stem}_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "complete" or not manifest.get("solved"):
            raise RuntimeError(f"Tolerance case is not a complete solve: {manifest_path}")
        metrics = manifest["diversity_metrics"]
        row = {
            "case": label,
            "project": stem,
            "height_mm": manifest["parameters_mm"]["height"],
            "feed_gap_mm": manifest["parameters_mm"]["feed_gap"],
            "worst_s11_db": metrics["worst_s11"]["s11_db"],
            "worst_s22_db": metrics["worst_s22"]["s22_db"],
            "worst_isolation_db": metrics["worst_s12_isolation"]["s12_db"],
            "worst_tarc_db": metrics["worst_tarc"]["tarc_worst_phase_db"],
            "match_margin_db": min(
                -10.0 - metrics["worst_s11"]["s11_db"],
                -10.0 - metrics["worst_s22"]["s22_db"],
            ),
            "isolation_margin_db": -20.0
            - metrics["worst_s12_isolation"]["s12_db"],
            "tarc_margin_db": -10.0 - metrics["worst_tarc"]["tarc_worst_phase_db"],
            "passes_all_s_parameter_gates": all(
                (
                    metrics["all_s11_s22_at_or_below_minus_10_db"],
                    metrics["all_s12_s21_at_or_below_minus_20_db"],
                    metrics["all_tarc_at_or_below_minus_10_db"],
                )
            ),
        }
        rows.append(row)

    csv_path = RESULTS / "tolerance_corner_summary.csv"
    json_path = RESULTS / "tolerance_corner_summary.json"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "evidence_class": "simulated two-corner screening",
        "declared_fabrication_window_screened": {
            "blade_height_mm": "21.0 +/- 0.5",
            "feed_gap_mm": "1.0 +/- 0.2",
        },
        "screening_only": True,
        "not_a_statistical_yield_claim": True,
        "limiting_case": min(rows, key=lambda item: item["tarc_margin_db"])["case"],
        "all_cases_pass_s_parameter_gates": all(
            item["passes_all_s_parameter_gates"] for item in rows
        ),
        "caveat": (
            "Corner runs use the screening mesh and establish S-parameter "
            "robustness only. They do not validate gain, efficiency, radome, "
            "connector, roof, environmental, or Monte Carlo yield."
        ),
        "cases": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
