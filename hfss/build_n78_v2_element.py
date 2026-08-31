"""Build and solve a natively matched n78 tapered-monopole candidate.

This design is deliberately separate from the submitted-paper baseline.  It
is the single-element precursor to the dual-port Velocity Connect donor.  The
geometry uses a roughly quarter-wave, flared planar monopole over a realistic
laboratory roof coupon instead of repairing the electrically short baseline
with a lossy lumped matching network.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

from ansys.aedt.core import Hfss
from ansys.aedt.core.generic.constants import Plane

from build_n78_donor import AEDT_VERSION
from solve_n78_donor import _summarize_s11


PROJECT_NAME = "Velocity_Connect_n78_V2_Student.aedt"
DESIGN_NAME = "VC_n78_V2_Element"
SETUP_NAME = "Setup_V2"
SWEEP_NAME = "Sweep_V2"
FAR_FIELD_NAME = "FFSphere_V2"
RESULTS_FOLDER = "n78_v2_element"

START_GHZ = 3.3
CENTER_GHZ = 3.55
STOP_GHZ = 3.8
STEP_GHZ = 0.025

# Initial values are physics-led starting points, not an optimized release.
# The free-space quarter wavelength at 3.55 GHz is about 21.1 mm.
DEFAULT_PARAMETERS_MM = {
    "ground_x": 140.0,
    "ground_y": 100.0,
    "ground_t": 1.0,
    "height": 21.0,
    "top_w": 10.0,
    "base_w": 16.0,
    "neck_w": 3.5,
    "shoulder_h": 5.0,
    "feed_gap": 1.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Velocity Connect V2 tapered n78 donor element."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / PROJECT_NAME,
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--solve", action="store_true")
    parser.add_argument("--non-graphical", action="store_true")
    parser.add_argument("--cores", type=int, default=2)
    parser.add_argument(
        "--aedt-process-id",
        type=int,
        default=None,
        help="Attach to an existing AEDT Student gRPC process.",
    )
    for name, value in DEFAULT_PARAMETERS_MM.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=float, default=value)
    return parser.parse_args()


def _parameters(args: argparse.Namespace) -> dict[str, float]:
    return {
        name: float(getattr(args, name))
        for name in DEFAULT_PARAMETERS_MM
    }


def _validate_parameters(parameters: dict[str, float]) -> None:
    if not 16.0 <= parameters["height"] <= 28.0:
        raise ValueError("height must remain within the bounded 16-28 mm search.")
    if not 0.4 <= parameters["feed_gap"] <= 2.5:
        raise ValueError("feed_gap must remain within 0.4-2.5 mm.")
    if not 1.0 <= parameters["neck_w"] <= parameters["base_w"]:
        raise ValueError("neck_w must be positive and no wider than base_w.")
    if not 2.0 <= parameters["top_w"] <= 30.0:
        raise ValueError("top_w is outside the bounded prototype range.")
    if parameters["shoulder_h"] >= parameters["height"]:
        raise ValueError("shoulder_h must be below the blade height.")


def _json_value(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value


def _center_impedance(app: Hfss, terminal: str) -> dict[str, float]:
    expression = f"St({terminal},{terminal})"
    data = app.post.get_solution_data(
        expressions=expression,
        setup_sweep_name=f"{SETUP_NAME} : {SWEEP_NAME}",
        report_category="Terminal Solution Data",
        variations=app.available_variations.nominal_values,
    )
    if not data:
        raise RuntimeError(f"No complex terminal data was returned for {terminal}.")
    frequency, real = data.get_expression_data(expression, formula="real")
    _, imaginary = data.get_expression_data(expression, formula="imag")
    points = [
        (
            float(_json_value(freq)),
            complex(float(_json_value(r)), float(_json_value(i))),
        )
        for freq, r, i in zip(frequency, real, imaginary)
    ]
    if not points:
        raise RuntimeError("The complex terminal sweep was empty.")
    frequency_ghz, gamma = min(
        points,
        key=lambda point: abs(point[0] - CENTER_GHZ),
    )
    impedance = 50.0 * (1.0 + gamma) / (1.0 - gamma)
    return {
        "frequency_ghz": frequency_ghz,
        "gamma_magnitude": abs(gamma),
        "s11_db": 20.0 * math.log10(max(abs(gamma), 1e-15)),
        "resistance_ohm": impedance.real,
        "reactance_ohm": impedance.imag,
    }


def build_project(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"{output} exists; pass --overwrite explicitly.")

    parameters = _parameters(args)
    _validate_parameters(parameters)
    manifest_file = output.with_name(output.stem + "_element_manifest.json")
    validation_log = output.with_name(output.stem + "_element_validation.log")
    results_dir = output.parent / "results" / RESULTS_FOLDER
    results_dir.mkdir(parents=True, exist_ok=True)
    s11_csv = results_dir / "s11_v2_element.csv"
    manifest: dict[str, Any] = {
        "status": "started",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(output),
        "design": DESIGN_NAME,
        "geometry_family": "quarter-wave tapered planar monopole",
        "evidence_class": "generated",
        "frequency_ghz": {
            "start": START_GHZ,
            "center": CENTER_GHZ,
            "stop": STOP_GHZ,
            "step": STEP_GHZ,
        },
        "parameters_mm": parameters,
        "external_matching_network": False,
        "solved": False,
    }
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    app: Hfss | None = None
    try:
        app = Hfss(
            project=str(output),
            design=DESIGN_NAME,
            solution_type="Terminal",
            version=AEDT_VERSION,
            non_graphical=args.non_graphical,
            new_desktop=args.aedt_process_id is None,
            close_on_exit=False,
            student_version=True,
            aedt_process_id=args.aedt_process_id,
        )
        app.modeler.model_units = "mm"
        for name, value in parameters.items():
            app[name] = f"{value:.12g}mm"

        ground = app.modeler.create_box(
            origin=["-ground_x/2", "-ground_y/2", "-ground_t"],
            sizes=["ground_x", "ground_y", "ground_t"],
            name="RoofCoupon",
            material="pec",
        )
        if not ground:
            raise RuntimeError("Roof coupon geometry was not created.")

        blade_points = [
            ["-neck_w/2", "0mm", "feed_gap"],
            ["-base_w/2", "0mm", "shoulder_h"],
            ["-top_w/2", "0mm", "height"],
            ["top_w/2", "0mm", "height"],
            ["base_w/2", "0mm", "shoulder_h"],
            ["neck_w/2", "0mm", "feed_gap"],
        ]
        radiator = app.modeler.create_polyline(
            points=blade_points,
            cover_surface=True,
            close_surface=True,
            name="TaperedRadiator",
            material="pec",
        )
        if not radiator:
            raise RuntimeError("Tapered radiator geometry was not created.")
        radiator_boundary = app.assign_perfect_e(
            assignment=radiator.name,
            name="PerfE_TaperedRadiator",
        )
        if not radiator_boundary:
            raise RuntimeError("The tapered radiator PEC boundary was not assigned.")

        port_sheet = app.modeler.create_rectangle(
            orientation=Plane.ZX,
            origin=["-neck_w/2", "0mm", "0mm"],
            # Plane.ZX consumes sizes in local Z then X order.
            sizes=["feed_gap", "neck_w"],
            name="PortSheet1",
            is_covered=True,
        )
        if not port_sheet:
            raise RuntimeError("The explicit radiator-to-roof port sheet was not created.")
        port = app.lumped_port(
            assignment=port_sheet,
            reference=[ground.name],
            impedance=50,
            name="Port1",
            renormalize=True,
            terminals_rename=True,
        )
        if not port:
            raise RuntimeError("The radiator-to-roof lumped port was not created.")

        if not app.create_open_region(
            frequency=f"{START_GHZ}GHz",
            boundary="Radiation",
            apply_infinite_ground=False,
        ):
            raise RuntimeError("The open radiation region was not created.")

        setup = app.create_setup(
            name=SETUP_NAME,
            setup_type="HFSSDriven",
            Frequency=f"{CENTER_GHZ}GHz",
            MaximumPasses=12,
            MinimumPasses=2,
            MinimumConvergedPasses=2,
            MaxDeltaS=0.015,
        )
        if not setup:
            raise RuntimeError("The V2 adaptive setup was not created.")
        sweep = app.create_linear_step_sweep(
            setup=SETUP_NAME,
            unit="GHz",
            start_frequency=START_GHZ,
            stop_frequency=STOP_GHZ,
            step_size=STEP_GHZ,
            name=SWEEP_NAME,
            save_fields=False,
            save_rad_fields=False,
            sweep_type="Interpolating",
        )
        if not sweep:
            raise RuntimeError("The V2 n78 sweep was not created.")
        if not app.insert_infinite_sphere(
            definition="Theta-Phi",
            phi_start=0,
            phi_stop=360,
            phi_step=5,
            theta_start=0,
            theta_stop=180,
            theta_step=5,
            name=FAR_FIELD_NAME,
        ):
            raise RuntimeError("The V2 far-field sphere was not created.")

        validation_code = app.validate_simple(log_file=validation_log)
        manifest["validation_code"] = bool(validation_code)
        manifest["validation_log"] = str(validation_log)
        manifest["objects"] = sorted(app.modeler.object_names)
        manifest["boundaries"] = sorted(boundary.name for boundary in app.boundaries)
        manifest["ports"] = list(app.ports)
        if validation_code != 1:
            raise RuntimeError(f"HFSS validation failed; inspect {validation_log}.")

        if not app.save_project(file_name=str(output), overwrite=True):
            raise RuntimeError("HFSS could not save the V2 element project.")

        if args.solve:
            solve_start = time.perf_counter()
            if not app.analyze_setup(
                SETUP_NAME,
                cores=args.cores,
                use_auto_settings=False,
                blocking=True,
            ):
                raise RuntimeError("The V2 element solve did not complete.")
            manifest["solve_elapsed_seconds"] = time.perf_counter() - solve_start
            if not app.save_project(file_name=str(output), overwrite=True):
                raise RuntimeError("The solved V2 project could not be saved.")

            expression = app.get_traces_for_plot(
                get_self_terms=True,
                get_mutual_terms=False,
            )[0]
            solution_data = app.post.get_solution_data(
                expressions=expression,
                setup_sweep_name=f"{SETUP_NAME} : {SWEEP_NAME}",
            )
            if not solution_data:
                raise RuntimeError("The V2 solve returned no S11 sweep.")
            if not solution_data.export_data_to_csv(str(s11_csv), delimiter=","):
                raise RuntimeError("The V2 S11 CSV export failed.")
            terminal_names = [
                boundary.name
                for boundary in app.boundaries
                if boundary.name.startswith("Port1") and boundary.name != "Port1"
            ]
            if not terminal_names:
                raise RuntimeError("The V2 terminal name could not be identified.")
            manifest["s11_summary"] = _summarize_s11(solution_data, expression)
            manifest["center_impedance"] = _center_impedance(
                app,
                terminal_names[0],
            )
            manifest["s11_csv"] = str(s11_csv)
            manifest["evidence_class"] = "simulated"
            manifest["solved"] = True

        manifest["status"] = "complete"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Project: {output}")
        print(f"Manifest: {manifest_file}")
        if args.solve:
            print(json.dumps(manifest["s11_summary"], indent=2))
            print(json.dumps(manifest["center_impedance"], indent=2))
        return 0
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(manifest["error"], file=sys.stderr)
        print(f"Failure manifest: {manifest_file}", file=sys.stderr)
        return 1
    finally:
        if app is not None:
            app.release_desktop(
                close_projects=True,
                close_desktop=args.aedt_process_id is None,
            )


if __name__ == "__main__":
    raise SystemExit(build_project(parse_args()))
