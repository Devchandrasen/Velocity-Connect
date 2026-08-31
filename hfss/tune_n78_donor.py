"""Run a bounded HFSS geometry search for the Velocity Connect n78 donor."""

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

from build_n78_donor import AEDT_VERSION, DESIGN_NAME, PROJECT_NAME, SETUP_NAME
from solve_n78_donor import _summarize_s11


TUNING_DESIGN = "VC_Donor_n78_Tuning"
TUNING_SETUP = "TuneCenter"
ANTENNA_SUFFIX = "_VC_Donor_Blade"
TERMINAL = "port_VC_Donor_Blade_1_T1"

VERTICAL_PARAMETERS = (
    "height_blade",
    "height_feed",
    "height_port",
    "height_slot_1",
    "height_slot_2",
    "height_slot_3",
    "thickness_slot",
)
FEED_PARAMETERS = ("width_feed_base", "width_feed_top")
HEIGHT_SCALES = (0.82, 0.87, 0.92)
FEED_SCALES = (0.40, 0.60, 0.80)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Screen blade height and feed width, then solve the best n78 candidate."
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=Path(__file__).resolve().parent / PROJECT_NAME,
        help="Existing AEDT project containing the baseline design.",
    )
    parser.add_argument(
        "--aedt-process-id",
        type=int,
        default=None,
        help="Attach to an existing AEDT Student gRPC process.",
    )
    parser.add_argument("--cores", type=int, default=2)
    return parser.parse_args()


def _set_candidate(
    app: Hfss,
    base_parameters: dict[str, float],
    height_scale: float,
    feed_scale: float,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for parameter in VERTICAL_PARAMETERS:
        value = f"{base_parameters[parameter] * height_scale:.12g}mm"
        app[f"{parameter}{ANTENNA_SUFFIX}"] = value
        values[f"{parameter}{ANTENNA_SUFFIX}"] = value
    for parameter in FEED_PARAMETERS:
        value = f"{base_parameters[parameter] * feed_scale:.12g}mm"
        app[f"{parameter}{ANTENNA_SUFFIX}"] = value
        values[f"{parameter}{ANTENNA_SUFFIX}"] = value
    return values


def _center_result(app: Hfss) -> dict[str, float]:
    expression = f"St({TERMINAL},{TERMINAL})"
    data = app.post.get_solution_data(
        expressions=expression,
        setup_sweep_name=f"{TUNING_SETUP} : LastAdaptive",
        report_category="Terminal Solution Data",
        variations=app.available_variations.nominal_values,
    )
    if not data:
        raise RuntimeError("TuneCenter returned no terminal solution data.")

    frequency, real = data.get_expression_data(expression, formula="real")
    _, imaginary = data.get_expression_data(expression, formula="imag")
    if len(frequency) == 0:
        raise RuntimeError("TuneCenter returned an empty frequency vector.")

    index = min(
        range(len(frequency)),
        key=lambda item: abs(float(frequency[item]) - 3.5),
    )
    gamma = complex(float(real[index]), float(imaginary[index]))
    impedance = 50.0 * (1.0 + gamma) / (1.0 - gamma)
    return {
        "frequency_ghz": float(frequency[index]),
        "s11_db": 20.0 * math.log10(abs(gamma)),
        "gamma_magnitude": abs(gamma),
        "resistance_ohm": impedance.real,
        "reactance_ohm": impedance.imag,
    }


def tune_project(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    if not project.is_file():
        raise FileNotFoundError(f"Generate the project first: {project}")

    build_manifest_file = project.with_name(project.stem + "_manifest.json")
    if not build_manifest_file.is_file():
        raise FileNotFoundError(f"Missing build manifest: {build_manifest_file}")
    build_manifest = json.loads(build_manifest_file.read_text(encoding="utf-8"))
    base_parameters = {
        key: float(value)
        for key, value in build_manifest["model_parameters_mm"].items()
    }

    results_dir = project.parent / "results" / "n78_tuning"
    results_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = project.with_name(project.stem + "_tuning_manifest.json")
    tuned_csv = results_dir / "s11_n78_tuned.csv"
    manifest: dict[str, Any] = {
        "status": "started",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(project),
        "baseline_design": DESIGN_NAME,
        "tuning_design": TUNING_DESIGN,
        "screening_setup": TUNING_SETUP,
        "height_scales": HEIGHT_SCALES,
        "feed_scales": FEED_SCALES,
        "cores_requested": args.cores,
        "candidates": [],
    }
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    app: Hfss | None = None
    try:
        app = Hfss(
            project=str(project),
            design=DESIGN_NAME,
            version=AEDT_VERSION,
            new_desktop=args.aedt_process_id is None,
            close_on_exit=False,
            student_version=True,
            aedt_process_id=args.aedt_process_id,
        )

        if TUNING_DESIGN not in app.design_list:
            if not app.duplicate_design(TUNING_DESIGN, save_after_duplicate=True):
                raise RuntimeError("The baseline design could not be duplicated.")
        else:
            app.set_active_design(TUNING_DESIGN)

        if TUNING_SETUP not in app.setup_names:
            setup = app.create_setup(
                name=TUNING_SETUP,
                setup_type="HFSSDriven",
                Frequency="3.5GHz",
                MaximumPasses=6,
                MinimumPasses=2,
                MinimumConvergedPasses=1,
                MaxDeltaS=0.05,
            )
            if not setup:
                raise RuntimeError("TuneCenter setup could not be created.")

        best: dict[str, Any] | None = None
        for height_scale in HEIGHT_SCALES:
            for feed_scale in FEED_SCALES:
                variables = _set_candidate(
                    app,
                    base_parameters,
                    height_scale,
                    feed_scale,
                )
                solve_start = time.perf_counter()
                solved = app.analyze_setup(
                    TUNING_SETUP,
                    cores=args.cores,
                    use_auto_settings=False,
                    blocking=True,
                )
                candidate: dict[str, Any] = {
                    "height_scale": height_scale,
                    "feed_scale": feed_scale,
                    "variables": variables,
                    "solve_elapsed_seconds": time.perf_counter() - solve_start,
                    "solved": bool(solved),
                }
                if solved:
                    candidate.update(_center_result(app))
                    if best is None or candidate["gamma_magnitude"] < best["gamma_magnitude"]:
                        best = candidate
                manifest["candidates"].append(candidate)
                manifest_file.write_text(
                    json.dumps(manifest, indent=2),
                    encoding="utf-8",
                )
                print(
                    "Candidate "
                    f"h={height_scale:.2f}, feed={feed_scale:.2f}: "
                    f"S11={candidate.get('s11_db', float('nan')):.3f} dB",
                    flush=True,
                )

        if best is None:
            raise RuntimeError("No screening candidate solved successfully.")

        _set_candidate(
            app,
            base_parameters,
            best["height_scale"],
            best["feed_scale"],
        )
        full_solve_start = time.perf_counter()
        if not app.analyze_setup(
            SETUP_NAME,
            cores=args.cores,
            use_auto_settings=False,
            blocking=True,
        ):
            raise RuntimeError("The best candidate failed during the full n78 sweep.")
        manifest["full_sweep_elapsed_seconds"] = (
            time.perf_counter() - full_solve_start
        )

        expression = app.get_traces_for_plot(
            get_self_terms=True,
            get_mutual_terms=False,
        )[0]
        solution_data = app.post.get_solution_data(
            expressions=expression,
            setup_sweep_name=f"{SETUP_NAME} : Sweep_n78",
            variations=app.available_variations.nominal_values,
        )
        if not solution_data:
            raise RuntimeError("The best candidate returned no full-sweep S11 data.")
        if not solution_data.export_data_to_csv(str(tuned_csv), delimiter=","):
            raise RuntimeError("The tuned S11 CSV export failed.")

        manifest["best_screening_candidate"] = best
        manifest["full_sweep_s11"] = _summarize_s11(solution_data, expression)
        manifest["full_sweep_csv"] = str(tuned_csv)
        manifest["status"] = "complete"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        if not app.save_project(file_name=str(project), overwrite=True):
            raise RuntimeError("The tuned project could not be saved.")
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Tuned design: {TUNING_DESIGN}")
        print(f"Manifest: {manifest_file}")
        print(f"S11 CSV: {tuned_csv}")
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
            app.release_desktop(close_projects=False, close_desktop=False)


if __name__ == "__main__":
    raise SystemExit(tune_project(parse_args()))
