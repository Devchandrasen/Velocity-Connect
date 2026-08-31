"""Summarize installed-radome HFSS candidates without upgrading evidence claims."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results" / "n78_v3_installed"
PATTERN = "Velocity_Connect_n78_V3*_manifest.json"


def _nested(record: dict[str, Any], *keys: str):
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _mesh_and_delta(stem: str) -> tuple[int | None, float | None]:
    evidence = ROOT / "results" / "n78_v2_dualport" / stem
    mesh_file = evidence / "mesh_v2_dualport.mstat"
    convergence_file = evidence / "convergence_v2_dualport.conv"
    mesh_elements = None
    delta_s = None
    if mesh_file.is_file():
        match = re.search(
            r"Total number of mesh elements:\s*(\d+)",
            mesh_file.read_text(encoding="utf-8", errors="replace"),
        )
        if match:
            mesh_elements = int(match.group(1))
    if convergence_file.is_file():
        matches = re.findall(
            r"Current\s*:\s*([0-9.eE+-]+)",
            convergence_file.read_text(encoding="utf-8", errors="replace"),
        )
        if matches:
            delta_s = float(matches[-1])
    return mesh_elements, delta_s


def _row(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    diversity = manifest.get("diversity_metrics") or {}
    field = manifest.get("embedded_pattern_metrics") or {}
    per_port = field.get("per_port") or []
    stem = path.name.removesuffix("_manifest.json")
    mesh_elements, delta_s = _mesh_and_delta(stem)

    s11 = _nested(diversity, "worst_s11", "s11_db")
    s22 = _nested(diversity, "worst_s22", "s22_db")
    isolation = _nested(diversity, "worst_s12_isolation", "s12_db")
    tarc = _nested(diversity, "worst_tarc", "tarc_worst_phase_db")
    ecc_s = _nested(diversity, "maximum_ecc_s_parameter", "ecc_s_parameter")
    ccl = _nested(
        diversity,
        "maximum_channel_capacity_loss",
        "channel_capacity_loss_bits_s_hz",
    )
    ecc_field = field.get("embedded_field_ecc")
    coverage = _nested(
        field,
        "upper_horizon_selection_coverage",
        "fraction_at_or_above_0_dbi",
    )
    radiation_efficiencies = [
        port.get("radiation_efficiency_far_field_integral_ratio")
        for port in per_port
        if port.get("radiation_efficiency_far_field_integral_ratio") is not None
    ]
    gains = [
        port.get("peak_realized_gain_far_field_integral_dbi")
        for port in per_port
        if port.get("peak_realized_gain_far_field_integral_dbi") is not None
    ]
    solved = bool(manifest.get("solved")) and manifest.get("status") == "complete"
    network_gates = bool(
        solved
        and s11 is not None
        and s22 is not None
        and isolation is not None
        and tarc is not None
        and ecc_s is not None
        and ccl is not None
        and s11 <= -10.0
        and s22 <= -10.0
        and isolation <= -20.0
        and tarc <= -10.0
        and ecc_s <= 0.05
        and ccl <= 0.4
    )
    pattern_gates = bool(
        solved
        and ecc_field is not None
        and coverage is not None
        and ecc_field <= 0.05
        and coverage >= 0.90
    )
    power_gate = bool(
        solved
        and len(radiation_efficiencies) == 2
        and max(radiation_efficiencies) <= 1.01
    )
    installed = manifest.get("installed_environment") or {}
    return {
        "candidate": stem,
        "status": manifest.get("status"),
        "solved": solved,
        "aedt_version": _nested(manifest, "aedt_runtime", "version_requested"),
        "aedt_edition": _nested(manifest, "aedt_runtime", "edition_requested"),
        "open_boundary": manifest.get("open_boundary"),
        "roof_geometry": installed.get("roof_geometry"),
        "radome_layout": installed.get("radome_layout"),
        "radome_permittivity": installed.get("radome_permittivity"),
        "radome_loss_tangent": installed.get("radome_loss_tangent"),
        "radome_wall_mm": installed.get("radome_wall_mm"),
        "radome_air_gap_mm": installed.get("radome_air_gap_mm"),
        "separation_mm": _nested(manifest, "parameters_mm", "separation"),
        "mesh_elements": mesh_elements,
        "final_delta_s": delta_s,
        "worst_s11_db": s11,
        "worst_s22_db": s22,
        "worst_isolation_db": isolation,
        "worst_tarc_db": tarc,
        "max_ecc_s": ecc_s,
        "max_ccl_bits_s_hz": ccl,
        "embedded_field_ecc": ecc_field,
        "coverage_fraction_ge_0_dbi": coverage,
        "gain_port1_dbi": gains[0] if len(gains) > 0 else None,
        "gain_port2_dbi": gains[1] if len(gains) > 1 else None,
        "max_radiation_efficiency_ratio": (
            max(radiation_efficiencies) if radiation_efficiencies else None
        ),
        "network_gates_pass": network_gates,
        "pattern_gates_pass": pattern_gates,
        "power_gate_le_101_percent_pass": power_gate,
        "all_numerical_gates_pass": network_gates and pattern_gates and power_gate,
        "error": manifest.get("error"),
    }


def main() -> int:
    rows = [_row(path) for path in sorted(ROOT.glob(PATTERN))]
    RESULTS.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS / "installed_candidate_summary.csv"
    json_path = RESULTS / "installed_candidate_summary.json"
    if not rows:
        raise RuntimeError(f"No manifests matched {ROOT / PATTERN}")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    eligible_screening = [
        row
        for row in rows
        if row["open_boundary"] == "PML"
        and row["network_gates_pass"]
        and row["pattern_gates_pass"]
    ]
    selected = None
    if eligible_screening:
        selected = max(
            eligible_screening,
            key=lambda row: (
                row["worst_isolation_db"] is not None,
                -(row["max_ccl_bits_s_hz"] or 999.0),
                row["coverage_fraction_ge_0_dbi"] or 0.0,
            ),
        )["candidate"]
    summary = {
        "candidate_count": len(rows),
        "selected_installed_screening_candidate": selected,
        "selected_status": (
            "provisional_simulation_screening" if selected else "none"
        ),
        "publication_ready_candidate": next(
            (
                row["candidate"]
                for row in rows
                if row["all_numerical_gates_pass"]
                and row["roof_geometry"] == "cylindrical_crown"
            ),
            None,
        ),
        "selection_rule": (
            "PML solve passing network and embedded-pattern gates; this does "
            "not waive the <=101% power gate, curved-roof gate, or measurement."
        ),
        "rows": rows,
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
