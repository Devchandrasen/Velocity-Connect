"""Screen blade flare angle for 50-ohm matching at 3.5 GHz."""

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

from build_n78_donor import AEDT_VERSION, PROJECT_NAME
from tune_n78_donor import (
    ANTENNA_SUFFIX,
    TERMINAL,
    TUNING_DESIGN,
    _set_candidate,
)


SETUP_NAME = "TuneFlare"
HEIGHT_SCALE = 0.87
FEED_SCALE = 0.80
FLARE_ANGLES_DEG = (10.0, 20.0, 30.0, 40.0, 50.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen blade flare angle.")
    parser.add_argument(
        "--project",
        type=Path,
        default=Path(__file__).resolve().parent / PROJECT_NAME,
    )
    parser.add_argument("--aedt-process-id", type=int, default=None)
    parser.add_argument("--cores", type=int, default=2)
    return parser.parse_args()


def _center_result(app: Hfss) -> dict[str, float]:
    expression = f"St({TERMINAL},{TERMINAL})"
    data = app.post.get_solution_data(
        expressions=expression,
        setup_sweep_name=f"{SETUP_NAME} : LastAdaptive",
        report_category="Terminal Solution Data",
        variations=app.available_variations.nominal_values,
    )
    if not data:
        raise RuntimeError("Flare setup returned no terminal data.")
    frequency, real = data.get_expression_data(expression, formula="real")
    _, imaginary = data.get_expression_data(expression, formula="imag")
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


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    build_manifest_file = project.with_name(project.stem + "_manifest.json")
    if not project.is_file() or not build_manifest_file.is_file():
        raise FileNotFoundError("The baseline project and build manifest are required.")
    build_manifest = json.loads(build_manifest_file.read_text(encoding="utf-8"))
    base_parameters = {
        key: float(value)
        for key, value in build_manifest["model_parameters_mm"].items()
    }

    manifest_file = project.with_name(project.stem + "_flare_tuning_manifest.json")
    manifest: dict[str, Any] = {
        "status": "started",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(project),
        "design": TUNING_DESIGN,
        "setup": SETUP_NAME,
        "height_scale": HEIGHT_SCALE,
        "feed_scale": FEED_SCALE,
        "flare_angles_deg": FLARE_ANGLES_DEG,
        "candidates": [],
    }
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    app: Hfss | None = None
    try:
        app = Hfss(
            project=str(project),
            design=TUNING_DESIGN,
            version=AEDT_VERSION,
            new_desktop=args.aedt_process_id is None,
            close_on_exit=False,
            student_version=True,
            aedt_process_id=args.aedt_process_id,
        )
        if TUNING_DESIGN not in app.design_list:
            raise RuntimeError(
                f"{TUNING_DESIGN} is absent; run tune_n78_donor.py first."
            )
        app.set_active_design(TUNING_DESIGN)
        if SETUP_NAME not in app.setup_names:
            setup = app.create_setup(
                name=SETUP_NAME,
                setup_type="HFSSDriven",
                Frequency="3.5GHz",
                MaximumPasses=6,
                MinimumPasses=2,
                MinimumConvergedPasses=1,
                MaxDeltaS=0.05,
            )
            if not setup:
                raise RuntimeError(f"{SETUP_NAME} could not be created.")

        _set_candidate(app, base_parameters, HEIGHT_SCALE, FEED_SCALE)
        app[f"spacing_feed{ANTENNA_SUFFIX}"] = "0mm"
        app[f"spacing_port{ANTENNA_SUFFIX}"] = "0mm"

        best: dict[str, Any] | None = None
        for angle in FLARE_ANGLES_DEG:
            app[f"flare_angle{ANTENNA_SUFFIX}"] = f"{angle:.12g}deg"
            solve_start = time.perf_counter()
            solved = app.analyze_setup(
                SETUP_NAME,
                cores=args.cores,
                use_auto_settings=False,
                blocking=True,
            )
            candidate: dict[str, Any] = {
                "flare_angle_deg": angle,
                "solved": bool(solved),
                "solve_elapsed_seconds": time.perf_counter() - solve_start,
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
                f"Flare {angle:.1f} deg: "
                f"S11={candidate.get('s11_db', float('nan')):.3f} dB",
                flush=True,
            )

        if best is None:
            raise RuntimeError("No flare candidate solved successfully.")
        app[f"flare_angle{ANTENNA_SUFFIX}"] = (
            f"{best['flare_angle_deg']:.12g}deg"
        )
        if not app.save_project(file_name=str(project), overwrite=True):
            raise RuntimeError("The flare tuning state could not be saved.")

        manifest["best_candidate"] = best
        manifest["status"] = "complete"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Best flare: {best['flare_angle_deg']} deg")
        print(f"Manifest: {manifest_file}")
        return 0
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(manifest["error"], file=sys.stderr)
        return 1
    finally:
        if app is not None:
            app.release_desktop(close_projects=False, close_desktop=False)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
