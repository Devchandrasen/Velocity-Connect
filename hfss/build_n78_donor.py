"""Build the Velocity Connect n78 donor antenna in AEDT Student.

The default action creates and validates the HFSS project but does not solve it.
Use ``--solve`` only after inspecting the geometry, port, open region, and setup.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

# The Student installer did not register the variable PyAEDT uses for version
# discovery on this workstation, so expose the verified official install to
# this process without changing global Windows settings.
AEDT_STUDENT_ROOT = Path(
    r"C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM"
)
if AEDT_STUDENT_ROOT.is_dir():
    os.environ.setdefault("ANSYSEMSV_ROOT252", str(AEDT_STUDENT_ROOT))

from ansys.aedt.core import Hfss
import ansys.aedt.core.desktop as aedt_desktop
from ansys.aedt.core.generic.general_methods import active_sessions
from ansys.aedt.toolkits.antenna.backend.antenna_models.monopole import BladeAntenna


AEDT_VERSION = "2025.2"
PROJECT_NAME = "Velocity_Connect_n78_Student.aedt"
DESIGN_NAME = "VC_Donor_n78"
ANTENNA_NAME = "VC_Donor_Blade"
SETUP_NAME = "Setup_n78"
SWEEP_NAME = "Sweep_n78"
FAR_FIELD_NAME = "FFSphere_n78"

CENTER_GHZ = 3.5
START_GHZ = 3.3
STOP_GHZ = 3.8
STEP_GHZ = 0.01


def _student_grpc_session_active(port: int, machine: str | None = None) -> bool:
    """Detect local Student gRPC sessions for PyAEDT 1.3.0.

    PyAEDT 1.3.0 checks ``active_sessions()`` with its commercial-edition
    default while launching AEDT Student.  The Student server is therefore
    listening but is incorrectly treated as absent until the launch timeout.
    This project is local-only, so query the Student executable explicitly.
    """

    del machine
    return port in active_sessions(student_version=True).values()


# Apply the narrow Student-edition detection workaround before Desktop starts.
aedt_desktop.is_grpc_session_active = _student_grpc_session_active


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the Velocity Connect parameterized n78 donor antenna."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / PROJECT_NAME,
        help="Destination .aedt file.",
    )
    parser.add_argument(
        "--solve",
        action="store_true",
        help="Run Setup_n78 after model generation and validation.",
    )
    parser.add_argument(
        "--non-graphical",
        action="store_true",
        help="Run AEDT without its graphical interface.",
    )
    parser.add_argument(
        "--aedt-process-id",
        type=int,
        default=None,
        help="Attach to an already running AEDT Student process instead of opening another.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output project.",
    )
    return parser.parse_args()


def _parameter_manifest(antenna: BladeAntenna) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in vars(antenna.synthesis_parameters).items():
        if hasattr(value, "value"):
            values[key] = value.value
    return dict(sorted(values.items()))


def build_project(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.overwrite:
        raise FileExistsError(
            f"{output} already exists. Use --overwrite only after preserving needed results."
        )

    validation_log = output.with_name(output.stem + "_validation.log")
    manifest_file = output.with_name(output.stem + "_manifest.json")
    app: Hfss | None = None
    manifest: dict[str, Any] = {
        "status": "started",
        "project": str(output),
        "design": DESIGN_NAME,
        "aedt_version_requested": AEDT_VERSION,
        "aedt_process_id": args.aedt_process_id,
        "student_version": True,
        "antenna_family": "BladeAntenna",
        "frequency_ghz": {
            "start": START_GHZ,
            "center": CENTER_GHZ,
            "stop": STOP_GHZ,
            "step": STEP_GHZ,
        },
        "reference_impedance_ohm": 50,
        "solved": False,
    }

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

        antenna = BladeAntenna(
            app,
            name=ANTENNA_NAME,
            frequency=CENTER_GHZ,
            frequency_unit="GHz",
            length_unit="mm",
            material="pec",
        )
        if not antenna.model_hfss():
            raise RuntimeError("The blade antenna geometry was not created.")

        # Use the bottom of n78 so the radiation clearance is not undersized.
        if not app.create_open_region(
            frequency=f"{START_GHZ}GHz",
            boundary="Radiation",
            apply_infinite_ground=False,
        ):
            raise RuntimeError("The open radiation region was not created.")

        if not antenna.setup_hfss():
            raise RuntimeError("The 50-ohm terminal/lumped-port setup failed.")

        setup = app.create_setup(
            name=SETUP_NAME,
            setup_type="HFSSDriven",
            Frequency=f"{CENTER_GHZ}GHz",
            MaximumPasses=8,
            MinimumPasses=2,
            MinimumConvergedPasses=2,
            MaxDeltaS=0.02,
        )
        if not setup:
            raise RuntimeError("The adaptive HFSS setup was not created.")

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
            raise RuntimeError("The n78 frequency sweep was not created.")

        far_field = app.insert_infinite_sphere(
            definition="Theta-Phi",
            phi_start=0,
            phi_stop=360,
            phi_step=5,
            theta_start=0,
            theta_stop=180,
            theta_step=5,
            name=FAR_FIELD_NAME,
        )
        if not far_field:
            raise RuntimeError("The far-field sphere was not created.")

        validation_code = app.validate_simple(log_file=validation_log)
        manifest["validation_code"] = validation_code
        manifest["validation_log"] = str(validation_log)
        manifest["model_parameters_mm"] = _parameter_manifest(antenna)
        manifest["objects"] = sorted(app.modeler.object_names)
        manifest["boundaries"] = sorted(boundary.name for boundary in app.boundaries)
        manifest["setups"] = sorted(app.setup_names)
        manifest["sweeps"] = sorted(app.setup_sweeps_names)

        if validation_code != 1:
            raise RuntimeError(
                f"HFSS validation failed; inspect {validation_log} before solving."
            )

        if not app.save_project(file_name=str(output), overwrite=True):
            raise RuntimeError(f"HFSS could not save {output}.")

        if args.solve:
            if not app.analyze_setup(SETUP_NAME):
                raise RuntimeError("HFSS solve did not complete successfully.")
            manifest["solved"] = True
            if not app.save_project(file_name=str(output), overwrite=True):
                raise RuntimeError("HFSS solved but could not save the updated project.")

        manifest["status"] = "complete"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Created: {output}")
        print(f"Validation: {validation_log}")
        print(f"Manifest: {manifest_file}")
        print(f"Solved: {manifest['solved']}")
        return 0
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(manifest["error"], file=sys.stderr)
        print(f"Failure manifest: {manifest_file}", file=sys.stderr)
        return 1
    finally:
        if app is not None:
            # Leave AEDT and the generated project open for visual inspection.
            app.release_desktop(close_projects=False, close_desktop=False)


if __name__ == "__main__":
    raise SystemExit(build_project(parse_args()))
