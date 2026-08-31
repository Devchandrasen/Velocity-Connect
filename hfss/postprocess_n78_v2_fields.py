"""Post-process an existing solved V2 dual-port HFSS project.

This utility deliberately does not solve or modify the antenna geometry.  It
opens a completed project, extracts center-frequency antenna parameters and
complex embedded element patterns, and writes a standalone JSON evidence file.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from ansys.aedt.core import Hfss

from build_n78_donor import AEDT_VERSION
from build_n78_v2_dualport import (
    DESIGN_NAME,
    FAR_FIELD_NAME,
    SETUP_NAME,
    _antenna_parameters_for_port,
    _embedded_pattern_metrics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract embedded-field evidence from a solved V2 HFSS project."
    )
    parser.add_argument("project", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--graphical", action="store_true")
    parser.add_argument(
        "--aedt-version",
        default=AEDT_VERSION,
        help="AEDT release that created the project, for example 2025.2 or 2024.1.",
    )
    parser.add_argument(
        "--aedt-edition",
        choices=("student", "commercial"),
        default="student",
        help="Select the installed AEDT license family.",
    )
    parser.add_argument(
        "--far-field-step-deg",
        type=float,
        default=None,
        help=(
            "Temporarily resample the existing infinite sphere at this angular "
            "step. This does not require another electromagnetic solve."
        ),
    )
    return parser.parse_args()


def main(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    output = args.output.resolve()
    if not project.exists():
        raise FileNotFoundError(project)
    output.parent.mkdir(parents=True, exist_ok=True)

    app: Hfss | None = None
    record = {
        "status": "started",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(project),
        "design": DESIGN_NAME,
        "setup": f"{SETUP_NAME} : LastAdaptive",
        "far_field_setup": FAR_FIELD_NAME,
        "aedt_runtime": {
            "version_requested": args.aedt_version,
            "edition_requested": args.aedt_edition,
            "student_version": args.aedt_edition == "student",
        },
    }
    output.write_text(json.dumps(record, indent=2), encoding="utf-8")
    try:
        print("Opening solved project...", flush=True)
        app = Hfss(
            project=str(project),
            design=DESIGN_NAME,
            solution_type="Terminal",
            version=args.aedt_version,
            non_graphical=not args.graphical,
            new_desktop=True,
            close_on_exit=False,
            student_version=args.aedt_edition == "student",
        )
        if f"{SETUP_NAME} : LastAdaptive" not in app.existing_analysis_sweeps:
            raise RuntimeError("The requested LastAdaptive solution is not available.")
        if args.far_field_step_deg is not None:
            if not 1.0 <= args.far_field_step_deg <= 10.0:
                raise ValueError("far_field_step_deg must remain within 1-10 degrees.")
            sphere = next(
                (
                    setup
                    for setup in app.field_setups
                    if setup.name == FAR_FIELD_NAME
                ),
                None,
            )
            if sphere is None:
                raise RuntimeError(f"Far-field setup {FAR_FIELD_NAME} was not found.")
            step = f"{args.far_field_step_deg}deg"
            sphere.props["ThetaStep"] = step
            sphere.props["PhiStep"] = step
            record["temporary_far_field_step_deg"] = args.far_field_step_deg
            print(f"Temporary far-field sampling: {step}", flush=True)
        record["sources"] = list(app.osolution.GetAllSources())
        print(f"Sources: {record['sources']}", flush=True)
        print("Extracting center-frequency antenna parameters...", flush=True)
        antenna_parameters = [
            _antenna_parameters_for_port(app, "Port1_T1", "Port2_T1"),
            _antenna_parameters_for_port(app, "Port2_T1", "Port1_T1"),
        ]
        print("Integrating complex embedded fields...", flush=True)
        embedded_metrics = _embedded_pattern_metrics(app, antenna_parameters)
        record.update(
            {
                "status": "complete",
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "antenna_parameters_center": antenna_parameters,
                "embedded_pattern_metrics": embedded_metrics,
            }
        )
        output.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"Evidence: {output}", flush=True)
        print(json.dumps(embedded_metrics, indent=2), flush=True)
        return 0
    except Exception as exc:
        record.update(
            {
                "status": "failed",
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        output.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(record["error"], file=sys.stderr, flush=True)
        return 1
    finally:
        if app is not None:
            app.release_desktop(close_projects=True, close_desktop=True)


if __name__ == "__main__":
    raise SystemExit(main(parse_args()))
