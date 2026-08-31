"""Build and solve the PTF-MIMO shielded four-port roof feedthrough.

This HFSS model characterizes the conducted passive network only.  It has two
short 50-ohm coaxial channels passing through an aluminium roof coupon.  Port
labels deliberately implement the polarization swap used by PTF-MIMO:

* donor port 1 connects to service port 4 (S41/S14), and
* donor port 2 connects to service port 3 (S32/S23).

The exterior and interior radiators are separate HFSS components.  Therefore
this file must not be presented as a monolithic installed-coach antenna solve.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
from typing import Any

import numpy as np
from ansys.aedt.core import Hfss


DESIGN_NAME = "VC_PTF_V4_FourPortFeedthrough"
SETUP_NAME = "Setup_PTF_V4"
SWEEP_NAME = "Sweep_n78"
START_GHZ = 3.3
CENTER_GHZ = 3.55
STOP_GHZ = 3.8
STEP_GHZ = 0.025


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent
        / "Velocity_Connect_PTF_V4_FourPort_Feedthrough.aedt",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--solve", action="store_true")
    parser.add_argument("--non-graphical", action="store_true")
    parser.add_argument("--cores", type=int, default=2)
    parser.add_argument("--aedt-version", default="2025.2")
    parser.add_argument(
        "--aedt-process-id",
        type=int,
        default=None,
        help="Attach to an already-running AEDT process instead of launching one.",
    )
    parser.add_argument(
        "--aedt-edition", choices=("student", "commercial"), default="student"
    )
    parser.add_argument("--channel-spacing-mm", type=float, default=40.0)
    parser.add_argument("--feedthrough-length-mm", type=float, default=30.0)
    parser.add_argument("--inner-radius-mm", type=float, default=0.50)
    parser.add_argument("--dielectric-radius-mm", type=float, default=1.675)
    parser.add_argument("--outer-radius-mm", type=float, default=2.00)
    parser.add_argument("--roof-x-mm", type=float, default=90.0)
    parser.add_argument("--roof-y-mm", type=float, default=45.0)
    parser.add_argument("--roof-thickness-mm", type=float, default=1.0)
    parser.add_argument("--maximum-passes", type=int, default=10)
    parser.add_argument("--max-delta-s", type=float, default=0.005)
    parser.add_argument("--percent-refinement", type=int, default=20)
    return parser.parse_args()


def _validate(args: argparse.Namespace) -> None:
    positive = (
        "channel_spacing_mm",
        "feedthrough_length_mm",
        "inner_radius_mm",
        "dielectric_radius_mm",
        "outer_radius_mm",
        "roof_x_mm",
        "roof_y_mm",
        "roof_thickness_mm",
    )
    for name in positive:
        value = float(getattr(args, name))
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and positive")
    if not (
        args.inner_radius_mm
        < args.dielectric_radius_mm
        < args.outer_radius_mm
    ):
        raise ValueError("coax radii must satisfy inner < dielectric < outer")
    if args.feedthrough_length_mm <= args.roof_thickness_mm:
        raise ValueError("feedthrough must extend beyond both roof faces")
    if args.channel_spacing_mm + 4.0 * args.outer_radius_mm > args.roof_x_mm:
        raise ValueError("roof_x_mm is too small for the two shielded channels")
    characteristic = 60.0 / math.sqrt(2.1) * math.log(
        args.dielectric_radius_mm / args.inner_radius_mm
    )
    if not 45.0 <= characteristic <= 55.0:
        raise ValueError(
            f"coax geometry gives approximately {characteristic:.2f} ohm; "
            "keep it within 45-55 ohm"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _solution_values(app: Hfss, expression: str) -> tuple[np.ndarray, np.ndarray]:
    solution = app.post.get_solution_data(
        expressions=expression,
        setup_sweep_name=f"{SETUP_NAME} : {SWEEP_NAME}",
    )
    if not solution:
        raise RuntimeError(f"HFSS returned no data for {expression}")
    frequencies = np.asarray(solution.primary_sweep_values, dtype=float)
    values = np.asarray(solution.data_real(expression), dtype=float) + 1j * np.asarray(
        solution.data_imag(expression), dtype=float
    )
    return frequencies, values


def _extract_s_matrix(
    app: Hfss, terminal_names: list[str]
) -> tuple[np.ndarray, np.ndarray]:
    frequency_axis: np.ndarray | None = None
    matrices: np.ndarray | None = None
    for row, output_terminal in enumerate(terminal_names):
        for column, input_terminal in enumerate(terminal_names):
            expression = f"S({output_terminal},{input_terminal})"
            frequencies, values = _solution_values(app, expression)
            if frequency_axis is None:
                frequency_axis = frequencies
                matrices = np.zeros(
                    (frequencies.size, len(terminal_names), len(terminal_names)),
                    dtype=complex,
                )
            elif not np.allclose(frequency_axis, frequencies, atol=1e-12):
                raise RuntimeError("S-parameter frequency axes are inconsistent")
            matrices[:, row, column] = values
    if frequency_axis is None or matrices is None:
        raise RuntimeError("empty S matrix")
    return frequency_axis, matrices


def _db(value: complex) -> float:
    return 20.0 * math.log10(max(abs(value), 1e-15))


def _summarize_network(
    frequencies_ghz: np.ndarray, matrices: np.ndarray
) -> dict[str, Any]:
    intended_pairs = {(3, 0), (0, 3), (2, 1), (1, 2)}
    return_losses = []
    intended = []
    unintended = []
    passivity = []
    reciprocity = []
    rows = []
    for frequency, matrix in zip(frequencies_ghz, matrices, strict=True):
        return_db = [_db(matrix[index, index]) for index in range(4)]
        intended_db = [_db(matrix[row, col]) for row, col in sorted(intended_pairs)]
        unintended_db = [
            _db(matrix[row, col])
            for row in range(4)
            for col in range(4)
            if row != col and (row, col) not in intended_pairs
        ]
        sigma_max = float(np.linalg.svd(matrix, compute_uv=False)[0])
        reciprocity_error = float(np.max(np.abs(matrix - matrix.T)))
        return_losses.extend(return_db)
        intended.extend(intended_db)
        unintended.extend(unintended_db)
        passivity.append(sigma_max)
        reciprocity.append(reciprocity_error)
        rows.append(
            {
                "frequency_ghz": float(frequency),
                "worst_return_loss_db": max(return_db),
                "worst_intended_insertion_db": min(intended_db),
                "worst_unintended_coupling_db": max(unintended_db),
                "sigma_max": sigma_max,
                "reciprocity_error": reciprocity_error,
            }
        )
    summary = {
        "port_order": ["D1_minus45", "D2_plus45", "S1_minus45", "S2_plus45"],
        "intended_transfers": ["S41/S14", "S32/S23"],
        "worst_return_loss_db": max(return_losses),
        "worst_intended_insertion_db": min(intended),
        "worst_unintended_coupling_db": max(unintended),
        "maximum_singular_value": max(passivity),
        "maximum_reciprocity_error": max(reciprocity),
        "gates": {
            "return_loss_le_minus_15_db": max(return_losses) <= -15.0,
            "intended_insertion_ge_minus_1p5_db": min(intended) >= -1.5,
            "unintended_coupling_le_minus_35_db": max(unintended) <= -35.0,
            "passivity_sigma_max_le_1p01": max(passivity) <= 1.01,
            "reciprocity_error_le_1e_minus_6": max(reciprocity) <= 1e-6,
        },
        "frequency_rows": rows,
    }
    summary["all_gates_pass"] = all(summary["gates"].values())
    return summary


def _write_matrix_csv(
    path: Path, frequencies_ghz: np.ndarray, matrices: np.ndarray
) -> None:
    fields = ["frequency_ghz"]
    for row in range(4):
        for column in range(4):
            fields.extend(
                [
                    f"s{row + 1}{column + 1}_real",
                    f"s{row + 1}{column + 1}_imag",
                    f"s{row + 1}{column + 1}_db",
                ]
            )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for frequency, matrix in zip(frequencies_ghz, matrices, strict=True):
            row_data: dict[str, float] = {"frequency_ghz": float(frequency)}
            for row in range(4):
                for column in range(4):
                    value = matrix[row, column]
                    prefix = f"s{row + 1}{column + 1}"
                    row_data[f"{prefix}_real"] = float(value.real)
                    row_data[f"{prefix}_imag"] = float(value.imag)
                    row_data[f"{prefix}_db"] = _db(value)
            writer.writerow(row_data)


def _create_channel(
    app: Hfss,
    *,
    center_x_mm: float,
    channel_name: str,
    top_port_name: str,
    bottom_port_name: str,
    args: argparse.Namespace,
) -> list[str]:
    half_length = args.feedthrough_length_mm / 2.0
    origin = [f"{center_x_mm:.12g}mm", "0mm", f"{-half_length:.12g}mm"]
    inner = app.modeler.create_cylinder(
        orientation="Z",
        origin=origin,
        radius=f"{args.inner_radius_mm:.12g}mm",
        height=f"{args.feedthrough_length_mm:.12g}mm",
        name=f"{channel_name}_Inner",
        material="copper",
    )
    dielectric = app.modeler.create_cylinder(
        orientation="Z",
        origin=origin,
        radius=f"{args.dielectric_radius_mm:.12g}mm",
        height=f"{args.feedthrough_length_mm:.12g}mm",
        name=f"{channel_name}_PTFE",
        material="VC_PTFE",
    )
    outer = app.modeler.create_cylinder(
        orientation="Z",
        origin=origin,
        radius=f"{args.outer_radius_mm:.12g}mm",
        height=f"{args.feedthrough_length_mm:.12g}mm",
        name=f"{channel_name}_Outer",
        material="copper",
    )
    outer_tool = app.modeler.create_cylinder(
        orientation="Z",
        origin=origin,
        radius=f"{args.dielectric_radius_mm:.12g}mm",
        height=f"{args.feedthrough_length_mm:.12g}mm",
        name=f"{channel_name}_OuterTool",
        material="vacuum",
    )
    if not all((inner, dielectric, outer, outer_tool)):
        raise RuntimeError(f"{channel_name} coax geometry was not created")
    if not app.modeler.subtract(outer, outer_tool, keep_originals=False):
        raise RuntimeError(f"{channel_name} outer-conductor subtraction failed")

    top_face = dielectric.top_face_z
    bottom_face = dielectric.bottom_face_z
    top_line = [
        [f"{center_x_mm:.12g}mm", "0mm", f"{half_length:.12g}mm"],
        [
            f"{center_x_mm + args.dielectric_radius_mm:.12g}mm",
            "0mm",
            f"{half_length:.12g}mm",
        ],
    ]
    bottom_line = [
        [f"{center_x_mm:.12g}mm", "0mm", f"{-half_length:.12g}mm"],
        [
            f"{center_x_mm + args.dielectric_radius_mm:.12g}mm",
            "0mm",
            f"{-half_length:.12g}mm",
        ],
    ]
    if not app.wave_port(
        assignment=top_face,
        reference=[inner.name, outer.name],
        integration_line=top_line,
        modes=1,
        impedance=50,
        name=top_port_name,
        renormalize=True,
        terminals_rename=True,
    ):
        raise RuntimeError(f"{top_port_name} was not created")
    if not app.wave_port(
        assignment=bottom_face,
        reference=[inner.name, outer.name],
        integration_line=bottom_line,
        modes=1,
        impedance=50,
        name=bottom_port_name,
        renormalize=True,
        terminals_rename=True,
    ):
        raise RuntimeError(f"{bottom_port_name} was not created")
    return [inner.name, dielectric.name, outer.name]


def build(args: argparse.Namespace) -> int:
    _validate(args)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = output.with_name(output.stem + "_manifest.json")
    validation_log = output.with_name(output.stem + "_validation.log")
    results_dir = output.parent / "results" / "ptf_v4_feedthrough" / output.stem
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"{output} exists; pass --overwrite explicitly")
    if args.overwrite:
        for target in (
            output,
            output.with_name(output.name + ".lock"),
            output.with_name(output.stem + ".aedtresults"),
            output.with_name(output.stem + ".pyaedt"),
            manifest_path,
            validation_log,
            results_dir,
        ):
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    results_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "status": "started",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(output),
        "design": DESIGN_NAME,
        "evidence_class": "generated",
        "scope": (
            "conducted four-port feedthrough only; exterior and interior "
            "radiators, connectors, cable bends, fasteners, and coach cabin "
            "are separate validation artifacts"
        ),
        "port_order": ["D1_minus45", "D2_plus45", "S1_minus45", "S2_plus45"],
        "intended_cross_connections": ["D1_to_S2 (S41)", "D2_to_S1 (S32)"],
        "parameters": vars(args) | {"output": str(output)},
        "solved": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    app: Hfss | None = None
    try:
        app = Hfss(
            project=str(output),
            design=DESIGN_NAME,
            solution_type="Terminal",
            version=args.aedt_version,
            non_graphical=args.non_graphical,
            new_desktop=args.aedt_process_id is None,
            close_on_exit=False,
            student_version=args.aedt_edition == "student",
            aedt_process_id=args.aedt_process_id,
        )
        app.modeler.model_units = "mm"
        ptfe = app.materials.add_material("VC_PTFE")
        ptfe.permittivity = 2.1
        ptfe.dielectric_loss_tangent = 0.0002

        roof = app.modeler.create_box(
            [
                f"{-args.roof_x_mm / 2.0:.12g}mm",
                f"{-args.roof_y_mm / 2.0:.12g}mm",
                f"{-args.roof_thickness_mm / 2.0:.12g}mm",
            ],
            [
                f"{args.roof_x_mm:.12g}mm",
                f"{args.roof_y_mm:.12g}mm",
                f"{args.roof_thickness_mm:.12g}mm",
            ],
            name="AluminiumRoofCoupon",
            material="aluminum",
        )
        if not roof:
            raise RuntimeError("roof coupon was not created")

        channel_centers = (
            -args.channel_spacing_mm / 2.0,
            args.channel_spacing_mm / 2.0,
        )
        for index, center in enumerate(channel_centers, start=1):
            hole = app.modeler.create_cylinder(
                orientation="Z",
                origin=[
                    f"{center:.12g}mm",
                    "0mm",
                    f"{-args.roof_thickness_mm:.12g}mm",
                ],
                radius=f"{args.outer_radius_mm + 0.10:.12g}mm",
                height=f"{2.0 * args.roof_thickness_mm:.12g}mm",
                name=f"RoofHoleTool{index}",
                material="vacuum",
            )
            if not hole or not app.modeler.subtract(roof, hole, keep_originals=False):
                raise RuntimeError(f"roof hole {index} subtraction failed")

        _create_channel(
            app,
            center_x_mm=channel_centers[0],
            channel_name="ChannelA_D1_to_S2",
            top_port_name="Port1_DonorMinus",
            bottom_port_name="Port4_ServicePlus",
            args=args,
        )
        _create_channel(
            app,
            center_x_mm=channel_centers[1],
            channel_name="ChannelB_D2_to_S1",
            top_port_name="Port2_DonorPlus",
            bottom_port_name="Port3_ServiceMinus",
            args=args,
        )

        setup = app.create_setup(
            name=SETUP_NAME,
            setup_type="HFSSDriven",
            Frequency=f"{CENTER_GHZ}GHz",
            MaximumPasses=args.maximum_passes,
            MinimumPasses=3,
            MinimumConvergedPasses=2,
            MaxDeltaS=args.max_delta_s,
            PercentRefinement=args.percent_refinement,
            BasisOrder=1,
            PortAccuracy=4,
        )
        if not setup:
            raise RuntimeError("four-port setup was not created")
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
            raise RuntimeError("n78 sweep was not created")

        validation_code = app.validate_simple(log_file=validation_log)
        manifest["validation_code"] = bool(validation_code)
        manifest["validation_log"] = str(validation_log)
        manifest["objects"] = sorted(app.modeler.object_names)
        manifest["boundaries"] = sorted(boundary.name for boundary in app.boundaries)
        manifest["ports"] = list(app.ports)
        if validation_code != 1:
            raise RuntimeError(f"HFSS validation failed; inspect {validation_log}")
        if not app.save_project(file_name=str(output), overwrite=True):
            raise RuntimeError("four-port project could not be saved")

        if args.solve:
            start = time.perf_counter()
            if not app.analyze_setup(
                SETUP_NAME,
                cores=args.cores,
                use_auto_settings=False,
                blocking=True,
            ):
                raise RuntimeError("four-port feedthrough solve did not complete")
            manifest["solve_elapsed_seconds"] = time.perf_counter() - start
            if not app.save_project(file_name=str(output), overwrite=True):
                raise RuntimeError("solved four-port project could not be saved")

            terminal_names = [
                "Port1_DonorMinus_T1",
                "Port2_DonorPlus_T1",
                "Port3_ServiceMinus_T1",
                "Port4_ServicePlus_T1",
            ]
            frequencies, matrices = _extract_s_matrix(app, terminal_names)
            matrix_csv = results_dir / "ptf_v4_s_matrix.csv"
            summary_json = results_dir / "ptf_v4_network_summary.json"
            _write_matrix_csv(matrix_csv, frequencies, matrices)
            summary = _summarize_network(frequencies, matrices)
            summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            manifest["network_summary"] = summary
            manifest["s_matrix_csv"] = str(matrix_csv)
            manifest["network_summary_json"] = str(summary_json)
            manifest["convergence_file"] = app.export_convergence(
                SETUP_NAME,
                output_file=str(results_dir / "ptf_v4_convergence.conv"),
            )
            manifest["mesh_file"] = app.export_mesh_stats(
                SETUP_NAME,
                output_file=str(results_dir / "ptf_v4_mesh.mstat"),
            )
            manifest["solved"] = True
            manifest["evidence_class"] = "simulated"

        manifest["status"] = "complete"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest["project_sha256"] = _sha256(output)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps(manifest.get("network_summary", {}), indent=2))
        print(f"Project: {output}")
        print(f"Manifest: {manifest_path}")
        return 0
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(manifest["error"], file=sys.stderr)
        print(f"Failure manifest: {manifest_path}", file=sys.stderr)
        return 1
    finally:
        if app is not None:
            app.release_desktop(close_projects=True, close_desktop=True)


if __name__ == "__main__":
    raise SystemExit(build(parse_args()))
