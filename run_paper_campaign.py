#!/usr/bin/env python3
"""Run the three experiment families described in the submitted paper.

Each family is kept in its own directory because the paper uses different
control variables for speed, distance, and passenger-load experiments.
Failures remain visible in each campaign ledger and are never replaced with
synthetic values.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research_campaign import build_parser, run_campaign


SPEEDS = "0,100,200,300,400,500"
DISTANCES = "100,300,500,800,1000,1200,1500"
USER_COUNTS = "10,20,30,40,50"


def build_parser_for_paper() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns3", default="./ns3")
    parser.add_argument("--program", default="hsr_velocity_connect")
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--out", default="out/paper_campaign")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--max-runs", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-failures", action="store_true")
    return parser


def run_family(parent: argparse.Namespace, name: str, extra: list[str]) -> int:
    output = Path(parent.out).resolve() / name
    argv = [
        "--profile", "paper",
        "--ns3", parent.ns3,
        "--program", parent.program,
        "--workdir", parent.workdir,
        "--out", str(output),
        "--scenarios", "metal,composite,repeater",
        "--seeds", parent.seeds,
        "--timeout", str(parent.timeout),
        "--max-runs", str(parent.max_runs),
    ]
    argv.extend(extra)
    if parent.dry_run:
        argv.append("--dry-run")
    if parent.allow_failures:
        argv.append("--allow-failures")

    # Reuse the production parser so the paper runner and ordinary campaigns
    # cannot drift apart in argument handling.
    args = build_parser().parse_args(argv)
    return run_campaign(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser_for_paper()
    args = parser.parse_args(argv)
    root = Path(args.out).resolve()
    root.mkdir(parents=True, exist_ok=True)

    families = {
        "speed": ["--speeds", SPEEDS, "--distances", "500", "--num-ues", "10"],
        "distance": ["--speeds", "300", "--distances", DISTANCES, "--num-ues", "10"],
        "scalability": [
            "--scenarios", "repeater",
            "--speeds", "300",
            "--distances", "500",
            "--num-ues-list", USER_COUNTS,
        ],
    }
    statuses = {}
    for name, extra in families.items():
        print(f"=== paper family: {name} ===")
        statuses[name] = run_family(args, name, extra)

    manifest = {
        "profile": "paper",
        "paper_title": "Enhancing 5G NR Connectivity in High-Speed Railways via Passive Relaying",
        "dependency_fixes": [
            {
                "project": "CTTC 5G-LENA",
                "base_version": "v4.1.1",
                "upstream_revision": "81892efac84f2aef0a962b9da176ea7d7b6912b0",
                "patch": "patches/5g-lena-v4.1.1-harq-beam-order.patch",
                "reason": "Fix HARQ RR beam-order heap overflow",
            },
            {
                "project": "CTTC 5G-LENA",
                "base_version": "v4.1.1",
                "upstream_revision": "a1aa32c757e0f834a4e40654853ce56dee13eca3",
                "patch": "patches/5g-lena-v4.1.1-harq-symbol-budget.patch",
                "reason": "Fix DL HARQ symbol-budget underflow (upstream issue #278)",
            }
        ],
        "families": families,
        "seeds": args.seeds,
        "statuses": statuses,
        "ns3": args.ns3,
        "program": args.program,
        "workdir": args.workdir,
    }
    (root / "paper_campaign_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    failed = [name for name, status in statuses.items() if status]
    print(f"Paper campaign complete: {len(failed)} family failures")
    print(f"Manifest: {root / 'paper_campaign_manifest.json'}")
    return 1 if failed and not args.allow_failures else 0


if __name__ == "__main__":
    sys.exit(main())
