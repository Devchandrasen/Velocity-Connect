"""Fail-closed audit of exported radiator powers; never renormalizes a result.

This checks necessary physical bounds and adaptive convergence, not a complete
energy balance: exported dielectric/conductor dissipation and an independent
field solution are still needed for that stronger conclusion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re


def audit(manifest: dict, convergence_text: str) -> dict:
    failures: list[str] = []
    rows: list[dict] = []
    if manifest.get("status") != "complete" or manifest.get("solved") is not True:
        failures.append("solver_not_complete")
    converged = bool(re.search(r"^Converged\s*:\s*Yes\s*$", convergence_text, re.M))
    if not converged:
        failures.append("adaptive_convergence_not_demonstrated")
    native = manifest.get("antenna_parameters_center", [])
    fields = manifest.get("embedded_pattern_metrics", {}).get("per_port", [])
    by_port = {str(row.get("source", "")).split("_T")[0]: row for row in fields}
    native_names = [str(row.get("active_terminal", "")).split("_T")[0] for row in native]
    if len(native) != 2 or set(native_names) != {"Port1", "Port2"} or set(by_port) != {"Port1", "Port2"}:
        failures.append("two_native_and_embedded_ports_required")
    for record in native:
        name = str(record.get("active_terminal", "unknown")).split("_T")[0]
        try:
            accepted = float(record["accepted_power_w"])
            incident = float(record["incident_power_w"])
            radiated = float(record["radiated_power_w"])
            far_field = float(by_port[name]["radiated_power_far_field_integral_w"])
            reported = float(record["radiation_efficiency_ratio"])
            values = (accepted, incident, radiated, far_field, reported)
            if not all(math.isfinite(x) for x in values):
                raise ValueError("nonfinite export")
            if accepted <= 0 or incident <= 0 or min(radiated, far_field) < 0:
                raise ValueError("invalid power")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            failures.append(f"{name}:invalid_or_missing_power:{exc}")
            continue
        native_ratio = radiated / accepted
        field_ratio = far_field / accepted
        eps = 1e-9  # Floating point guard, not an empirical efficiency tolerance.
        physical = (accepted <= incident * (1 + eps)
                    and native_ratio <= 1 + eps and field_ratio <= 1 + eps
                    and radiated / incident <= 1 + eps)
        consistent = math.isclose(reported, native_ratio, rel_tol=1e-6, abs_tol=1e-9)
        if not physical:
            failures.append(f"{name}:power_exceeds_passive_bound")
        if not consistent:
            failures.append(f"{name}:reported_ratio_disagrees_with_powers")
        rows.append({"port": name, "accepted_power_w": accepted,
                     "incident_power_w": incident, "radiated_power_w": radiated,
                     "radiated_field_integral_w": far_field,
                     "native_radiated_to_accepted": native_ratio,
                     "field_radiated_to_accepted": field_ratio,
                     "native_excess_percent": 100 * (native_ratio - 1),
                     "field_excess_percent": 100 * (field_ratio - 1),
                     "native_vs_field_difference_percent_of_accepted":
                         100 * (radiated - far_field) / accepted,
                     "necessary_power_bounds_pass": physical,
                     "reported_ratio_consistent": consistent})
    return {"schema_version": 1, "adaptive_converged": converged,
            "necessary_checks_pass": not failures, "failures": failures,
            "ports": rows, "values_clipped_or_renormalized": False,
            "full_energy_closure_demonstrated": False,
            "independent_solver_validation": False,
            "scope": "Necessary passive-power and adaptive checks only. Native and "
                     "far-field integration share one HFSS solution; losses are not "
                     "independently exported. Passing is not installed-path validation."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--convergence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    conv = args.convergence.read_bytes()
    result = audit(json.loads(raw), conv.decode("utf-8-sig"))
    result["inputs"] = [{"name": path.name, "sha256": hashlib.sha256(data).hexdigest()}
                        for path, data in [(args.manifest, raw), (args.convergence, conv)]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"necessary_checks_pass": result["necessary_checks_pass"],
                      "failures": result["failures"]}))
    return 0 if result["necessary_checks_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
