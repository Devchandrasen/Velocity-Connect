"""Build and evaluate the Velocity Connect V2 dual-port n78 donor.

The design uses two natively matched, quarter-wave tapered monopoles on a
common roof coupon.  The elements are spatially separated and placed in
orthogonal vertical planes.  This makes S12/S21 and TARC direct screening
metrics.  ECC, diversity gain, channel-capacity loss, and the accepted-power
imbalance reported below are S-parameter-derived screening proxies; they are
not substitutes for installed-platform pattern or efficiency validation.

All diversity metrics in this script are simulation screening metrics.  ECC
is initially calculated from the complex S matrix; final publication evidence
must use the complex embedded far-field integral and measured S parameters.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sys
import time
from typing import Any

from ansys.aedt.core import Hfss

from build_n78_donor import AEDT_VERSION


PROJECT_NAME = "Velocity_Connect_n78_V2_DualPort_Student.aedt"
DESIGN_NAME = "VC_n78_V2_DualPort"
SETUP_NAME = "Setup_V2_Dual"
SWEEP_NAME = "Sweep_V2_Dual"
FAR_FIELD_NAME = "FFSphere_V2_Dual"
RESULTS_FOLDER = "n78_v2_dualport"

START_GHZ = 3.3
CENTER_GHZ = 3.55
STOP_GHZ = 3.8
STEP_GHZ = 0.025

DEFAULT_PARAMETERS_MM = {
    "ground_x": 180.0,
    "ground_y": 120.0,
    "ground_t": 1.0,
    "height": 21.0,
    "top_w": 10.0,
    "base_w": 16.0,
    "neck_w": 3.5,
    "shoulder_h": 5.0,
    "feed_gap": 1.0,
    "blade_t": 0.5,
    "separation": 60.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and solve the Velocity Connect V2 dual-port donor."
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
    parser.add_argument("--aedt-process-id", type=int, default=None)
    parser.add_argument(
        "--aedt-version",
        default=AEDT_VERSION,
        help=(
            "AEDT release used to regenerate the project, for example 2025.2 "
            "or 2024.1. Projects are not opened backward across AEDT releases."
        ),
    )
    parser.add_argument(
        "--aedt-edition",
        choices=("student", "commercial"),
        default="student",
        help="Select the installed AEDT license family.",
    )
    parser.add_argument("--maximum-passes", type=int, default=14)
    parser.add_argument("--minimum-converged-passes", type=int, default=2)
    parser.add_argument("--max-delta-s", type=float, default=0.01)
    parser.add_argument("--percent-refinement", type=int, default=30)
    parser.add_argument(
        "--basis-order",
        type=int,
        choices=(-1, 1, 2),
        default=1,
        help="-1 mixed order, 1 first order, 2 second order.",
    )
    parser.add_argument(
        "--absorbing-boundary-mesh-mm",
        type=float,
        default=None,
        help=(
            "Optional maximum edge length seeded on the inner absorbing-region "
            "faces to improve radiated-power accuracy."
        ),
    )
    parser.add_argument(
        "--far-field-step-deg",
        type=float,
        default=5.0,
        help="Theta/Phi sampling used for embedded-pattern integration.",
    )
    parser.add_argument(
        "--finite-conductivity",
        action="store_true",
        help="Use aluminium roof and finite-thickness copper blade losses.",
    )
    parser.add_argument(
        "--open-boundary",
        choices=("Radiation", "PML"),
        default="Radiation",
        help="Outer-region boundary used for the solve.",
    )
    parser.add_argument(
        "--roof-radius-mm",
        type=float,
        default=None,
        help=(
            "Optional transverse roof radius. When supplied, replace the flat "
            "coupon with a cylindrical crown tangent to z=0."
        ),
    )
    parser.add_argument(
        "--radome",
        action="store_true",
        help="Add a hollow, open-bottom dielectric radome over both elements.",
    )
    parser.add_argument(
        "--radome-layout",
        choices=("common", "split"),
        default="common",
        help=(
            "Use one shared elongated cover or two physically separated "
            "single-element pods."
        ),
    )
    parser.add_argument("--radome-permittivity", type=float, default=2.9)
    parser.add_argument("--radome-loss-tangent", type=float, default=0.008)
    parser.add_argument("--radome-wall-mm", type=float, default=2.0)
    parser.add_argument("--radome-air-gap-mm", type=float, default=8.0)
    parser.add_argument(
        "--polarization-layout",
        choices=("orthogonal-plane", "dual-slant"),
        default="orthogonal-plane",
        help=(
            "Use the legacy orthogonal blade planes or a true dual-slant "
            "pair whose radiator axes are +angle and -angle from vertical."
        ),
    )
    parser.add_argument(
        "--slant-angle-deg",
        type=float,
        default=45.0,
        help=(
            "Absolute dual-slant angle from vertical. At 45 degrees the "
            "two radiator axes are orthogonal."
        ),
    )
    for name, value in DEFAULT_PARAMETERS_MM.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=float, default=value)
    return parser.parse_args()


def _parameters(args: argparse.Namespace) -> dict[str, float]:
    return {name: float(getattr(args, name)) for name in DEFAULT_PARAMETERS_MM}


def _validate_parameters(parameters: dict[str, float]) -> None:
    if not 16.0 <= parameters["height"] <= 28.0:
        raise ValueError("height must remain within 16-28 mm.")
    if not 35.0 <= parameters["separation"] <= 200.0:
        raise ValueError("separation must remain within 35-200 mm.")
    if parameters["separation"] + parameters["base_w"] > parameters["ground_x"]:
        raise ValueError("The selected element separation does not fit the roof coupon.")
    if not 0.4 <= parameters["feed_gap"] <= 2.5:
        raise ValueError("feed_gap must remain within 0.4-2.5 mm.")


def _validate_solver_controls(args: argparse.Namespace) -> None:
    if not 3 <= args.maximum_passes <= 30:
        raise ValueError("maximum_passes must remain within 3-30.")
    if not 1 <= args.minimum_converged_passes <= 5:
        raise ValueError("minimum_converged_passes must remain within 1-5.")
    if args.minimum_converged_passes >= args.maximum_passes:
        raise ValueError(
            "minimum_converged_passes must be smaller than maximum_passes."
        )
    if not 0.001 <= args.max_delta_s <= 0.03:
        raise ValueError("max_delta_s must remain within 0.001-0.03.")
    if not 10 <= args.percent_refinement <= 50:
        raise ValueError("percent_refinement must remain within 10-50.")
    if (
        args.absorbing_boundary_mesh_mm is not None
        and not 5.0 <= args.absorbing_boundary_mesh_mm <= 40.0
    ):
        raise ValueError("absorbing_boundary_mesh_mm must remain within 5-40 mm.")
    if not 1.0 <= args.far_field_step_deg <= 10.0:
        raise ValueError("far_field_step_deg must remain within 1-10 degrees.")
    if args.roof_radius_mm is not None:
        if args.roof_radius_mm <= args.ground_y / 2.0:
            raise ValueError("roof_radius_mm must exceed half the roof width.")
        if args.roof_radius_mm < 500.0:
            raise ValueError("roof_radius_mm must be at least 500 mm.")
    if not 1.8 <= args.radome_permittivity <= 4.5:
        raise ValueError("radome_permittivity must remain within 1.8-4.5.")
    if not 0.0 <= args.radome_loss_tangent <= 0.05:
        raise ValueError("radome_loss_tangent must remain within 0-0.05.")
    if not 0.8 <= args.radome_wall_mm <= 5.0:
        raise ValueError("radome_wall_mm must remain within 0.8-5 mm.")
    if not 3.0 <= args.radome_air_gap_mm <= 25.0:
        raise ValueError("radome_air_gap_mm must remain within 3-25 mm.")
    if not 20.0 <= args.slant_angle_deg <= 60.0:
        raise ValueError("slant_angle_deg must remain within 20-60 degrees.")


def _json_value(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value


def _db(magnitude: float) -> float:
    return 20.0 * math.log10(max(float(magnitude), 1e-15))


def _db_power(linear: float) -> float:
    return 10.0 * math.log10(max(float(linear), 1e-15))


def _create_radiator_xz(
    app: Hfss,
    center_x: str,
    name: str,
    port_name: str,
    ground_name: str,
    finite_conductivity: bool,
) -> None:
    points = [
        [f"{center_x}-neck_w/2", "0mm", "feed_gap"],
        [f"{center_x}-base_w/2", "0mm", "shoulder_h"],
        [f"{center_x}-top_w/2", "0mm", "height"],
        [f"{center_x}+top_w/2", "0mm", "height"],
        [f"{center_x}+base_w/2", "0mm", "shoulder_h"],
        [f"{center_x}+neck_w/2", "0mm", "feed_gap"],
    ]
    radiator = app.modeler.create_polyline(
        points=points,
        cover_surface=True,
        close_surface=True,
        name=name,
        material="copper" if finite_conductivity else "pec",
    )
    if not radiator:
        raise RuntimeError(f"{name} was not created.")
    if finite_conductivity:
        conductor_boundary = app.assign_finite_conductivity(
            assignment=radiator.name,
            material="copper",
            use_thickness=True,
            thickness="blade_t",
            roughness="2um",
            is_two_side=True,
            name=f"FiniteCond_{name}",
        )
    else:
        conductor_boundary = app.assign_perfect_e(
            radiator.name,
            name=f"PerfE_{name}",
        )
    if not conductor_boundary:
        raise RuntimeError(f"{name} conductor boundary was not created.")
    port_sheet = app.modeler.create_polyline(
        points=[
            [f"{center_x}-neck_w/2", "0mm", "0mm"],
            [f"{center_x}-neck_w/2", "0mm", "feed_gap"],
            [f"{center_x}+neck_w/2", "0mm", "feed_gap"],
            [f"{center_x}+neck_w/2", "0mm", "0mm"],
        ],
        cover_surface=True,
        close_surface=True,
        name=f"{port_name}_Sheet",
    )
    if not port_sheet:
        raise RuntimeError(f"{port_name} sheet was not created.")
    if not app.lumped_port(
        assignment=port_sheet,
        reference=[ground_name],
        impedance=50,
        name=port_name,
        renormalize=True,
        terminals_rename=True,
    ):
        raise RuntimeError(f"{port_name} was not created.")


def _create_radiator_yz(
    app: Hfss,
    center_x: str,
    name: str,
    port_name: str,
    ground_name: str,
    finite_conductivity: bool,
) -> None:
    points = [
        [center_x, "-neck_w/2", "feed_gap"],
        [center_x, "-base_w/2", "shoulder_h"],
        [center_x, "-top_w/2", "height"],
        [center_x, "top_w/2", "height"],
        [center_x, "base_w/2", "shoulder_h"],
        [center_x, "neck_w/2", "feed_gap"],
    ]
    radiator = app.modeler.create_polyline(
        points=points,
        cover_surface=True,
        close_surface=True,
        name=name,
        material="copper" if finite_conductivity else "pec",
    )
    if not radiator:
        raise RuntimeError(f"{name} was not created.")
    if finite_conductivity:
        conductor_boundary = app.assign_finite_conductivity(
            assignment=radiator.name,
            material="copper",
            use_thickness=True,
            thickness="blade_t",
            roughness="2um",
            is_two_side=True,
            name=f"FiniteCond_{name}",
        )
    else:
        conductor_boundary = app.assign_perfect_e(
            radiator.name,
            name=f"PerfE_{name}",
        )
    if not conductor_boundary:
        raise RuntimeError(f"{name} conductor boundary was not created.")
    port_sheet = app.modeler.create_polyline(
        points=[
            [center_x, "-neck_w/2", "0mm"],
            [center_x, "-neck_w/2", "feed_gap"],
            [center_x, "neck_w/2", "feed_gap"],
            [center_x, "neck_w/2", "0mm"],
        ],
        cover_surface=True,
        close_surface=True,
        name=f"{port_name}_Sheet",
    )
    if not port_sheet:
        raise RuntimeError(f"{port_name} sheet was not created.")
    if not app.lumped_port(
        assignment=port_sheet,
        reference=[ground_name],
        impedance=50,
        name=port_name,
        renormalize=True,
        terminals_rename=True,
    ):
        raise RuntimeError(f"{port_name} was not created.")


def _create_slanted_radiator(
    app: Hfss,
    parameters: dict[str, float],
    center_x_mm: float,
    slant_angle_deg: float,
    name: str,
    port_name: str,
    ground_name: str,
    finite_conductivity: bool,
) -> None:
    """Create one tapered blade with a controlled slant-polarization axis.

    The blade axis lies in the x-z plane while its physical width lies along
    y. A +45/-45 degree pair therefore has orthogonal axis vectors. The
    idealized lumped-port plane remains at the roof reference plane so the
    geometry can be compared directly with the legacy candidate.
    """

    theta = math.radians(float(slant_angle_deg))
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    feed_gap = parameters["feed_gap"]

    def point(distance_mm: float, half_width_mm: float, sign: float) -> list[str]:
        x_mm = center_x_mm + distance_mm * sin_theta
        z_mm = feed_gap + distance_mm * cos_theta
        return [
            f"{x_mm:.12g}mm",
            f"{sign * half_width_mm:.12g}mm",
            f"{z_mm:.12g}mm",
        ]

    points = [
        point(0.0, parameters["neck_w"] / 2.0, -1.0),
        point(parameters["shoulder_h"], parameters["base_w"] / 2.0, -1.0),
        point(parameters["height"], parameters["top_w"] / 2.0, -1.0),
        point(parameters["height"], parameters["top_w"] / 2.0, 1.0),
        point(parameters["shoulder_h"], parameters["base_w"] / 2.0, 1.0),
        point(0.0, parameters["neck_w"] / 2.0, 1.0),
    ]
    radiator = app.modeler.create_polyline(
        points=points,
        cover_surface=True,
        close_surface=True,
        name=name,
        material="copper" if finite_conductivity else "pec",
    )
    if not radiator:
        raise RuntimeError(f"{name} was not created.")
    if finite_conductivity:
        conductor_boundary = app.assign_finite_conductivity(
            assignment=radiator.name,
            material="copper",
            use_thickness=True,
            thickness="blade_t",
            roughness="2um",
            is_two_side=True,
            name=f"FiniteCond_{name}",
        )
    else:
        conductor_boundary = app.assign_perfect_e(
            radiator.name,
            name=f"PerfE_{name}",
        )
    if not conductor_boundary:
        raise RuntimeError(f"{name} conductor boundary was not created.")

    neck_half = parameters["neck_w"] / 2.0
    port_sheet = app.modeler.create_polyline(
        points=[
            [f"{center_x_mm:.12g}mm", f"{-neck_half:.12g}mm", "0mm"],
            [
                f"{center_x_mm:.12g}mm",
                f"{-neck_half:.12g}mm",
                f"{feed_gap:.12g}mm",
            ],
            [
                f"{center_x_mm:.12g}mm",
                f"{neck_half:.12g}mm",
                f"{feed_gap:.12g}mm",
            ],
            [f"{center_x_mm:.12g}mm", f"{neck_half:.12g}mm", "0mm"],
        ],
        cover_surface=True,
        close_surface=True,
        name=f"{port_name}_Sheet",
    )
    if not port_sheet:
        raise RuntimeError(f"{port_name} sheet was not created.")
    if not app.lumped_port(
        assignment=port_sheet,
        reference=[ground_name],
        impedance=50,
        name=port_name,
        renormalize=True,
        terminals_rename=True,
    ):
        raise RuntimeError(f"{port_name} was not created.")


def _create_roof(
    app: Hfss,
    parameters: dict[str, float],
    finite_conductivity: bool,
    roof_radius_mm: float | None,
):
    material = "aluminum" if finite_conductivity else "pec"
    if roof_radius_mm is None:
        roof = app.modeler.create_box(
            ["-ground_x/2", "-ground_y/2", "-ground_t"],
            ["ground_x", "ground_y", "ground_t"],
            name="RoofCoupon",
            material=material,
        )
        if not roof:
            raise RuntimeError("The flat dual-port roof coupon was not created.")
        return roof

    radius = float(roof_radius_mm)
    thickness = parameters["ground_t"]
    half_width = parameters["ground_y"] / 2.0
    sag = radius - math.sqrt(radius * radius - half_width * half_width)
    outer = app.modeler.create_cylinder(
        orientation="X",
        origin=["-ground_x/2", "0mm", f"{-radius:.12g}mm"],
        radius=f"{radius:.12g}mm",
        height="ground_x",
        name="RoofOuterCylinder",
        material=material,
    )
    inner = app.modeler.create_cylinder(
        orientation="X",
        origin=["-ground_x/2", "0mm", f"{-radius:.12g}mm"],
        radius=f"{radius - thickness:.12g}mm",
        height="ground_x",
        name="RoofInnerCylinder",
        material="vacuum",
    )
    if not outer or not inner:
        raise RuntimeError("The curved roof cylinders were not created.")
    if not app.modeler.subtract(outer, inner, keep_originals=False):
        raise RuntimeError("The curved roof shell subtraction failed.")

    trim_margin = 0.5
    trim_bottom = -(sag + thickness + trim_margin)
    trim_height = sag + thickness + 2.0 * trim_margin
    trim = app.modeler.create_box(
        [
            f"{-parameters['ground_x'] / 2.0 - trim_margin:.12g}mm",
            "-ground_y/2",
            f"{trim_bottom:.12g}mm",
        ],
        [
            f"{parameters['ground_x'] + 2.0 * trim_margin:.12g}mm",
            "ground_y",
            f"{trim_height:.12g}mm",
        ],
        name="RoofCrownTrim",
        material="vacuum",
    )
    if not trim:
        raise RuntimeError("The curved roof trim volume was not created.")
    if not app.modeler.intersect([outer, trim], keep_originals=False):
        raise RuntimeError("The curved roof crown intersection failed.")
    outer.name = "RoofCoupon"
    return outer


def _create_radome(
    app: Hfss,
    parameters: dict[str, float],
    permittivity: float,
    loss_tangent: float,
    wall_mm: float,
    air_gap_mm: float,
    layout: str,
):
    material_name = "VC_LowLossRadome"
    material = app.materials.add_material(material_name)
    if not material:
        raise RuntimeError("The radome dielectric material was not created.")
    material.permittivity = float(permittivity)
    material.dielectric_loss_tangent = float(loss_tangent)

    outer_z = parameters["height"] + air_gap_mm + wall_mm

    def create_shell(center_x_mm: float, outer_x: float, name: str):
        outer_y = parameters["base_w"] + 2.0 * (air_gap_mm + wall_mm)
        outer = app.modeler.create_box(
            [
                f"{center_x_mm - outer_x / 2.0:.12g}mm",
                f"{-outer_y / 2.0:.12g}mm",
                "0mm",
            ],
            [
                f"{outer_x:.12g}mm",
                f"{outer_y:.12g}mm",
                f"{outer_z:.12g}mm",
            ],
            name=name,
            material=material_name,
        )
        inner = app.modeler.create_box(
            [
                f"{center_x_mm - outer_x / 2.0 + wall_mm:.12g}mm",
                f"{-outer_y / 2.0 + wall_mm:.12g}mm",
                "0mm",
            ],
            [
                f"{outer_x - 2.0 * wall_mm:.12g}mm",
                f"{outer_y - 2.0 * wall_mm:.12g}mm",
                f"{outer_z - wall_mm:.12g}mm",
            ],
            name=f"{name}_InteriorTool",
            material="vacuum",
        )
        if not outer or not inner:
            raise RuntimeError(f"{name} volumes were not created.")
        if not app.modeler.subtract(outer, inner, keep_originals=False):
            raise RuntimeError(f"{name} open-bottom subtraction failed.")
        return outer

    if layout == "split":
        pod_x = parameters["base_w"] + 2.0 * (air_gap_mm + wall_mm)
        return [
            create_shell(
                -parameters["separation"] / 2.0,
                pod_x,
                "RadomeShell_Port1",
            ),
            create_shell(
                parameters["separation"] / 2.0,
                pod_x,
                "RadomeShell_Port2",
            ),
        ]
    common_x = (
        parameters["separation"]
        + parameters["base_w"]
        + 2.0 * (air_gap_mm + wall_mm)
    )
    return [create_shell(0.0, common_x, "RadomeShell")]


def _complex_s_matrix(
    app: Hfss,
    terminal_1: str,
    terminal_2: str,
) -> list[dict[str, Any]]:
    expressions = {
        "s11": f"St({terminal_1},{terminal_1})",
        "s12": f"St({terminal_1},{terminal_2})",
        "s21": f"St({terminal_2},{terminal_1})",
        "s22": f"St({terminal_2},{terminal_2})",
    }
    data = app.post.get_solution_data(
        expressions=list(expressions.values()),
        setup_sweep_name=f"{SETUP_NAME} : {SWEEP_NAME}",
        report_category="Terminal Solution Data",
        variations=app.available_variations.nominal_values,
    )
    if not data:
        raise RuntimeError("The complex dual-port S matrix could not be retrieved.")

    by_name: dict[str, list[tuple[float, complex]]] = {}
    for key, expression in expressions.items():
        frequency, real = data.get_expression_data(expression, formula="real")
        _, imaginary = data.get_expression_data(expression, formula="imag")
        by_name[key] = [
            (
                float(_json_value(freq)),
                complex(float(_json_value(r)), float(_json_value(i))),
            )
            for freq, r, i in zip(frequency, real, imaginary)
        ]
    frequencies = [point[0] for point in by_name["s11"]]
    if not frequencies:
        raise RuntimeError("The complex dual-port S matrix was empty.")
    rows: list[dict[str, Any]] = []
    for index, frequency in enumerate(frequencies):
        rows.append(
            {
                "frequency_ghz": frequency,
                **{key: by_name[key][index][1] for key in expressions},
            }
        )
    return rows


def _diversity_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    phase_values = range(0, 360, 5)
    frequency_metrics: list[dict[str, float]] = []
    for row in rows:
        s11 = row["s11"]
        s12 = row["s12"]
        s21 = row["s21"]
        s22 = row["s22"]

        tarc_values: list[tuple[int, float]] = []
        for phase_deg in phase_values:
            phase = complex(
                math.cos(math.radians(phase_deg)),
                math.sin(math.radians(phase_deg)),
            )
            b1 = (s11 + s12 * phase) / math.sqrt(2.0)
            b2 = (s21 + s22 * phase) / math.sqrt(2.0)
            tarc_values.append((phase_deg, math.sqrt(abs(b1) ** 2 + abs(b2) ** 2)))
        worst_phase, worst_tarc = max(tarc_values, key=lambda item: item[1])

        alpha_11 = max(1.0 - abs(s11) ** 2 - abs(s21) ** 2, 1e-15)
        alpha_22 = max(1.0 - abs(s22) ** 2 - abs(s12) ** 2, 1e-15)
        cross = s11.conjugate() * s12 + s21.conjugate() * s22
        ecc = min(max(abs(cross) ** 2 / (alpha_11 * alpha_22), 0.0), 1.0)
        diversity_gain_db = 10.0 * math.sqrt(max(1.0 - ecc**2, 0.0))
        determinant = max(alpha_11 * alpha_22 - abs(cross) ** 2, 1e-15)
        channel_capacity_loss = -math.log2(determinant)
        meg_1 = 0.5 * alpha_11
        meg_2 = 0.5 * alpha_22
        frequency_metrics.append(
            {
                "frequency_ghz": float(row["frequency_ghz"]),
                "s11_db": _db(abs(s11)),
                "s22_db": _db(abs(s22)),
                "s12_db": _db(abs(s12)),
                "s21_db": _db(abs(s21)),
                "tarc_worst_phase_db": _db(worst_tarc),
                "tarc_worst_phase_deg": float(worst_phase),
                "ecc_s_parameter": ecc,
                "diversity_gain_db": diversity_gain_db,
                "channel_capacity_loss_bits_s_hz": channel_capacity_loss,
                "meg_1_db": _db_power(meg_1),
                "meg_2_db": _db_power(meg_2),
                "meg_imbalance_db": abs(_db_power(meg_1) - _db_power(meg_2)),
            }
        )

    def maximum(key: str) -> dict[str, float]:
        return max(frequency_metrics, key=lambda item: item[key])

    def minimum(key: str) -> dict[str, float]:
        return min(frequency_metrics, key=lambda item: item[key])

    return {
        "frequency_metrics": frequency_metrics,
        "band_summary": {
            "worst_s11": maximum("s11_db"),
            "worst_s22": maximum("s22_db"),
            "worst_s12_isolation": maximum("s12_db"),
            "worst_s21_isolation": maximum("s21_db"),
            "worst_tarc": maximum("tarc_worst_phase_db"),
            "maximum_ecc_s_parameter": maximum("ecc_s_parameter"),
            "minimum_diversity_gain": minimum("diversity_gain_db"),
            "maximum_channel_capacity_loss": maximum(
                "channel_capacity_loss_bits_s_hz"
            ),
            "maximum_meg_imbalance": maximum("meg_imbalance_db"),
            "maximum_reciprocity_error": max(
                abs(row["s12"] - row["s21"]) for row in rows
            ),
            "all_s11_s22_at_or_below_minus_10_db": all(
                item["s11_db"] <= -10.0 and item["s22_db"] <= -10.0
                for item in frequency_metrics
            ),
            "all_s12_s21_at_or_below_minus_20_db": all(
                item["s12_db"] <= -20.0 and item["s21_db"] <= -20.0
                for item in frequency_metrics
            ),
            "all_tarc_at_or_below_minus_10_db": all(
                item["tarc_worst_phase_db"] <= -10.0
                for item in frequency_metrics
            ),
        },
    }


def _write_s_matrix_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["frequency_ghz"]
    for key in ("s11", "s12", "s21", "s22"):
        fieldnames.extend([f"{key}_real", f"{key}_imag", f"{key}_db"])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output: dict[str, float] = {"frequency_ghz": row["frequency_ghz"]}
            for key in ("s11", "s12", "s21", "s22"):
                value = row[key]
                output[f"{key}_real"] = value.real
                output[f"{key}_imag"] = value.imag
                output[f"{key}_db"] = _db(abs(value))
            writer.writerow(output)


def _antenna_parameters_for_port(
    app: Hfss,
    active_terminal: str,
    inactive_terminal: str,
) -> dict[str, Any]:
    if not app.edit_sources(
        {
            active_terminal: ("1W", "0deg"),
            inactive_terminal: ("0W", "0deg"),
        },
        include_port_post_processing=True,
    ):
        raise RuntimeError(f"Could not activate {active_terminal} alone.")
    expressions = [
        "PeakDirectivity",
        "PeakGain",
        "PeakRealizedGain",
        "RadiatedPower",
        "AcceptedPower",
        "IncidentPower",
        "RadiationEfficiency",
        "TotalEfficiency",
    ]
    report = app.post.reports_by_category.antenna_parameters(
        expressions,
        f"{SETUP_NAME} : LastAdaptive",
        FAR_FIELD_NAME,
    )
    report.variations = app.available_variations.nominal_values
    report.variations["Freq"] = [f"{CENTER_GHZ}GHz"]
    data = report.get_solution_data()
    if not data:
        raise RuntimeError(f"No antenna parameters were returned for {active_terminal}.")
    values: dict[str, float] = {}
    for expression in expressions:
        _, result = data.get_expression_data(expression, formula="real")
        if not result:
            raise RuntimeError(f"{expression} was empty for {active_terminal}.")
        values[expression] = float(_json_value(result[0]))
    radiation_efficiency = values["RadiationEfficiency"]
    total_efficiency = values["TotalEfficiency"]
    strict_power_balance = (
        0.0 <= radiation_efficiency <= 1.0 + 1e-9
        and 0.0 <= total_efficiency <= 1.0 + 1e-9
    )
    return {
        "active_terminal": active_terminal,
        "frequency_ghz": CENTER_GHZ,
        "peak_directivity_linear": values["PeakDirectivity"],
        "peak_directivity_dbi": _db_power(values["PeakDirectivity"]),
        "peak_gain_linear": values["PeakGain"],
        "peak_gain_dbi": _db_power(values["PeakGain"]),
        "peak_realized_gain_linear": values["PeakRealizedGain"],
        "peak_realized_gain_dbi": _db_power(values["PeakRealizedGain"]),
        "radiated_power_w": values["RadiatedPower"],
        "accepted_power_w": values["AcceptedPower"],
        "incident_power_w": values["IncidentPower"],
        "radiation_efficiency_ratio": radiation_efficiency,
        "total_efficiency_ratio": total_efficiency,
        "power_balance_strictly_physical": strict_power_balance,
        # Retain the legacy key for downstream readers, but make it obey the
        # physical upper bound rather than silently accepting efficiency > 1.
        "power_balance_numerically_physical": strict_power_balance,
        "power_balance_within_one_percent": (
            0.0 <= radiation_efficiency <= 1.01
            and 0.0 <= total_efficiency <= 1.01
        ),
    }


def _embedded_pattern_metrics(
    app: Hfss,
    antenna_parameters: list[dict[str, Any]],
) -> dict[str, Any]:
    """Integrate complex embedded fields at the adaptive frequency.

    The full-sphere field integral provides publication-relevant ECC and a
    same-solve post-processed radiated-power diagnostic. HFSS's E-field
    convention is used:
    U = (|rE_theta|^2 + |rE_phi|^2) / (2 * eta_0).
    """
    try:
        import numpy as np
        from scipy.integrate import simpson
    except ImportError as exc:  # pragma: no cover - PyAEDT installs NumPy.
        raise RuntimeError(
            "NumPy and SciPy are required for embedded-field metrics."
        ) from exc

    fields = app.post.get_efields_data(
        setup_sweep_name=f"{SETUP_NAME} : LastAdaptive",
        ff_setup=FAR_FIELD_NAME,
    )
    if not fields or len(fields) != 2:
        raise RuntimeError(
            "Exactly two embedded element patterns were expected from HFSS."
        )
    source_names = list(fields)
    theta_deg = np.asarray(fields[source_names[0]][0], dtype=float)
    phi_deg = np.asarray(fields[source_names[0]][1], dtype=float)
    theta_rad = np.deg2rad(theta_deg)
    phi_rad = np.deg2rad(phi_deg)
    n_theta = len(theta_rad)
    n_phi = len(phi_rad)

    def field_array(source: str, index: int):
        raw = np.asarray(fields[source][index], dtype=complex)
        if raw.size != n_theta * n_phi:
            raise RuntimeError(
                f"Unexpected embedded-field size for {source}: {raw.size}."
            )
        # PyAEDT get_efields_data returns Phi as the outer sweep.
        return raw.reshape((n_phi, n_theta))

    def sphere_integral(values, method: str = "simpson"):
        weighted = values * np.sin(theta_rad)[None, :]
        if method == "simpson":
            theta_integral = simpson(weighted, x=theta_rad, axis=1)
            return simpson(theta_integral, x=phi_rad, axis=0)
        theta_integral = np.trapezoid(weighted, theta_rad, axis=1)
        return np.trapezoid(theta_integral, phi_rad, axis=0)

    e_theta = {name: field_array(name, 2) for name in source_names}
    e_phi = {name: field_array(name, 3) for name in source_names}
    field_power_integrals = {
        name: float(
            np.real(
                sphere_integral(
                    np.abs(e_theta[name]) ** 2 + np.abs(e_phi[name]) ** 2
                )
            )
        )
        for name in source_names
    }
    trapezoid_power_integrals = {
        name: float(
            np.real(
                sphere_integral(
                    np.abs(e_theta[name]) ** 2 + np.abs(e_phi[name]) ** 2,
                    method="trapezoid",
                )
            )
        )
        for name in source_names
    }
    cross = sphere_integral(
        e_theta[source_names[0]] * np.conj(e_theta[source_names[1]])
        + e_phi[source_names[0]] * np.conj(e_phi[source_names[1]])
    )
    ecc = float(
        abs(cross) ** 2
        / (
            field_power_integrals[source_names[0]]
            * field_power_integrals[source_names[1]]
        )
    )

    eta_0_ohm = 376.730313668
    by_terminal = {
        item["active_terminal"].split("_T", maxsplit=1)[0]: item
        for item in antenna_parameters
    }
    per_port: list[dict[str, Any]] = []
    realized_gain_grids: dict[str, Any] = {}
    for source in source_names:
        terminal_data = by_terminal.get(source.split("_T", maxsplit=1)[0])
        if terminal_data is None:
            raise RuntimeError(f"No antenna power record matched source {source}.")
        radiated_power_ff = field_power_integrals[source] / (2.0 * eta_0_ohm)
        incident_power = terminal_data["incident_power_w"]
        accepted_power = terminal_data["accepted_power_w"]
        realized_gain = (
            2.0
            * math.pi
            * (
                np.abs(e_theta[source]) ** 2
                + np.abs(e_phi[source]) ** 2
            )
            / (eta_0_ohm * incident_power)
        )
        realized_gain_grids[source] = realized_gain
        radiation_efficiency = radiated_power_ff / accepted_power
        total_efficiency = radiated_power_ff / incident_power
        strict_power_balance = (
            0.0 <= radiation_efficiency <= 1.0 + 1e-9
            and 0.0 <= total_efficiency <= 1.0 + 1e-9
        )
        per_port.append(
            {
                "source": source,
                "radiated_power_far_field_integral_w": radiated_power_ff,
                "radiation_efficiency_far_field_integral_ratio": radiation_efficiency,
                "total_efficiency_far_field_integral_ratio": total_efficiency,
                "peak_realized_gain_far_field_integral_dbi": _db_power(
                    float(np.max(realized_gain))
                ),
                "power_balance_strictly_physical": strict_power_balance,
                "power_balance_numerically_physical": strict_power_balance,
                "power_balance_within_one_percent": (
                    0.0 <= radiation_efficiency <= 1.01
                    and 0.0 <= total_efficiency <= 1.01
                ),
            }
        )

    # The train-to-base-station sector is the upper 30 degrees above horizon:
    # theta 60-90 degrees in the model's +Z upper hemisphere.
    sector_theta_mask = (theta_deg >= 60.0) & (theta_deg <= 90.0)
    port_1_gain = realized_gain_grids[source_names[0]][:, sector_theta_mask]
    port_2_gain = realized_gain_grids[source_names[1]][:, sector_theta_mask]
    selection_gain = np.maximum(port_1_gain, port_2_gain)
    selection_gain_db = 10.0 * np.log10(np.maximum(selection_gain, 1e-15))

    return {
        "frequency_ghz": CENTER_GHZ,
        "integration_grid": {
            "theta_samples": n_theta,
            "phi_samples": n_phi,
            "theta_step_deg": float(theta_deg[1] - theta_deg[0]),
            "phi_step_deg": float(phi_deg[1] - phi_deg[0]),
            "primary_quadrature": "composite Simpson",
            "cross_check_quadrature": "composite trapezoid",
            "power_integral_difference_percent": {
                name: (
                    100.0
                    * (
                        field_power_integrals[name]
                        - trapezoid_power_integrals[name]
                    )
                    / field_power_integrals[name]
                )
                for name in source_names
            },
        },
        "embedded_field_ecc": ecc,
        "embedded_field_diversity_gain_db": (
            10.0 * math.sqrt(max(1.0 - ecc**2, 0.0))
        ),
        "integrated_pattern_power_imbalance_db": abs(
            _db_power(field_power_integrals[source_names[0]])
            - _db_power(field_power_integrals[source_names[1]])
        ),
        "per_port": per_port,
        "upper_horizon_selection_coverage": {
            "theta_range_deg": [60.0, 90.0],
            "minimum_realized_gain_dbi": float(np.min(selection_gain_db)),
            "p10_realized_gain_dbi": float(np.percentile(selection_gain_db, 10)),
            "median_realized_gain_dbi": float(np.median(selection_gain_db)),
            "fraction_at_or_above_0_dbi": float(
                np.mean(selection_gain_db >= 0.0)
            ),
        },
        "method": (
            "complex embedded Etheta/Ephi full-sphere composite-Simpson "
            "integral with sin(theta) Jacobian and trapezoid cross-check; "
            "inactive port terminated by the solved network"
        ),
    }


def build_project(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"{output} exists; pass --overwrite explicitly.")
    parameters = _parameters(args)
    _validate_parameters(parameters)
    _validate_solver_controls(args)

    manifest_file = output.with_name(output.stem + "_manifest.json")
    validation_log = output.with_name(output.stem + "_validation.log")
    results_dir = output.parent / "results" / RESULTS_FOLDER / output.stem
    s_matrix_csv = results_dir / "s_matrix_v2_dualport.csv"
    diversity_json = results_dir / "diversity_metrics_v2_dualport.json"
    embedded_pattern_json = results_dir / "embedded_pattern_metrics_v2_dualport.json"
    convergence_file = results_dir / "convergence_v2_dualport.conv"
    mesh_file = results_dir / "mesh_v2_dualport.mstat"
    if args.overwrite:
        replace_targets = [
            output,
            output.with_name(output.name + ".lock"),
            output.with_name(output.stem + ".aedtresults"),
            output.with_name(output.stem + ".pyaedt"),
            manifest_file,
            validation_log,
            results_dir,
        ]
        for target in replace_targets:
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
        "aedt_runtime": {
            "version_requested": args.aedt_version,
            "edition_requested": args.aedt_edition,
            "student_version": args.aedt_edition == "student",
        },
        "architecture": (
            "two dual-slant, spatially separated, quarter-wave tapered "
            "monopoles on a common roof coupon"
            if args.polarization_layout == "dual-slant"
            else "two orthogonal-plane, spatially separated, quarter-wave "
            "tapered monopoles on a common roof coupon"
        ),
        "polarization_layout": args.polarization_layout,
        "slant_angle_deg": (
            args.slant_angle_deg
            if args.polarization_layout == "dual-slant"
            else None
        ),
        "installed_environment": {
            "roof_geometry": (
                "cylindrical_crown"
                if args.roof_radius_mm is not None
                else "flat_coupon"
            ),
            "roof_radius_mm": args.roof_radius_mm,
            "radome_enabled": bool(args.radome),
            "radome_layout": args.radome_layout if args.radome else None,
            "radome_permittivity": args.radome_permittivity if args.radome else None,
            "radome_loss_tangent": (
                args.radome_loss_tangent if args.radome else None
            ),
            "radome_wall_mm": args.radome_wall_mm if args.radome else None,
            "radome_air_gap_mm": args.radome_air_gap_mm if args.radome else None,
            "model_scope": (
                "representative roof-crown and dielectric-radome surrogate; "
                "connector, fasteners, cable launch, coach body, and wet-film "
                "effects are not included"
            ),
        },
        "evidence_class": "generated",
        "frequency_ghz": {
            "start": START_GHZ,
            "center": CENTER_GHZ,
            "stop": STOP_GHZ,
            "step": STEP_GHZ,
        },
        "parameters_mm": parameters,
        "finite_conductivity": bool(args.finite_conductivity),
        "open_boundary": args.open_boundary,
        "solver_controls": {
            "maximum_passes": args.maximum_passes,
            "minimum_converged_passes": args.minimum_converged_passes,
            "max_delta_s": args.max_delta_s,
            "percent_refinement": args.percent_refinement,
            "basis_order": args.basis_order,
            "absorbing_boundary_mesh_mm": args.absorbing_boundary_mesh_mm,
            "far_field_step_deg": args.far_field_step_deg,
        },
        "external_matching_network": False,
        "metric_limitations": [
            "S-parameter ECC is a screening approximation.",
            "Publication ECC requires complex embedded far-field integration.",
            "TARC is evaluated over relative phase in 5-degree increments.",
            "Radiation claims require physically bounded power balance and mesh independence.",
        ],
        "solved": False,
    }
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

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
        for name, value in parameters.items():
            app[name] = f"{value:.12g}mm"

        ground = _create_roof(
            app,
            parameters=parameters,
            finite_conductivity=args.finite_conductivity,
            roof_radius_mm=args.roof_radius_mm,
        )

        if args.polarization_layout == "dual-slant":
            _create_slanted_radiator(
                app,
                parameters=parameters,
                center_x_mm=-parameters["separation"] / 2.0,
                slant_angle_deg=-args.slant_angle_deg,
                name="Radiator1_SlantMinus",
                port_name="Port1",
                ground_name=ground.name,
                finite_conductivity=args.finite_conductivity,
            )
            _create_slanted_radiator(
                app,
                parameters=parameters,
                center_x_mm=parameters["separation"] / 2.0,
                slant_angle_deg=args.slant_angle_deg,
                name="Radiator2_SlantPlus",
                port_name="Port2",
                ground_name=ground.name,
                finite_conductivity=args.finite_conductivity,
            )
        else:
            _create_radiator_xz(
                app,
                center_x="-separation/2",
                name="Radiator1_XZ",
                port_name="Port1",
                ground_name=ground.name,
                finite_conductivity=args.finite_conductivity,
            )
            _create_radiator_yz(
                app,
                center_x="separation/2",
                name="Radiator2_YZ",
                port_name="Port2",
                ground_name=ground.name,
                finite_conductivity=args.finite_conductivity,
            )
        if args.radome:
            _create_radome(
                app,
                parameters=parameters,
                permittivity=args.radome_permittivity,
                loss_tangent=args.radome_loss_tangent,
                wall_mm=args.radome_wall_mm,
                air_gap_mm=args.radome_air_gap_mm,
                layout=args.radome_layout,
            )

        if not app.create_open_region(
            frequency=f"{START_GHZ}GHz",
            boundary=args.open_boundary,
            apply_infinite_ground=False,
        ):
            raise RuntimeError("The dual-port open region was not created.")
        if args.absorbing_boundary_mesh_mm is not None:
            absorbing_faces = [
                face.id for face in app.modeler["RadiatingSurface"].faces
            ]
            boundary_mesh = app.mesh.assign_length_mesh(
                assignment=absorbing_faces,
                inside_selection=False,
                maximum_length=f"{args.absorbing_boundary_mesh_mm}mm",
                maximum_elements=None,
                name="AbsorbingBoundaryAccuracy",
            )
            if not boundary_mesh:
                raise RuntimeError("The absorbing-boundary mesh seed was not created.")
        setup = app.create_setup(
            name=SETUP_NAME,
            setup_type="HFSSDriven",
            Frequency=f"{CENTER_GHZ}GHz",
            MaximumPasses=args.maximum_passes,
            MinimumPasses=3,
            MinimumConvergedPasses=args.minimum_converged_passes,
            MaxDeltaS=args.max_delta_s,
            PercentRefinement=args.percent_refinement,
            BasisOrder=args.basis_order,
            PortAccuracy=4,
        )
        if not setup:
            raise RuntimeError("The dual-port adaptive setup was not created.")
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
            raise RuntimeError("The dual-port n78 sweep was not created.")
        if not app.insert_infinite_sphere(
            definition="Theta-Phi",
            phi_start=0,
            phi_stop=360,
            phi_step=args.far_field_step_deg,
            theta_start=0,
            theta_stop=180,
            theta_step=args.far_field_step_deg,
            name=FAR_FIELD_NAME,
        ):
            raise RuntimeError("The dual-port far-field sphere was not created.")

        validation_code = app.validate_simple(log_file=validation_log)
        manifest["validation_code"] = bool(validation_code)
        manifest["validation_log"] = str(validation_log)
        manifest["objects"] = sorted(app.modeler.object_names)
        manifest["boundaries"] = sorted(boundary.name for boundary in app.boundaries)
        manifest["ports"] = list(app.ports)
        if validation_code != 1:
            raise RuntimeError(f"HFSS validation failed; inspect {validation_log}.")
        if not app.save_project(file_name=str(output), overwrite=True):
            raise RuntimeError("The dual-port project could not be saved.")

        if args.solve:
            solve_start = time.perf_counter()
            solve_ok = app.analyze_setup(
                SETUP_NAME,
                cores=args.cores,
                use_auto_settings=False,
                blocking=True,
            )
            if not solve_ok:
                messages = app.logger.get_messages(
                    project_name=app.project_name,
                    design_name=app.design_name,
                    level=1,
                    aedt_messages=True,
                )
                manifest["aedt_messages"] = {
                    "warnings": list(messages.warning_level),
                    "errors": list(messages.error_level),
                    "unknown": list(messages.unknown_level),
                }
                manifest_file.write_text(
                    json.dumps(manifest, indent=2),
                    encoding="utf-8",
                )
                diagnostic = (
                    messages.error_level[-1]
                    if messages.error_level
                    else "no AEDT error text was returned"
                )
                raise RuntimeError(
                    f"The dual-port solve did not complete: {diagnostic}"
                )
            manifest["solve_elapsed_seconds"] = time.perf_counter() - solve_start
            if not app.save_project(file_name=str(output), overwrite=True):
                raise RuntimeError("The solved dual-port project could not be saved.")

            rows = _complex_s_matrix(app, "Port1_T1", "Port2_T1")
            metrics = _diversity_metrics(rows)
            _write_s_matrix_csv(s_matrix_csv, rows)
            diversity_json.write_text(
                json.dumps(metrics, indent=2),
                encoding="utf-8",
            )
            manifest["diversity_metrics"] = metrics["band_summary"]
            manifest["s_matrix_csv"] = str(s_matrix_csv)
            manifest["diversity_metrics_json"] = str(diversity_json)
            antenna_parameters = [
                _antenna_parameters_for_port(app, "Port1_T1", "Port2_T1"),
                _antenna_parameters_for_port(app, "Port2_T1", "Port1_T1"),
            ]
            manifest["antenna_parameters_center"] = antenna_parameters
            embedded_pattern_metrics = _embedded_pattern_metrics(
                app,
                antenna_parameters,
            )
            embedded_pattern_json.write_text(
                json.dumps(embedded_pattern_metrics, indent=2),
                encoding="utf-8",
            )
            manifest["embedded_pattern_metrics"] = embedded_pattern_metrics
            manifest["embedded_pattern_metrics_json"] = str(
                embedded_pattern_json
            )
            manifest["convergence_file"] = app.export_convergence(
                SETUP_NAME,
                output_file=str(convergence_file),
            )
            manifest["mesh_file"] = app.export_mesh_stats(
                SETUP_NAME,
                output_file=str(mesh_file),
            )
            manifest["evidence_class"] = "simulated"
            manifest["solved"] = True

        manifest["status"] = "complete"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Project: {output}")
        print(f"Manifest: {manifest_file}")
        if args.solve:
            print(json.dumps(manifest["diversity_metrics"], indent=2))
            print(json.dumps(manifest["antenna_parameters_center"], indent=2))
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
