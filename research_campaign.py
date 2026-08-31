#!/usr/bin/env python3
"""Run reproducible multi-seed Velocity Connect experiments.

The NS-3 application exposes a machine-readable ``single_run.csv`` endpoint.
This driver owns the experiment matrix, process isolation, failure ledger, and
confidence-interval summary so a partial campaign is still auditable.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
from itertools import product
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from statistical_evidence import ci95_half_width


METRICS = (
    "throughput_mbps",
    "p05_ue_throughput_mbps",
    "median_ue_throughput_mbps",
    "pdr",
    "mean_lat_ms",
    "p95_lat_ms",
    "jain_fairness",
    "handover_attempts",
    "handover_successes",
    "handover_failures",
    "mean_handover_duration_ms",
    "max_handover_duration_ms",
    "mean_application_gap_ms",
    "max_application_gap_ms",
    "bad_ipv4_length_drops",
    "short_transport_header_hash_events",
)
SUMMARY_DIMENSIONS = (
    "scenario",
    "passive_model",
    "traffic_direction",
    "nr_scenario",
    "nr_condition",
    "shadowing",
    "speed_kmph",
    "distance_m",
    "gnb_height_m",
    "ue_height_m",
    "num_ues",
    "num_gnbs",
    "gnb_spacing_m",
    "enable_handover",
    "use_ideal_rrc",
    "handover_hysteresis_db",
    "handover_ttt_ms",
    "declared_passive_loss_db",
    "feeder_loss_db",
    "coupling_loss_db",
    "indoor_path_loss_db",
    "donor_gain_dbi",
    "service_gain_dbi",
    "network_loss_db",
    "aperture_gain_db",
    "eff_loss_db",
    "gnb_tx_power_dbm",
    "ue_tx_power_dbm",
    "effective_gnb_tx_power_dbm",
    "effective_ue_tx_power_dbm",
    "numerology",
    "scs_khz",
)
REQUIRED_RESULT_FIELDS = {
    "scenario",
    "passive_model",
    "traffic_direction",
    "nr_scenario",
    "nr_condition",
    "shadowing",
    "speed_kmph",
    "distance_m",
    "gnb_height_m",
    "ue_height_m",
    "num_ues",
    "num_gnbs",
    "gnb_spacing_m",
    "enable_handover",
    "use_ideal_rrc",
    "handover_hysteresis_db",
    "handover_ttt_ms",
    "seed",
    "run",
    "declared_passive_loss_db",
    "feeder_loss_db",
    "coupling_loss_db",
    "donor_gain_dbi",
    "service_gain_dbi",
    "network_loss_db",
    "indoor_path_loss_db",
    "aperture_gain_db",
    "eff_loss_db",
    "gnb_tx_power_dbm",
    "ue_tx_power_dbm",
    "effective_gnb_tx_power_dbm",
    "effective_ue_tx_power_dbm",
    "numerology",
    "scs_khz",
    "throughput_mbps",
    "p05_ue_throughput_mbps",
    "median_ue_throughput_mbps",
    "pdr",
    "tx_pkts",
    "rx_pkts",
    "mean_lat_ms",
    "p50_lat_ms",
    "p95_lat_ms",
    "jain_fairness",
    "handover_attempts",
    "handover_successes",
    "handover_failures",
    "mean_handover_duration_ms",
    "max_handover_duration_ms",
    "mean_application_gap_ms",
    "max_application_gap_ms",
    "bad_ipv4_length_drops",
    "short_transport_header_hash_events",
}


PROFILE_DEFAULTS: dict[str, dict[str, object]] = {
    "dev": {
        "num_ues": 1,
        "gnb_height_m": 10.0,
        "gnb_lateral_offset_m": 0.0,
        "ue_height_m": 1.5,
        "numerology": 0,
        "sim_time": 2.0,
        "app_start": 0.2,
        "app_stop": 0.0,
        "channel_update_period_ms": 0.0,
        "enable_srs": False,
        "app_pkt_size": 1024,
        "saturating_load": True,
        "per_ue_offered_mbps": 8.19,
        "saturating_interval_us": 100.0,
        "traffic_direction": "downlink",
        "nr_scenario": "UMi",
        "nr_condition": "LOS",
        "shadowing": False,
        "paper_profile": False,
        "passive_model": "component_budget",
        "num_gnbs": 1,
        "gnb_spacing_m": 1000.0,
        "guarded_corridor": False,
        "enable_handover": False,
        "handover_hysteresis_db": 1.5,
        "handover_ttt_ms": 128,
        "use_ideal_rrc": True,
        "legacy_repeater_loss_db": 5.0,
        "declared_passive_loss_db": 6.5,
        "donor_gain_dbi": 8.0,
        "service_gain_dbi": 2.0,
        "feeder_cable_loss_db": 3.0,
        "indoor_distrib_loss_db": 4.0,
        "coupling_loss_db": 8.0,
        "gnb_tx_power_dbm": 40.0,
        "ue_tx_power_dbm": 23.0,
    },
    "paper": {
        "num_ues": 10,
        "gnb_height_m": 10.0,
        "gnb_lateral_offset_m": 0.0,
        "ue_height_m": 1.5,
        "numerology": 1,
        "sim_time": 2.0,
        "app_start": 0.2,
        "app_stop": 0.0,
        "channel_update_period_ms": 0.0,
        "enable_srs": False,
        "app_pkt_size": 1024,
        "saturating_load": False,
        "per_ue_offered_mbps": 8.19,
        "saturating_interval_us": 100.0,
        "traffic_direction": "downlink",
        "nr_scenario": "UMi",
        "nr_condition": "LOS",
        "shadowing": False,
        "paper_profile": True,
        "passive_model": "legacy_scalar",
        "num_gnbs": 1,
        "gnb_spacing_m": 1000.0,
        "guarded_corridor": False,
        "enable_handover": False,
        "handover_hysteresis_db": 1.5,
        "handover_ttt_ms": 128,
        "use_ideal_rrc": True,
        "legacy_repeater_loss_db": 5.0,
        "declared_passive_loss_db": 6.5,
        "donor_gain_dbi": 8.0,
        "service_gain_dbi": 2.0,
        "feeder_cable_loss_db": 3.0,
        "indoor_distrib_loss_db": 4.0,
        "coupling_loss_db": 8.0,
        "gnb_tx_power_dbm": 40.0,
        "ue_tx_power_dbm": 23.0,
    },
    "corridor": {
        "num_ues": 10,
        "gnb_height_m": 10.0,
        "gnb_lateral_offset_m": 10.0,
        "ue_height_m": 1.5,
        "numerology": 1,
        "sim_time": 25.0,
        "app_start": 1.0,
        "app_stop": 0.0,
        "channel_update_period_ms": 5.0,
        "enable_srs": False,
        "app_pkt_size": 1024,
        "saturating_load": False,
        "per_ue_offered_mbps": 4.0,
        "saturating_interval_us": 100.0,
        "traffic_direction": "downlink",
        "nr_scenario": "UMi",
        "nr_condition": "LOS",
        "shadowing": False,
        "paper_profile": False,
        "passive_model": "component_budget",
        "num_gnbs": 3,
        "gnb_spacing_m": 1000.0,
        "guarded_corridor": False,
        "enable_handover": True,
        "handover_hysteresis_db": 1.5,
        "handover_ttt_ms": 128,
        "use_ideal_rrc": True,
        "legacy_repeater_loss_db": 5.0,
        "declared_passive_loss_db": 6.5,
        "donor_gain_dbi": 8.0,
        "service_gain_dbi": 2.0,
        "feeder_cable_loss_db": 3.0,
        "indoor_distrib_loss_db": 4.0,
        "coupling_loss_db": 8.0,
        "gnb_tx_power_dbm": 40.0,
        "ue_tx_power_dbm": 23.0,
    },
}


def parse_csv_list(raw: str, cast):
    """Parse a comma-separated CLI value while rejecting empty entries."""

    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            raise ValueError(f"Invalid empty value in list: {raw!r}")
        values.append(cast(item))
    if not values:
        raise ValueError("At least one value is required")
    return values


def build_simulation_command(
    ns3: str,
    program: str,
    scenario: str,
    speed_kmph: float,
    distance_m: float,
    num_ues: int,
    seed: int,
    run: int,
    out_dir: Path,
    *,
    gnb_height_m: float = 10.0,
    gnb_lateral_offset_m: float = 0.0,
    ue_height_m: float = 1.5,
    sim_time: float = 2.0,
    app_start: float = 0.2,
    app_stop: float = 0.0,
    channel_update_period_ms: float = 0.0,
    enable_srs: bool = False,
    app_pkt_size: int = 1024,
    saturating_load: bool = True,
    per_ue_offered_mbps: float = 8.19,
    saturating_interval_us: float = 100.0,
    traffic_direction: str = "downlink",
    nr_scenario: str = "UMi",
    nr_condition: str = "LOS",
    shadowing: bool = False,
    paper_profile: bool = False,
    numerology: int = 0,
    passive_model: str = "component_budget",
    num_gnbs: int = 1,
    gnb_spacing_m: float = 1000.0,
    guarded_corridor: bool = False,
    enable_handover: bool = False,
    handover_hysteresis_db: float = 1.5,
    handover_ttt_ms: int = 128,
    use_ideal_rrc: bool = False,
    legacy_repeater_loss_db: float = 5.0,
    declared_passive_loss_db: float = 6.5,
    donor_gain_dbi: float = 8.0,
    service_gain_dbi: float = 2.0,
    feeder_cable_loss_db: float = 3.0,
    indoor_distrib_loss_db: float = 4.0,
    coupling_loss_db: float = 8.0,
    gnb_tx_power_dbm: float = 40.0,
    ue_tx_power_dbm: float = 23.0,
) -> list[str]:
    """Build an argv-safe NS-3 wrapper command without invoking a shell."""

    run_arguments = (
        f"{program} --singleRun=1 --scenario={scenario} "
        f"--speed={speed_kmph:g} --distance={distance_m:g} "
        f"--gnbHeightM={gnb_height_m:g} "
        f"--gnbLateralOffsetM={gnb_lateral_offset_m:g} "
        f"--ueHeightM={ue_height_m:g} "
        f"--numUes={num_ues} --seed={seed} --run={run} "
        f"--simTime={sim_time:g} --appStart={app_start:g} "
        f"--appStop={app_stop:g} "
        f"--channelUpdatePeriodMs={channel_update_period_ms:g} "
        f"--enableSrs={int(enable_srs)} "
        f"--appPktSize={app_pkt_size} --saturatingLoad={int(saturating_load)} "
        f"--perUeOfferedMbps={per_ue_offered_mbps:g} "
        f"--saturatingIntervalUs={saturating_interval_us:g} "
        f"--trafficDirection={traffic_direction} "
        f"--nrScenario={nr_scenario} --nrCondition={nr_condition} "
        f"--shadowing={int(shadowing)} "
        f"--numerology={numerology} "
        f"--paperProfile={int(paper_profile)} "
        f"--passiveModel={passive_model} "
        f"--numGnbs={num_gnbs} --gnbSpacingM={gnb_spacing_m:g} "
        f"--guardedCorridor={int(guarded_corridor)} "
        f"--enableHandover={int(enable_handover)} "
        f"--handoverHysteresisDb={handover_hysteresis_db:g} "
        f"--handoverTimeToTriggerMs={handover_ttt_ms} "
        f"--useIdealRrc={int(use_ideal_rrc)} "
        f"--legacyRepeaterLossDb={legacy_repeater_loss_db:g} "
        f"--declaredPassiveLossDb={declared_passive_loss_db:g} "
        f"--donorGainDbi={donor_gain_dbi:g} "
        f"--serviceGainDbi={service_gain_dbi:g} "
        f"--feederCableLossDb={feeder_cable_loss_db:g} "
        f"--indoorDistribLossDb={indoor_distrib_loss_db:g} "
        f"--couplingLossDb={coupling_loss_db:g} "
        f"--gnbTxPowerDbm={gnb_tx_power_dbm:g} "
        f"--ueTxPowerDbm={ue_tx_power_dbm:g} "
        f"--outDir={out_dir.as_posix()}"
    )
    return [ns3, "run", run_arguments]


def resolve_profile(args: argparse.Namespace) -> dict[str, object]:
    """Resolve profile defaults while preserving explicit CLI overrides."""

    values = dict(PROFILE_DEFAULTS[args.profile])
    overrides = {
        "num_ues": args.num_ues,
        "gnb_height_m": args.gnb_height_m,
        "gnb_lateral_offset_m": args.gnb_lateral_offset_m,
        "ue_height_m": args.ue_height_m,
        "numerology": args.numerology,
        "sim_time": args.sim_time,
        "app_start": args.app_start,
        "app_stop": args.app_stop,
        "channel_update_period_ms": args.channel_update_period_ms,
        "enable_srs": args.enable_srs,
        "app_pkt_size": args.app_pkt_size,
        "saturating_load": args.saturating_load,
        "per_ue_offered_mbps": args.per_ue_offered_mbps,
        "saturating_interval_us": args.saturating_interval_us,
        "traffic_direction": args.traffic_direction,
        "nr_scenario": args.nr_scenario,
        "nr_condition": args.nr_condition,
        "shadowing": args.shadowing,
        "passive_model": args.passive_model,
        "num_gnbs": args.num_gnbs,
        "gnb_spacing_m": args.gnb_spacing_m,
        "guarded_corridor": args.guarded_corridor,
        "enable_handover": args.enable_handover,
        "handover_hysteresis_db": args.handover_hysteresis_db,
        "handover_ttt_ms": args.handover_ttt_ms,
        "use_ideal_rrc": args.use_ideal_rrc,
        "legacy_repeater_loss_db": args.legacy_repeater_loss_db,
        "declared_passive_loss_db": args.declared_passive_loss_db,
        "donor_gain_dbi": args.donor_gain_dbi,
        "service_gain_dbi": args.service_gain_dbi,
        "feeder_cable_loss_db": args.feeder_cable_loss_db,
        "indoor_distrib_loss_db": args.indoor_distrib_loss_db,
        "coupling_loss_db": args.coupling_loss_db,
        "gnb_tx_power_dbm": args.gnb_tx_power_dbm,
        "ue_tx_power_dbm": args.ue_tx_power_dbm,
    }
    for key, value in overrides.items():
        if value is not None:
            values[key] = value
    return values


def validate_profile(profile: Mapping[str, object]) -> None:
    """Reject invalid campaign settings before starting expensive runs."""

    finite_nonnegative = (
        "sim_time",
        "app_start",
        "app_stop",
        "channel_update_period_ms",
        "per_ue_offered_mbps",
        "saturating_interval_us",
        "gnb_spacing_m",
        "gnb_height_m",
        "gnb_lateral_offset_m",
        "ue_height_m",
        "handover_hysteresis_db",
        "legacy_repeater_loss_db",
        "declared_passive_loss_db",
        "donor_gain_dbi",
        "service_gain_dbi",
        "feeder_cable_loss_db",
        "indoor_distrib_loss_db",
        "coupling_loss_db",
    )
    for field in finite_nonnegative:
        value = float(profile[field])
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{field} must be finite and non-negative")

    for field in ("gnb_tx_power_dbm", "ue_tx_power_dbm"):
        if not math.isfinite(float(profile[field])):
            raise ValueError(f"{field} must be finite")

    if int(profile["num_ues"]) < 1:
        raise ValueError("num_ues must be at least 1")
    if int(profile["num_gnbs"]) < 1:
        raise ValueError("num_gnbs must be at least 1")
    if int(profile["app_pkt_size"]) < 1:
        raise ValueError("app_pkt_size must be at least 1")
    if not 0 <= int(profile["numerology"]) <= 5:
        raise ValueError("numerology must be between 0 and 5")
    if float(profile["sim_time"]) <= float(profile["app_start"]):
        raise ValueError("sim_time must be greater than app_start")
    app_stop = float(profile["app_stop"])
    if app_stop > 0.0 and not (
        float(profile["app_start"]) < app_stop <= float(profile["sim_time"])
    ):
        raise ValueError("app_stop must exceed app_start and not exceed sim_time")
    if bool(profile["saturating_load"]):
        if float(profile["saturating_interval_us"]) <= 0.0:
            raise ValueError("saturating_interval_us must be positive")
    elif float(profile["per_ue_offered_mbps"]) <= 0.0:
        raise ValueError("per_ue_offered_mbps must be positive")
    if bool(profile["enable_handover"]):
        if int(profile["num_gnbs"]) < 2:
            raise ValueError("handover requires at least two gNBs")
        if float(profile["gnb_spacing_m"]) <= 0.0:
            raise ValueError("handover requires positive gNB spacing")
    if bool(profile["guarded_corridor"]) and int(profile["num_gnbs"]) < 6:
        raise ValueError("guarded_corridor requires at least six gNBs")
    if str(profile["traffic_direction"]) not in {"downlink", "uplink"}:
        raise ValueError("traffic_direction must be downlink or uplink")
    if not str(profile["nr_scenario"]).strip():
        raise ValueError("nr_scenario cannot be empty")
    if str(profile["nr_condition"]) not in {"LOS", "NLOS", "Default"}:
        raise ValueError("nr_condition must be LOS, NLOS, or Default")

    if profile["passive_model"] == "component_budget":
        equivalent_loss = (
            float(profile["feeder_cable_loss_db"])
            + float(profile["coupling_loss_db"])
            + float(profile["indoor_distrib_loss_db"])
            - float(profile["donor_gain_dbi"])
            - float(profile["service_gain_dbi"])
        )
        if equivalent_loss < 0.0:
            raise ValueError(
                "component budget produces unsupported net passive gain "
                f"({equivalent_loss:g} dB)"
            )


def read_single_result(path: Path) -> dict[str, str]:
    """Read and validate exactly one simulator result row."""

    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != 1:
        raise ValueError(f"Expected one result row in {path}, found {len(rows)}")

    row = rows[0]
    missing = REQUIRED_RESULT_FIELDS.difference(row)
    if missing:
        raise ValueError(f"Missing result fields in {path}: {sorted(missing)}")
    return row


def _finite_values(rows: Iterable[Mapping[str, str]], field: str) -> list[float]:
    values = []
    for row in rows:
        try:
            value = float(row[field])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def aggregate_rows(rows: Sequence[Mapping[str, str]]) -> list[dict[str, object]]:
    """Aggregate successful single-run rows with sample SD and 95% CI."""

    groups: dict[tuple[str, ...], list[Mapping[str, str]]] = {}
    for row in rows:
        key = tuple(str(row.get(field, "")).strip() for field in SUMMARY_DIMENSIONS)
        groups.setdefault(key, []).append(row)

    summaries: list[dict[str, object]] = []
    for key, group in sorted(groups.items()):
        summary: dict[str, object] = dict(zip(SUMMARY_DIMENSIONS, key))
        summary["n_runs"] = len(group)
        for metric in METRICS:
            values = _finite_values(group, metric)
            mean = statistics.fmean(values) if values else math.nan
            std = statistics.stdev(values) if len(values) > 1 else 0.0
            ci95 = ci95_half_width(values)
            summary[f"{metric}_n"] = len(values)
            summary[f"{metric}_mean"] = mean
            summary[f"{metric}_std"] = std
            summary[f"{metric}_ci95"] = ci95
        summaries.append(summary)
    return summaries


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_summary(path: Path, summaries: Sequence[Mapping[str, object]]) -> None:
    fields = [*SUMMARY_DIMENSIONS, "n_runs"]
    for metric in METRICS:
        fields.extend(
            [f"{metric}_n", f"{metric}_mean", f"{metric}_std", f"{metric}_ci95"]
        )
    _write_csv(path, summaries, fields)


def _tail(text: str, limit: int = 4000) -> str:
    text = text.strip()
    return text[-limit:] if text else ""


def run_campaign(args: argparse.Namespace) -> int:
    output_dir = Path(args.out)
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    profile = resolve_profile(args)
    validate_profile(profile)
    scenarios = parse_csv_list(args.scenarios, str)
    unknown_scenarios = sorted(set(scenarios) - {"metal", "composite", "repeater"})
    if unknown_scenarios:
        raise ValueError(
            f"Unknown scenario(s): {', '.join(unknown_scenarios)}; "
            "expected metal, composite, or repeater"
        )
    speeds = parse_csv_list(args.speeds, float)
    distances = parse_csv_list(args.distances, float)
    seeds = parse_csv_list(args.seeds, int)
    if any(not math.isfinite(value) or value < 0.0 for value in speeds):
        raise ValueError("All speeds must be finite and non-negative")
    if bool(profile["guarded_corridor"]) and any(value <= 0.0 for value in speeds):
        raise ValueError("guarded_corridor requires every speed to be positive")
    if any(not math.isfinite(value) or value < 0.0 for value in distances):
        raise ValueError("All distances must be finite and non-negative")
    if any(value < 1 for value in seeds):
        raise ValueError("All seeds must be at least 1")
    if args.run_base < 1:
        raise ValueError("--run-base must be at least 1")
    if not math.isfinite(args.timeout) or args.timeout <= 0.0:
        raise ValueError("--timeout must be finite and positive")
    if args.num_ues_list.strip():
        num_ues_values = parse_csv_list(args.num_ues_list, int)
    else:
        num_ues_values = [int(profile["num_ues"])]
    if any(value < 1 for value in num_ues_values):
        raise ValueError("All UE counts must be at least 1")
    runs = list(product(scenarios, speeds, distances, num_ues_values, seeds))
    if args.max_runs and len(runs) > args.max_runs:
        raise ValueError(
            f"Campaign contains {len(runs)} runs, exceeding --max-runs={args.max_runs}"
        )

    config = {
        "program": args.program,
        "ns3": args.ns3,
        "scenarios": scenarios,
        "speeds_kmph": speeds,
        "distances_m": distances,
        "seeds": seeds,
        "num_ues": profile["num_ues"],
        "gnb_height_m": profile["gnb_height_m"],
        "gnb_lateral_offset_m": profile["gnb_lateral_offset_m"],
        "ue_height_m": profile["ue_height_m"],
        "num_ues_values": num_ues_values,
        "numerology": profile["numerology"],
        "subcarrier_spacing_khz": 15 * (2 ** int(profile["numerology"])),
        "profile": args.profile,
        "sim_time": profile["sim_time"],
        "app_start": profile["app_start"],
        "app_stop": profile["app_stop"],
        "channel_update_period_ms": profile["channel_update_period_ms"],
        "enable_srs": profile["enable_srs"],
        "app_pkt_size": profile["app_pkt_size"],
        "saturating_load": profile["saturating_load"],
        "per_ue_offered_mbps": profile["per_ue_offered_mbps"],
        "saturating_interval_us": profile["saturating_interval_us"],
        "traffic_direction": profile["traffic_direction"],
        "nr_scenario": profile["nr_scenario"],
        "nr_condition": profile["nr_condition"],
        "shadowing": profile["shadowing"],
        "passive_model": profile["passive_model"],
        "num_gnbs": profile["num_gnbs"],
        "gnb_spacing_m": profile["gnb_spacing_m"],
        "guarded_corridor": profile["guarded_corridor"],
        "enable_handover": profile["enable_handover"],
        "handover_hysteresis_db": profile["handover_hysteresis_db"],
        "handover_ttt_ms": profile["handover_ttt_ms"],
        "use_ideal_rrc": profile["use_ideal_rrc"],
        "legacy_repeater_loss_db": profile["legacy_repeater_loss_db"],
        "declared_passive_loss_db": profile["declared_passive_loss_db"],
        "donor_gain_dbi": profile["donor_gain_dbi"],
        "service_gain_dbi": profile["service_gain_dbi"],
        "feeder_cable_loss_db": profile["feeder_cable_loss_db"],
        "indoor_distrib_loss_db": profile["indoor_distrib_loss_db"],
        "coupling_loss_db": profile["coupling_loss_db"],
        "gnb_tx_power_dbm": profile["gnb_tx_power_dbm"],
        "ue_tx_power_dbm": profile["ue_tx_power_dbm"],
        "run_base": args.run_base,
        "timeout_s": args.timeout,
        "dry_run": args.dry_run,
    }
    (output_dir / "campaign_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    ledger_rows: list[dict[str, object]] = []
    successful_rows: list[dict[str, str]] = []
    for index, (scenario, speed, distance, num_ues, seed) in enumerate(runs):
        run_number = args.run_base + index
        run_id = f"run_{index + 1:04d}_{scenario}_{speed:g}kmh_{distance:g}m_n{num_ues}_seed{seed}"
        run_output = raw_dir / run_id
        run_output.mkdir(parents=True, exist_ok=True)
        command = build_simulation_command(
            args.ns3,
            args.program,
            scenario,
            speed,
            distance,
            num_ues,
            seed,
            run_number,
            run_output,
            gnb_height_m=float(profile["gnb_height_m"]),
            gnb_lateral_offset_m=float(profile["gnb_lateral_offset_m"]),
            ue_height_m=float(profile["ue_height_m"]),
            sim_time=float(profile["sim_time"]),
            app_start=float(profile["app_start"]),
            app_stop=float(profile["app_stop"]),
            channel_update_period_ms=float(profile["channel_update_period_ms"]),
            enable_srs=bool(profile["enable_srs"]),
            app_pkt_size=int(profile["app_pkt_size"]),
            saturating_load=bool(profile["saturating_load"]),
            per_ue_offered_mbps=float(profile["per_ue_offered_mbps"]),
            saturating_interval_us=float(profile["saturating_interval_us"]),
            traffic_direction=str(profile["traffic_direction"]),
            nr_scenario=str(profile["nr_scenario"]),
            nr_condition=str(profile["nr_condition"]),
            shadowing=bool(profile["shadowing"]),
            paper_profile=bool(profile["paper_profile"]),
            numerology=int(profile["numerology"]),
            passive_model=str(profile["passive_model"]),
            num_gnbs=int(profile["num_gnbs"]),
            gnb_spacing_m=float(profile["gnb_spacing_m"]),
            guarded_corridor=bool(profile["guarded_corridor"]),
            enable_handover=bool(profile["enable_handover"]),
            handover_hysteresis_db=float(profile["handover_hysteresis_db"]),
            handover_ttt_ms=int(profile["handover_ttt_ms"]),
            use_ideal_rrc=bool(profile["use_ideal_rrc"]),
            legacy_repeater_loss_db=float(profile["legacy_repeater_loss_db"]),
            declared_passive_loss_db=float(
                profile["declared_passive_loss_db"]
            ),
            donor_gain_dbi=float(profile["donor_gain_dbi"]),
            service_gain_dbi=float(profile["service_gain_dbi"]),
            feeder_cable_loss_db=float(profile["feeder_cable_loss_db"]),
            indoor_distrib_loss_db=float(profile["indoor_distrib_loss_db"]),
            coupling_loss_db=float(profile["coupling_loss_db"]),
            gnb_tx_power_dbm=float(profile["gnb_tx_power_dbm"]),
            ue_tx_power_dbm=float(profile["ue_tx_power_dbm"]),
        )
        print(f"[{index + 1}/{len(runs)}] {run_id}")

        ledger: dict[str, object] = {
            "run_id": run_id,
            "scenario": scenario,
            "speed_kmph": speed,
            "distance_m": distance,
            "num_ues": num_ues,
            "seed": seed,
            "run": run_number,
            "status": "dry_run" if args.dry_run else "failed",
            "return_code": "",
            "raw_dir": str(run_output),
            "error": "",
        }

        if args.dry_run:
            print("  " + " ".join(command))
            ledger_rows.append(ledger)
            continue

        try:
            completed = subprocess.run(
                command,
                cwd=args.workdir,
                capture_output=True,
                text=True,
                timeout=args.timeout,
                check=False,
            )
            ledger["return_code"] = completed.returncode
            result_path = run_output / "single_run.csv"
            if completed.returncode != 0:
                ledger["error"] = _tail(completed.stderr or completed.stdout)
            elif not result_path.exists():
                ledger["error"] = "Simulator exited successfully but single_run.csv is missing"
            else:
                result = read_single_result(result_path)
                if result["scenario"] != scenario:
                    raise ValueError(
                        f"Result scenario {result['scenario']!r} does not match {scenario!r}"
                    )
                result_numerology_raw = float(result["numerology"])
                if not result_numerology_raw.is_integer():
                    raise ValueError(
                        f"Result numerology {result_numerology_raw} is not an integer"
                    )
                result_numerology = int(result_numerology_raw)
                expected_numerology = int(profile["numerology"])
                if result_numerology != expected_numerology:
                    raise ValueError(
                        f"Result numerology {result_numerology} does not match "
                        f"campaign numerology {expected_numerology}"
                    )
                result_scs_khz = float(result["scs_khz"])
                expected_scs_khz = 15.0 * (2 ** expected_numerology)
                if not math.isfinite(result_scs_khz) or not math.isclose(
                    result_scs_khz, expected_scs_khz, rel_tol=0.0, abs_tol=1e-9
                ):
                    raise ValueError(
                        f"Result SCS {result_scs_khz:g} kHz does not match "
                        f"campaign SCS {expected_scs_khz:g} kHz"
                    )
                if result["passive_model"] != str(profile["passive_model"]):
                    raise ValueError(
                        f"Result passive model {result['passive_model']!r} does not match "
                        f"campaign model {profile['passive_model']!r}"
                    )
                if (
                    scenario == "repeater"
                    and profile["passive_model"] == "declared_scalar"
                ):
                    expected_declared_loss = float(
                        profile["declared_passive_loss_db"]
                    )
                    for field in ("declared_passive_loss_db", "eff_loss_db"):
                        actual = float(result[field])
                        if not math.isfinite(actual) or not math.isclose(
                            actual,
                            expected_declared_loss,
                            rel_tol=0.0,
                            abs_tol=1e-9,
                        ):
                            raise ValueError(
                                f"Result {field}={actual} does not match "
                                f"declared scalar loss {expected_declared_loss}"
                            )
                if result["traffic_direction"] != str(profile["traffic_direction"]):
                    raise ValueError(
                        f"Result traffic direction {result['traffic_direction']!r} does not "
                        f"match campaign direction {profile['traffic_direction']!r}"
                    )
                if result["nr_scenario"] != str(profile["nr_scenario"]):
                    raise ValueError("Result NR scenario does not match campaign configuration")
                if result["nr_condition"] != str(profile["nr_condition"]):
                    raise ValueError("Result NR condition does not match campaign configuration")
                if bool(int(float(result["shadowing"]))) != bool(profile["shadowing"]):
                    raise ValueError("Result shadowing mode does not match campaign configuration")
                for field, expected in {
                    "gnb_tx_power_dbm": float(profile["gnb_tx_power_dbm"]),
                    "ue_tx_power_dbm": float(profile["ue_tx_power_dbm"]),
                    "gnb_lateral_offset_m": float(profile["gnb_lateral_offset_m"]),
                    "channel_update_period_ms": float(
                        profile["channel_update_period_ms"]
                    ),
                }.items():
                    actual = float(result[field])
                    if not math.isfinite(actual) or not math.isclose(
                        actual, expected, rel_tol=0.0, abs_tol=1e-9
                    ):
                        raise ValueError(
                            f"Result {field}={actual} does not match campaign value {expected}"
                        )
                if int(float(result["num_gnbs"])) != int(profile["num_gnbs"]):
                    raise ValueError(
                        f"Result gNB count {result['num_gnbs']} does not match "
                        f"campaign count {profile['num_gnbs']}"
                    )
                if bool(int(float(result["guarded_corridor"]))) != bool(
                    profile["guarded_corridor"]
                ):
                    raise ValueError("Result guarded-corridor mode mismatch")
                if bool(int(float(result["enable_srs"]))) != bool(
                    profile["enable_srs"]
                ):
                    raise ValueError("Result SRS mode mismatch")
                if bool(profile["guarded_corridor"]):
                    speed_mps = speed / 3.6
                    spacing_m = float(profile["gnb_spacing_m"])
                    expected_timing = {
                        "distance_m": 0.0,
                        "app_start_s": 1.75 * spacing_m / speed_mps,
                        "app_stop_s": 3.75 * spacing_m / speed_mps,
                        "sim_time_s": 4.0 * spacing_m / speed_mps,
                    }
                    for field, expected in expected_timing.items():
                        actual = float(result[field])
                        if not math.isfinite(actual) or not math.isclose(
                            actual, expected, rel_tol=0.0, abs_tol=1e-6
                        ):
                            raise ValueError(
                                f"Result {field}={actual} does not match guarded "
                                f"corridor value {expected}"
                            )
                for field, expected in {
                    "gnb_height_m": float(profile["gnb_height_m"]),
                    "ue_height_m": float(profile["ue_height_m"]),
                }.items():
                    actual = float(result[field])
                    if not math.isfinite(actual) or not math.isclose(
                        actual, expected, rel_tol=0.0, abs_tol=1e-9
                    ):
                        raise ValueError(
                            f"Result {field}={actual} does not match "
                            f"campaign value {expected}"
                        )
                if bool(int(float(result["enable_handover"]))) != bool(
                    profile["enable_handover"]
                ):
                    raise ValueError("Result handover mode does not match campaign configuration")
                if bool(int(float(result["use_ideal_rrc"]))) != bool(
                    profile["use_ideal_rrc"]
                ):
                    raise ValueError("Result RRC mode does not match campaign configuration")
                if scenario == "repeater" and profile["passive_model"] == "component_budget":
                    expected_components = {
                        "feeder_loss_db": float(profile["feeder_cable_loss_db"]),
                        "coupling_loss_db": float(profile["coupling_loss_db"]),
                        "indoor_path_loss_db": float(profile["indoor_distrib_loss_db"]),
                        "donor_gain_dbi": float(profile["donor_gain_dbi"]),
                        "service_gain_dbi": float(profile["service_gain_dbi"]),
                    }
                    for field, expected in expected_components.items():
                        actual = float(result[field])
                        if not math.isfinite(actual) or not math.isclose(
                            actual, expected, rel_tol=0.0, abs_tol=1e-9
                        ):
                            raise ValueError(
                                f"Result {field}={actual} does not match "
                                f"campaign value {expected}"
                            )
                attempts = int(float(result["handover_attempts"]))
                successes = int(float(result["handover_successes"]))
                failures = int(float(result["handover_failures"]))
                if attempts != successes + failures:
                    raise ValueError(
                        "Handover accounting is inconsistent: "
                        f"{attempts} attempts != {successes} successes + {failures} failures"
                    )
                if bool(profile["enable_handover"]) and not (
                    run_output / "handover_events.csv"
                ).exists():
                    raise ValueError("Handover-enabled result is missing handover_events.csv")
                if bool(profile["enable_handover"]) and not (
                    run_output / "ue_serving_cells.csv"
                ).exists():
                    raise ValueError("Handover-enabled result is missing ue_serving_cells.csv")
                if bool(profile["enable_handover"]) and not (
                    run_output / "rsrp_measurements.csv"
                ).exists():
                    raise ValueError("Handover-enabled result is missing rsrp_measurements.csv")
                if not (run_output / "ue_metrics.csv").exists():
                    raise ValueError("Result is missing per-UE metrics")
                if not (run_output / "packet_receptions.csv").exists():
                    raise ValueError("Result is missing packet-level reception evidence")
                result.update(
                    {
                        "run_id": run_id,
                        "status": "ok",
                        "return_code": completed.returncode,
                        "raw_dir": str(run_output),
                        "error": "",
                    }
                )
                successful_rows.append(result)
                ledger.update(result)
                ledger["status"] = "ok"
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            ledger["error"] = str(exc)

        ledger_rows.append(ledger)

    # Keep the ledger column order deterministic.
    ledger_fields = [
        "run_id", "status", "return_code", "scenario", "speed_kmph", "distance_m",
        "num_ues", "gnb_height_m", "gnb_lateral_offset_m", "ue_height_m",
        "num_gnbs", "gnb_spacing_m", "guarded_corridor",
        "channel_update_period_ms", "sim_time_s", "app_start_s", "app_stop_s",
        "enable_srs",
        "enable_handover", "use_ideal_rrc",
        "handover_hysteresis_db", "handover_ttt_ms", "seed", "run",
        "declared_passive_loss_db", "raw_dir", "error", "passive_model",
        "traffic_direction", "nr_scenario", "nr_condition", "shadowing",
        "feeder_loss_db", "coupling_loss_db", "indoor_path_loss_db",
        "donor_gain_dbi", "service_gain_dbi", "network_loss_db",
        "aperture_gain_db", "eff_loss_db",
        "gnb_tx_power_dbm", "ue_tx_power_dbm",
        "effective_gnb_tx_power_dbm", "effective_ue_tx_power_dbm",
        "numerology", "scs_khz",
        "throughput_mbps", "p05_ue_throughput_mbps", "median_ue_throughput_mbps",
        "pdr", "tx_pkts", "rx_pkts", "mean_lat_ms", "p50_lat_ms",
        "p95_lat_ms", "jain_fairness", "handover_attempts", "handover_successes",
        "handover_failures", "mean_handover_duration_ms", "max_handover_duration_ms",
        "mean_application_gap_ms", "max_application_gap_ms",
        "bad_ipv4_length_drops",
        "short_transport_header_hash_events",
    ]
    for row in ledger_rows:
        for field in ledger_fields:
            row.setdefault(field, "")
    _write_csv(output_dir / "campaign_runs.csv", ledger_rows, ledger_fields)

    summaries = aggregate_rows(successful_rows)
    _write_summary(output_dir / "campaign_summary.csv", summaries)
    failed = sum(1 for row in ledger_rows if row["status"] == "failed")
    print(f"Campaign complete: {len(successful_rows)} succeeded, {failed} failed.")
    print(f"Run ledger: {output_dir / 'campaign_runs.csv'}")
    print(f"Summary:    {output_dir / 'campaign_summary.csv'}")
    return 1 if failed and not args.allow_failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns3", default="./ns3", help="Path to the ns-3 wrapper")
    parser.add_argument("--program", default="hsr_velocity_connect", help="Built ns-3 program name")
    parser.add_argument("--workdir", default=".", help="Working directory for the ns-3 wrapper")
    parser.add_argument("--out", default="out/campaign", help="Campaign output directory")
    parser.add_argument("--profile", choices=sorted(PROFILE_DEFAULTS), default="dev")
    parser.add_argument("--scenarios", default="metal,composite,repeater")
    parser.add_argument("--speeds", default="0,100,200,300,400,500")
    parser.add_argument("--distances", default="500")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--num-ues", type=int, default=None)
    parser.add_argument("--gnb-height-m", type=float, default=None)
    parser.add_argument("--gnb-lateral-offset-m", type=float, default=None)
    parser.add_argument("--ue-height-m", type=float, default=None)
    parser.add_argument("--num-ues-list", default="", help="Optional comma-separated UE counts")
    parser.add_argument("--numerology", type=int, default=None)
    parser.add_argument("--sim-time", type=float, default=None)
    parser.add_argument("--app-start", type=float, default=None)
    parser.add_argument("--app-stop", type=float, default=None)
    parser.add_argument("--channel-update-period-ms", type=float, default=None)
    parser.add_argument(
        "--enable-srs",
        type=lambda value: bool(int(value)),
        default=None,
    )
    parser.add_argument("--app-pkt-size", type=int, default=None)
    parser.add_argument("--saturating-load", type=lambda value: bool(int(value)), default=None)
    parser.add_argument("--per-ue-offered-mbps", type=float, default=None)
    parser.add_argument("--saturating-interval-us", type=float, default=None)
    parser.add_argument(
        "--traffic-direction",
        choices=("downlink", "uplink"),
        default=None,
    )
    parser.add_argument("--nr-scenario", default=None)
    parser.add_argument(
        "--nr-condition",
        choices=("LOS", "NLOS", "Default"),
        default=None,
    )
    parser.add_argument(
        "--shadowing",
        type=lambda value: bool(int(value)),
        default=None,
    )
    parser.add_argument(
        "--passive-model",
        choices=("component_budget", "declared_scalar", "legacy_scalar"),
        default=None,
    )
    parser.add_argument("--num-gnbs", type=int, default=None)
    parser.add_argument("--gnb-spacing-m", type=float, default=None)
    parser.add_argument(
        "--guarded-corridor",
        type=lambda value: bool(int(value)),
        default=None,
    )
    parser.add_argument(
        "--enable-handover",
        type=lambda value: bool(int(value)),
        default=None,
    )
    parser.add_argument("--handover-hysteresis-db", type=float, default=None)
    parser.add_argument("--handover-ttt-ms", type=int, default=None)
    parser.add_argument(
        "--use-ideal-rrc",
        type=lambda value: bool(int(value)),
        default=None,
    )
    parser.add_argument("--legacy-repeater-loss-db", type=float, default=None)
    parser.add_argument("--declared-passive-loss-db", type=float, default=None)
    parser.add_argument("--donor-gain-dbi", type=float, default=None)
    parser.add_argument("--service-gain-dbi", type=float, default=None)
    parser.add_argument("--feeder-cable-loss-db", type=float, default=None)
    parser.add_argument("--indoor-distrib-loss-db", type=float, default=None)
    parser.add_argument("--coupling-loss-db", type=float, default=None)
    parser.add_argument("--gnb-tx-power-dbm", type=float, default=None)
    parser.add_argument("--ue-tx-power-dbm", type=float, default=None)
    parser.add_argument("--run-base", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--max-runs", type=int, default=0, help="Guardrail; 0 means unlimited")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running NS-3")
    parser.add_argument("--allow-failures", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.num_ues is not None and args.num_ues < 1:
        parser.error("--num-ues must be at least 1")
    if args.gnb_height_m is not None and args.gnb_height_m <= 0:
        parser.error("--gnb-height-m must be positive")
    if args.ue_height_m is not None and args.ue_height_m <= 0:
        parser.error("--ue-height-m must be positive")
    if args.numerology is not None and not 0 <= args.numerology <= 5:
        parser.error("--numerology must be between 0 and 5")
    if args.num_gnbs is not None and args.num_gnbs < 1:
        parser.error("--num-gnbs must be at least 1")
    if args.gnb_spacing_m is not None and args.gnb_spacing_m <= 0:
        parser.error("--gnb-spacing-m must be positive")
    if args.handover_ttt_ms is not None and args.handover_ttt_ms < 0:
        parser.error("--handover-ttt-ms cannot be negative")
    if args.max_runs < 0:
        parser.error("--max-runs cannot be negative")
    try:
        return run_campaign(args)
    except ValueError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
