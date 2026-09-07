"""Replay the retained HFSS power discrepancy without running Ansys.

Exit zero means the recorded diagnostic was reproduced, not physical acceptance.
Byte integrity is checked separately by scripts/verify_source_manifest.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

try:
    from .export_power_budget_revision06 import field_rows
    from .power_balance import assess_power_budget, integrate_far_field
except ImportError:
    from export_power_budget_revision06 import field_rows
    from power_balance import assess_power_budget, integrate_far_field


def replay(directory: Path) -> dict:
    results = []
    for port in ("Port1_T1", "Port2_T1"):
        terms = json.loads((directory / f"{port}_power_terms.json").read_text())
        native = json.loads((directory / f"{port}_native.json").read_text())
        field_path = directory / f"{port}_complex_fields.csv"
        if hashlib.sha256(field_path.read_bytes()).hexdigest() != terms["fields_sha256"]:
            raise ValueError(f"{port}: field export hash mismatch")
        if native["context"] != terms["context"] or native["powers"] != terms["native"]:
            raise ValueError(f"{port}: native query and recorded context disagree")
        rows, unit = field_rows(field_path)
        integral = integrate_far_field(rows, angle_unit=unit)
        for key in ("radiated_power_w", "trapezoid_power_w"):
            if not math.isclose(integral[key], terms["coordinate_field_integral"][key], rel_tol=1e-10):
                raise ValueError(f"{port}: recorded field integration cannot be reproduced")
        powers = native["powers"]
        context = native["context"]
        budget = assess_power_budget(dict(
            incident_w=powers["IncidentPower"], accepted_w=powers["AcceptedPower"],
            native_radiated_w=powers["RadiatedPower"],
            field_radiated_w=integral["radiated_power_w"],
            conductor_loss_w=sum(terms["surface_loss_primary_w"].values()),
            dielectric_loss_w=sum(terms["volume_loss_w"].values()),
            native_context=context, field_context=context, loss_context=context))
        for key in ("native_efficiency", "field_efficiency", "relative_input_closure_residual",
                    "relative_native_field_difference"):
            if not math.isclose(budget[key], terms["primary_surface_budget"][key], rel_tol=1e-10):
                raise ValueError(f"{port}: recorded power budget cannot be reproduced")
        results.append({"port": port, "budget": budget, "field_integral": integral})
    return {"status": "recorded_diagnostic_reproduced", "solver_executed": False,
            "physical_acceptance": False, "results": results,
            "limitations": ["Replays exports; does not independently solve Maxwell equations.",
                            "Conductor sheet-side accounting remains subject to expert review.",
                            "Numerical power imbalance is retained, not corrected or clipped."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[1] /
                        "fixtures" / "hfss" / "power_budget_revision06")
    args = parser.parse_args()
    print(json.dumps(replay(args.input), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
