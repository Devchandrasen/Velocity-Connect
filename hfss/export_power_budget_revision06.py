"""Read a solved HFSS terminal model; export independently queried power terms.

No solve, geometry/material change, clipping, or source-project save is performed.
Defaults to 4 GiB available RAM; a 1.5 GiB read-only admission is supported only
with the separate process-memory guard. Failure leaves
an explicit report, never a fabricated efficiency or a zero for a missing term.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path


def available_memory_gib():
    if os.name != "nt":
        values = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        return float(values["MemAvailable"].split()[0]) / 1024**2
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in
            ("total_physical", "available_physical", "total_page", "available_page",
             "total_virtual", "available_virtual", "available_extended")]
    state = MemoryStatus()
    state.length = ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise OSError("Cannot determine available memory")
    return state.available_physical / 1024**3


def checked(value):
    if isinstance(value, bool) or value is None:
        raise RuntimeError("HFSS export returned no numeric value")
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError("HFSS export returned nonfinite value")
    return result


def field_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        def column(prefix):
            found = [c for c in columns if c == prefix or c.startswith(prefix + " [")
                     or c.startswith(prefix + " (Real) [")]
            if len(found) != 1:
                raise ValueError(f"One explicit field column required: {prefix}")
            return found[0]
        t, p = column("Theta"), column("Phi")
        unit = t.split("[")[-1].rstrip("]")
        if unit not in {"deg", "rad"} or p.split("[")[-1].rstrip("]") != unit:
            raise ValueError("Explicit common angular units required")
        names = {key: column(prefix) for key, prefix in (
            ("etheta_re", "re(rETheta)"), ("etheta_im", "im(rETheta)"),
            ("ephi_re", "re(rEPhi)"), ("ephi_im", "im(rEPhi)"))}
        scales = {"V": 1.0, "mV": 1e-3, "uV": 1e-6}
        factors = {}
        for label in names.values():
            field_unit = label.split("[")[-1].rstrip("]")
            if field_unit not in scales:
                raise ValueError("rE phasors require explicit supported voltage units")
            factors[label] = scales[field_unit]
        result = []
        for row in reader:
            for label in names.values():
                if " (Real) " in label:
                    imaginary = label.replace(" (Real) ", " (Imag) ")
                    if imaginary not in columns or checked(row[imaginary]) != 0:
                        raise ValueError("A real/imag field expression has an unexpected complex remainder")
            result.append({"theta": checked(row[t]), "phi": checked(row[p]),
                           **{key: checked(row[label]) * factors[label] for key, label in names.items()}})
    return result, unit


def signed_flux(app, obj, destination, solution, frequency):
    field = app.post.ofieldsreporter
    field.CalcStack("clear")
    field.EnterQty("Poynting")
    field.CalcOp("Real")
    field.EnterSurf(obj)
    field.CalcOp("NormalComponent")
    field.CalcOp("Integrate")
    variation = []
    for name, value in app.available_variations.nominal_variation(dependent_params=False).items():
        if app.variable_manager.variables[name].sweep:
            variation.extend([name + ":=", value])
    variation.extend(["Freq:=", frequency, "Phase:=", "0deg"])
    field.CalculatorWrite(str(destination), ["Solution:=", solution], variation)
    value = checked(destination.read_text().splitlines()[-1].strip())
    field.CalcStack("clear")
    return value


def export(app, destination):
    from build_n78_v2_dualport import SETUP_NAME, FAR_FIELD_NAME, CENTER_GHZ
    from power_balance import integrate_far_field, assess_power_budget
    solution, freq = f"{SETUP_NAME} : LastAdaptive", f"{CENTER_GHZ}GHz"
    conductors = ("RoofCoupon", "Radiator1_SlantMinus", "Radiator2_SlantPlus")
    dielectrics = ("RadomeShell_Port1", "RadomeShell_Port2")
    for obj in (*conductors, *dielectrics, "RadiatingSurface"):
        if obj not in app.modeler.object_names:
            raise ValueError(f"Unexpected model: required object {obj} absent")
    results = []
    for port in ("Port1_T1", "Port2_T1"):
        other = "Port2_T1" if port == "Port1_T1" else "Port1_T1"
        if not app.edit_sources({port: ("1V", "0deg"), other: ("0V", "0deg")},
                                use_incident_voltage=True, include_port_post_processing=False):
            raise RuntimeError("Explicit terminal incident-voltage excitation failed")
        context = f"{port}:1Vincident:other0V:postprocessing=false:{freq}"
        quantities = ["IncidentPower", "AcceptedPower", "RadiatedPower", "RadiationEfficiency"]
        report = app.post.reports_by_category.antenna_parameters(quantities, solution, FAR_FIELD_NAME)
        report.variations = {**app.available_variations.nominal_values, "Freq": [freq]}
        native = report.get_solution_data()
        if not native:
            raise RuntimeError("Native antenna powers unavailable")
        powers = {}
        for name in quantities:
            _, values = native.get_expression_data(name, formula="real")
            if len(values) != 1:
                raise ValueError("Exactly one adaptive-frequency power required")
            powers[name] = checked(values[0])
        with (destination / f"{port}_native.json").open("x", encoding="utf-8") as handle:
            json.dump({"context": context, "powers": powers}, handle, indent=2, allow_nan=False)
        fields = app.post.get_solution_data(
            expressions=["re(rETheta)", "im(rETheta)", "re(rEPhi)", "im(rEPhi)"], setup_sweep_name=solution,
            report_category="Far Fields", context=FAR_FIELD_NAME,
            primary_sweep_variable="Theta",
            variations={**app.available_variations.nominal_values,
                        "Freq": [freq], "Theta": ["All"], "Phi": ["All"]})
        fields_path = destination / f"{port}_complex_fields.csv"
        if not fields or not fields.export_data_to_csv(str(fields_path), delimiter=","):
            raise RuntimeError("Coordinate-labelled field export failed")
        rows, unit = field_rows(fields_path)
        integral = integrate_far_field(rows, angle_unit=unit)
        surface, adjacent, volume = {}, {}, {}
        for obj in conductors:
            for side, target in ((False, surface), (True, adjacent)):
                target[obj] = checked(app.post.get_scalar_field_value(
                    "SurfaceLossDensity", "Integrate", solution=solution,
                    intrinsics={"Freq": freq, "Phase": "0deg"}, object_name=obj,
                    object_type="surface", adjacent_side=side))
        for obj in dielectrics:
            volume[obj] = checked(app.post.get_scalar_field_value(
                "VolumeLossDensity", "Integrate", solution=solution,
                intrinsics={"Freq": freq, "Phase": "0deg"}, object_name=obj, object_type="volume"))
        flux = signed_flux(app, "RadiatingSurface", destination / f"{port}_boundary_flux.fld", solution, freq)
        record = dict(incident_w=powers["IncidentPower"], accepted_w=powers["AcceptedPower"],
                      native_radiated_w=powers["RadiatedPower"], field_radiated_w=integral["radiated_power_w"],
                      conductor_loss_w=sum(surface.values()), dielectric_loss_w=sum(volume.values()),
                      native_context=context, field_context=context, loss_context=context)
        result = {"port": port, "context": context, "native": powers, "coordinate_field_integral": integral,
                  "surface_loss_primary_w": surface, "surface_loss_adjacent_w": adjacent,
                  "volume_loss_w": volume, "signed_boundary_flux_w": flux,
                  "primary_surface_budget": assess_power_budget(record),
                  "surface_side_accounting_requires_review": True,
                  "fields_sha256": hashlib.sha256(fields_path.read_bytes()).hexdigest()}
        results.append(result)
        with (destination / f"{port}_power_terms.json").open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
        print(json.dumps({"port": port, "native": powers, "budget": result["primary_surface_budget"]}), flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--minimum-free-memory-gib", type=float, choices=(1.5, 4.0), default=4.0)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.mkdir(parents=True)
    initial_hash = hashlib.sha256(project.read_bytes()).hexdigest()
    report = dict(project=str(project), project_sha256_before=initial_hash,
                  available_memory_gib=available_memory_gib(), required_free_memory_gib=args.minimum_free_memory_gib,
                  solved_in_this_run=False, efficiency_corrected=False, results=[])
    app = None
    try:
        if report["available_memory_gib"] < args.minimum_free_memory_gib:
            report["status"] = "resource_admission_denied"
            return 3
        from ansys.aedt.core import Hfss
        from build_n78_v2_dualport import DESIGN_NAME
        os.environ.setdefault("ANSYSEMSV_ROOT252", r"C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM")
        app = Hfss(project=str(project), design=DESIGN_NAME, solution_type="Terminal",
                   version="2025.2", student_version=True, non_graphical=True,
                   new_desktop=True, close_on_exit=False)
        report["results"] = export(app, args.out)
        report["status"] = "diagnostic_export_completed_not_physical_acceptance"
        return 0
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        cleanup_errors = []
        if app is not None:
            try:
                app.close_project(save=False)
            except Exception as exc:
                cleanup_errors.append(f"close_project: {type(exc).__name__}: {exc}")
            try:
                app.release_desktop(close_projects=False, close_desktop=True)
            except Exception as exc:
                cleanup_errors.append(f"release_desktop: {type(exc).__name__}: {exc}")
        report["cleanup_errors"] = cleanup_errors
        report["project_sha256_after"] = hashlib.sha256(project.read_bytes()).hexdigest()
        report["source_project_unchanged"] = report["project_sha256_after"] == initial_hash
        with (args.out / "power_budget_report.json").open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
        print(json.dumps({key: report[key] for key in ("status", "available_memory_gib", "source_project_unchanged")}), flush=True)
        if cleanup_errors or not report["source_project_unchanged"]:
            raise RuntimeError("Diagnostic cleanup or source-integrity check failed; inspect the retained report")


if __name__ == "__main__":
    raise SystemExit(main())
