"""Solve and export the already-generated Velocity Connect n78 HFSS model."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

from ansys.aedt.core import Hfss

from build_n78_donor import (
    AEDT_VERSION,
    DESIGN_NAME,
    PROJECT_NAME,
    SETUP_NAME,
    SWEEP_NAME,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate, solve, and export the existing n78 donor project."
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=Path(__file__).resolve().parent / PROJECT_NAME,
        help="Existing AEDT project to solve.",
    )
    parser.add_argument(
        "--aedt-process-id",
        type=int,
        default=None,
        help="Attach to an existing AEDT Student gRPC process.",
    )
    parser.add_argument(
        "--non-graphical",
        action="store_true",
        help="Open AEDT without its graphical interface when not attaching.",
    )
    parser.add_argument(
        "--cores",
        type=int,
        default=2,
        help="CPU cores requested from the Student solver.",
    )
    return parser.parse_args()


def _json_value(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def _summarize_s11(solution_data: Any, expression: str) -> dict[str, Any]:
    frequency, s11_db = solution_data.get_expression_data(
        expression=expression,
        formula="real",
    )
    points = sorted(
        (float(_json_value(freq)), float(_json_value(value)))
        for freq, value in zip(frequency, s11_db)
    )
    if not points:
        raise RuntimeError("The solved sweep returned no S11 points.")

    minimum = min(points, key=lambda point: point[1])
    center = min(points, key=lambda point: abs(point[0] - 3.5))
    passing = [point for point in points if point[1] <= -10.0]
    return {
        "trace": expression,
        "points": len(points),
        "frequency_unit": solution_data.units_sweeps.get(
            solution_data.primary_sweep, ""
        ),
        "s11_unit": solution_data.units_data.get(expression, "dB"),
        "minimum_db": minimum[1],
        "minimum_frequency_ghz": minimum[0],
        "at_3_5_ghz_db": center[1],
        "points_at_or_below_minus_10_db": len(passing),
        "fraction_at_or_below_minus_10_db": len(passing) / len(points),
    }


def solve_project(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    if not project.is_file():
        raise FileNotFoundError(f"Generate the project first: {project}")

    results_dir = project.parent / "results" / "n78_baseline"
    results_dir.mkdir(parents=True, exist_ok=True)
    validation_log = project.with_name(project.stem + "_solve_validation.log")
    build_manifest_file = project.with_name(project.stem + "_manifest.json")
    solve_manifest_file = project.with_name(project.stem + "_solve_manifest.json")
    s11_csv = results_dir / "s11_n78.csv"

    manifest: dict[str, Any] = {
        "status": "started",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(project),
        "design": DESIGN_NAME,
        "setup": SETUP_NAME,
        "sweep": SWEEP_NAME,
        "aedt_version_requested": AEDT_VERSION,
        "aedt_process_id": args.aedt_process_id,
        "student_version": True,
        "cores_requested": args.cores,
        "solved": False,
    }
    solve_manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    app: Hfss | None = None
    try:
        app = Hfss(
            project=str(project),
            design=DESIGN_NAME,
            version=AEDT_VERSION,
            non_graphical=args.non_graphical,
            new_desktop=args.aedt_process_id is None,
            close_on_exit=False,
            student_version=True,
            aedt_process_id=args.aedt_process_id,
        )

        validation_code = app.validate_simple(log_file=validation_log)
        manifest["validation_code"] = bool(validation_code)
        manifest["validation_log"] = str(validation_log)
        if validation_code != 1:
            raise RuntimeError(
                f"HFSS validation failed; inspect {validation_log} before solving."
            )

        solve_start = time.perf_counter()
        if not app.analyze_setup(
            SETUP_NAME,
            cores=args.cores,
            use_auto_settings=False,
            blocking=True,
        ):
            raise RuntimeError("HFSS did not report a successful Setup_n78 solve.")
        manifest["solve_elapsed_seconds"] = time.perf_counter() - solve_start

        if not app.save_project(file_name=str(project), overwrite=True):
            raise RuntimeError("HFSS solved but could not save the updated project.")

        expression = app.get_traces_for_plot(
            get_self_terms=True,
            get_mutual_terms=False,
        )[0]
        solution_data = app.post.get_solution_data(
            expressions=expression,
            setup_sweep_name=f"{SETUP_NAME} : {SWEEP_NAME}",
        )
        if not solution_data:
            raise RuntimeError("HFSS solved but S11 data could not be retrieved.")
        if not solution_data.export_data_to_csv(str(s11_csv), delimiter=","):
            raise RuntimeError("HFSS solved but the S11 CSV export failed.")

        exported_result_files = app.export_results(export_folder=str(results_dir))
        manifest["s11_summary"] = _summarize_s11(solution_data, expression)
        manifest["s11_csv"] = str(s11_csv)
        manifest["solver_diagnostic_files"] = [
            str(path) for path in exported_result_files
        ]
        manifest["touchstone_exported"] = False
        manifest["available_solution_sweeps"] = app.existing_analysis_sweeps
        manifest["solved"] = True
        manifest["status"] = "complete"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        solve_manifest_file.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        if build_manifest_file.is_file():
            build_manifest = json.loads(
                build_manifest_file.read_text(encoding="utf-8")
            )
            build_manifest["solved"] = True
            build_manifest["solve_manifest"] = str(solve_manifest_file)
            build_manifest_file.write_text(
                json.dumps(build_manifest, indent=2),
                encoding="utf-8",
            )

        print(f"Solved: {project}")
        print(f"S11 CSV: {s11_csv}")
        print(f"Solve manifest: {solve_manifest_file}")
        return 0
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        solve_manifest_file.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
        print(manifest["error"], file=sys.stderr)
        print(f"Failure manifest: {solve_manifest_file}", file=sys.stderr)
        return 1
    finally:
        if app is not None:
            app.release_desktop(close_projects=False, close_desktop=False)


if __name__ == "__main__":
    raise SystemExit(solve_project(parse_args()))
