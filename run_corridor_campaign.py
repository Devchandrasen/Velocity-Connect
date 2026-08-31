#!/usr/bin/env python3
"""Run the advanced multi-cell high-speed-rail handover campaign.

The distance argument is the initial along-track UE position. With the default
three gNBs at 0, 1000, and 2000 m, a 25 s run crosses cell boundaries at both
300 and 500 km/h. This runner records every attempt and never fills missing
handover events with synthetic values.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_campaign import build_parser, run_campaign


def build_corridor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns3", default="./ns3")
    parser.add_argument("--program", default="hsr_velocity_connect")
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--out", default="out/corridor_campaign")
    parser.add_argument("--scenarios", default="metal,composite,repeater")
    parser.add_argument("--speeds", default="300,500")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--num-ues", type=int, default=10)
    parser.add_argument("--num-gnbs", type=int, default=3)
    parser.add_argument("--gnb-spacing-m", type=float, default=1000.0)
    parser.add_argument("--sim-time", type=float, default=25.0)
    parser.add_argument(
        "--traffic-direction",
        choices=("downlink", "uplink"),
        default="downlink",
    )
    parser.add_argument("--nr-scenario", default="UMi")
    parser.add_argument(
        "--nr-condition",
        choices=("LOS", "NLOS", "Default"),
        default="LOS",
    )
    parser.add_argument(
        "--shadowing",
        type=lambda value: bool(int(value)),
        default=False,
    )
    parser.add_argument(
        "--use-ideal-rrc",
        type=lambda value: bool(int(value)),
        default=True,
    )
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--max-runs", type=int, default=0)
    parser.add_argument("--donor-gain-dbi", type=float, default=None)
    parser.add_argument("--service-gain-dbi", type=float, default=None)
    parser.add_argument("--feeder-cable-loss-db", type=float, default=None)
    parser.add_argument("--indoor-distrib-loss-db", type=float, default=None)
    parser.add_argument("--coupling-loss-db", type=float, default=None)
    parser.add_argument("--gnb-tx-power-dbm", type=float, default=None)
    parser.add_argument("--ue-tx-power-dbm", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-failures", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parent = build_corridor_parser().parse_args(argv)
    args = [
        "--profile", "corridor",
        "--ns3", parent.ns3,
        "--program", parent.program,
        "--workdir", parent.workdir,
        "--out", str(Path(parent.out).resolve()),
        "--scenarios", parent.scenarios,
        "--speeds", parent.speeds,
        "--distances", "100",
        "--seeds", parent.seeds,
        "--num-ues", str(parent.num_ues),
        "--num-gnbs", str(parent.num_gnbs),
        "--gnb-spacing-m", str(parent.gnb_spacing_m),
        "--sim-time", str(parent.sim_time),
        "--traffic-direction", parent.traffic_direction,
        "--nr-scenario", parent.nr_scenario,
        "--nr-condition", parent.nr_condition,
        "--shadowing", str(int(parent.shadowing)),
        "--use-ideal-rrc", str(int(parent.use_ideal_rrc)),
        "--timeout", str(parent.timeout),
        "--max-runs", str(parent.max_runs),
    ]
    for option, value in (
        ("--donor-gain-dbi", parent.donor_gain_dbi),
        ("--service-gain-dbi", parent.service_gain_dbi),
        ("--feeder-cable-loss-db", parent.feeder_cable_loss_db),
        ("--indoor-distrib-loss-db", parent.indoor_distrib_loss_db),
        ("--coupling-loss-db", parent.coupling_loss_db),
        ("--gnb-tx-power-dbm", parent.gnb_tx_power_dbm),
        ("--ue-tx-power-dbm", parent.ue_tx_power_dbm),
    ):
        if value is not None:
            args.extend([option, str(value)])
    if parent.dry_run:
        args.append("--dry-run")
    if parent.allow_failures:
        args.append("--allow-failures")
    return run_campaign(build_parser().parse_args(args))


if __name__ == "__main__":
    sys.exit(main())
