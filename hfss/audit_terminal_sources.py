"""Read-only same-solve audit of terminal excitation and field normalization.

The generic PyAEDT get_efields_data helper assumes modal ':1' / watt sources.
This diagnostic instead keeps terminal volts, excitation type and postprocessing
identical when obtaining both powers and complex fields. No geometry is solved,
no negative result is clipped and no source project is saved.

The sampled far-field integral is a same-solver diagnostic, not an independent
energy-closure test. It assumes the HFSS phi-outer/theta-inner Cartesian export
ordering; native powers are reported separately and never replaced by the
integral. Conductor and dielectric loss terms are not independently measured.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

from ansys.aedt.core import Hfss
import numpy as np
from scipy.integrate import simpson

from build_n78_v2_dualport import DESIGN_NAME, SETUP_NAME, FAR_FIELD_NAME, CENTER_GHZ


def extract(app, active, incident, post):
    inactive = "Port2_T1" if active == "Port1_T1" else "Port1_T1"
    if not app.edit_sources({active: ("1V", "0deg"), inactive: ("0V", "0deg")},
                            use_incident_voltage=incident,
                            include_port_post_processing=post):
        raise RuntimeError("Terminal source assignment failed")
    expressions = ["RadiatedPower", "AcceptedPower", "IncidentPower", "RadiationEfficiency",
                   "TotalEfficiency", "PeakDirectivity", "PeakGain", "PeakRealizedGain"]
    setup = f"{SETUP_NAME} : LastAdaptive"
    report = app.post.reports_by_category.antenna_parameters(expressions, setup, FAR_FIELD_NAME)
    report.variations = app.available_variations.nominal_values
    report.variations["Freq"] = [f"{CENTER_GHZ}GHz"]
    data = report.get_solution_data()
    if not data:
        raise RuntimeError("No antenna parameter data")
    values = {}
    for name in expressions:
        _, sequence = data.get_expression_data(name, formula="real")
        if len(sequence) != 1:
            raise RuntimeError(f"Expected one value for {name}")
        values[name] = float(sequence[0])
    # get_far_field_data does not edit source settings, unlike get_efields_data.
    fields = {}
    for name in ("rETheta", "rEPhi"):
        solution = app.post.get_far_field_data(expressions=name, setup_sweep_name=setup,
                                               domain=FAR_FIELD_NAME)
        raw = solution.nominal_variation
        theta = np.asarray(raw.GetSweepValues("Theta"), dtype=float)
        phi = np.asarray(raw.GetSweepValues("Phi"), dtype=float)
        real = np.asarray(raw.GetRealDataValues(name), dtype=float)
        imag = np.asarray(raw.GetImagDataValues(name), dtype=float)
        theta_unique, phi_unique = np.unique(theta), np.unique(phi)
        if real.size != theta_unique.size * phi_unique.size:
            raise RuntimeError("Field angular grid is not a full Cartesian sphere")
        fields[name] = (real + 1j * imag).reshape(phi_unique.size, theta_unique.size)
    if not (math.isclose(theta_unique[0], 0, abs_tol=1e-8) and
            math.isclose(theta_unique[-1], math.pi, abs_tol=1e-8) and
            math.isclose(phi_unique[-1] - phi_unique[0], 2*math.pi, abs_tol=1e-8)):
        raise RuntimeError("Full-sphere angular support required")
    intensity = (abs(fields["rETheta"])**2 + abs(fields["rEPhi"])**2) / (2*376.730313668)
    prad = float(simpson(simpson(intensity * np.sin(theta_unique)[None, :],
                                 x=theta_unique, axis=1), x=phi_unique))
    accepted = values["AcceptedPower"]
    if accepted <= 0 or not all(math.isfinite(x) for x in [*values.values(), prad]):
        raise RuntimeError("Invalid exported powers")
    ratio = prad/accepted
    return {"active_terminal": active, "source_unit": "V",
            "use_incident_voltage": incident, "include_port_post_processing": post,
            "powers_and_parameters": values, "radiated_field_integral_w": prad,
            "field_to_accepted_ratio": ratio,
            "necessary_power_bounds_pass": 0 <= ratio <= 1+1e-9 and
                0 <= values["RadiationEfficiency"] <= 1+1e-9,
            "theta_samples": int(theta_unique.size), "phi_samples": int(phi_unique.size)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    project = args.project.resolve()
    before = hashlib.sha256(project.read_bytes()).hexdigest()
    os.environ.setdefault("ANSYSEMSV_ROOT252", r"C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM")
    report = {"schema_version": 1, "project_name": project.name,
              "project_sha256_before": before, "same_solve_diagnostic_only": True,
              "independent_solver_validation": False, "results": []}
    app = None
    try:
        app = Hfss(project=str(project), design=DESIGN_NAME, solution_type="Terminal",
                   version="2025.2", non_graphical=True, new_desktop=True,
                   student_version=True, close_on_exit=False)
        for incident in (False, True):
            for post in (True, False):
                for active in ("Port1_T1", "Port2_T1"):
                    row = extract(app, active, incident, post)
                    report["results"].append(row)
                    print(json.dumps(row), flush=True)
        report["status"] = "complete"
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if app is not None:
            app.close_project(save=False)
            app.release_desktop(close_projects=False, close_desktop=True)
        report["project_sha256_after"] = hashlib.sha256(project.read_bytes()).hexdigest()
        report["source_project_unchanged"] = before == report["project_sha256_after"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")


if __name__ == "__main__":
    main()
