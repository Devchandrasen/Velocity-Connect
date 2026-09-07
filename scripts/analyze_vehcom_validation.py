#!/usr/bin/env python3
"""Fail-closed analysis of complete VehCom plans; no survivor-only summaries."""
from __future__ import annotations

import argparse
from collections import defaultdict
import math
from pathlib import Path
import statistics
import sys

import numpy as np
from scipy.stats import chi2

try:
    from . import run_vehcom_validation as campaign
except ImportError:  # Direct CLI execution.
    import run_vehcom_validation as campaign


def poisson_bounds(count, exposure, confidence=0.95):
    """Garwood rate bounds, conditional on a homogeneous Poisson count model.

    Return both equal-tailed two-sided CI and one-sided upper bound. For zero
    events these are -ln(alpha/2)/exposure and -ln(alpha)/exposure respectively.
    They are not evidence that repeated handovers really form a Poisson process.
    """
    if isinstance(count, bool) or not math.isfinite(count) or count < 0 or int(count) != count:
        raise ValueError("Poisson count must be a nonnegative integer")
    if not math.isfinite(exposure) or exposure <= 0 or not 0 < confidence < 1:
        raise ValueError("Invalid exposure or confidence")
    alpha = 1 - confidence
    return {"count": int(count), "exposure_ue_km": exposure, "rate_per_ue_km": count / exposure,
            "two_sided_low": 0.0 if count == 0 else float(chi2.ppf(alpha / 2, 2 * count) / (2 * exposure)),
            "two_sided_high": float(chi2.ppf(1 - alpha / 2, 2 * (count + 1)) / (2 * exposure)),
            "one_sided_upper": float(chi2.ppf(confidence, 2 * (count + 1)) / (2 * exposure)),
            "confidence": confidence, "model": "homogeneous Poisson assumption; not verified"}


def paired_bootstrap(differences, *, seed, resamples=20000):
    if resamples != 20000:
        raise ValueError("Protocol fixes 20,000 bootstrap resamples")
    n = len(differences)
    undefined = sum(x is None for x in differences)
    result = {"n_pairs": n, "valid_pairs": n - undefined, "undefined_pairs": undefined, "resamples": resamples,
              "mean_difference": None, "median_difference": None,
              "ci95_low": None, "ci95_high": None, "unit": "matched seed/run block (run-pair), not packets"}
    if undefined or n == 0:
        result["status"] = "undefined; no available-case substitution"
        return result
    values = np.asarray(differences, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Bootstrap differences must be finite or explicitly undefined")
    result.update(mean_difference=float(values.mean()), median_difference=float(np.median(values)))
    if n < 2:
        result["status"] = "insufficient run-pairs for interval"
        return result
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    # Resample paired differences, never packets or individual treatment runs.
    for start in range(0, resamples, 1000):
        indices = rng.integers(0, n, size=(min(1000, resamples - start), n))
        means[start:start + len(indices)] = values[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    result.update(ci95_low=float(low), ci95_high=float(high), status="percentile bootstrap; pointwise exploratory interval")
    return result


def continuity(path, *, ues, direction, start, stop, threshold_ms, scales):
    """Streaming receive-gap diagnostics; unserved edges are not internal events."""
    if ues < 1 or stop <= start or threshold_ms <= 0 or any(s <= 0 for s in scales):
        raise ValueError("Invalid continuity configuration")
    first, last = {}, {}
    counts = {str(scale): 0 for scale in scales}
    excess = {str(scale): 0.0 for scale in scales}
    maximum, packets = 0.0, 0
    per_ue = defaultdict(int)
    for record in campaign.read_csv(path, ("ue_index", "traffic_direction", "receive_time_s", "latency_ms")):
        ue = campaign.number(record["ue_index"], "ue_index", integer=True)
        time = campaign.number(record["receive_time_s"], "receive_time_s")
        campaign.number(record["latency_ms"], "latency_ms")
        if ue >= ues or record["traffic_direction"] != direction or not start - 1e-8 <= time <= stop + 1e-8:
            raise ValueError("Reception outside planned UE/direction/window")
        time = min(stop, max(start, time))
        if ue in last:
            if time < last[ue]:
                raise ValueError("Reception times not ordered within UE")
            gap = (time - last[ue]) * 1000
            maximum = max(maximum, gap)
            for scale in scales:
                threshold = threshold_ms * scale
                if gap > threshold + 1e-7:
                    counts[str(scale)] += 1
                    excess[str(scale)] += gap - threshold
        else:
            first[ue] = time
        last[ue] = time
        packets += 1
        per_ue[ue] += 1
    edges = 0.0
    for ue in range(ues):
        if ue in first:
            left, right = (first[ue] - start) * 1000, (stop - last[ue]) * 1000
            edges += left + right
            maximum = max(maximum, left, right)
        else:
            edges += (stop - start) * 1000
            maximum = max(maximum, (stop - start) * 1000)
    return {"rx_pkts": packets, "per_ue_rx": dict(per_ue),
            "zero_reception_ues": ues - len(first), "maximum_receive_gap_ms": maximum,
            "unserved_edge_ms": edges, "internal_gap_counts": counts,
            "internal_gap_excess_ms": excess}


def handovers(path, *, start, stop, guarded, ping_pong_window_s):
    successes = failures = attempts = ping_pongs = 0
    previous = {}
    last_start = {}
    for r in campaign.read_csv(path, ("imsi", "source_cell_id", "target_cell_id", "start_time_s",
                                     "end_time_s", "success", "completed")):
        imsi = campaign.number(r["imsi"], "imsi", integer=True)
        t = campaign.number(r["start_time_s"], "start_time_s")
        success, completed = int(r["success"]), int(r["completed"])
        if success not in (0, 1) or completed not in (0, 1):
            raise ValueError("Invalid handover boolean")
        if guarded and not start - 1e-8 <= t < stop:
            raise ValueError("Handover outside guarded window")
        if t < last_start.get(imsi, -math.inf):
            raise ValueError("Handover traces not ordered within IMSI")
        last_start[imsi] = t
        attempts += 1
        if success and completed:
            end = campaign.number(r["end_time_s"], "end_time_s")
            if end < t:
                raise ValueError("Handover end precedes start")
            prior = previous.get(imsi)
            if prior and (r["source_cell_id"], r["target_cell_id"]) == (prior["target_cell_id"], prior["source_cell_id"]):
                delay = t - float(prior["end_time_s"])
                if 0 <= delay <= ping_pong_window_s:
                    ping_pongs += 1
            previous[imsi] = r
            successes += 1
        else:
            failures += 1
            # A failed attempt breaks the consecutive-success transition sequence.
            previous.pop(imsi, None)
    return dict(handover_attempts=attempts, handover_successes=successes,
                handover_failures=failures, ping_pongs=ping_pongs)


def analyze_row(root, plan, row, terminal):
    raw = campaign.contained(root, "raw/" + row["row_id"])
    for name, expected in terminal.get("log_sha256", {}).items():
        if campaign.sha256(campaign.contained(root, name)) != expected:
            raise ValueError(f"Execution log changed: {row['row_id']}/{name}")
    if not set(campaign.RAW_FILES) <= set(terminal.get("raw_sha256", {})):
        raise ValueError("Successful ledger row lacks complete raw hashes")
    for name, expected in terminal["raw_sha256"].items():
        if campaign.sha256(campaign.contained(raw, name)) != expected:
            raise ValueError(f"Raw evidence changed: {row['row_id']}/{name}")
    metrics = campaign.validate_result(raw, row)
    options, config = row["options"], plan["analysis"]
    start, stop, ues = options["appStart"], options["appStop"], options["numUes"]
    route_km = (stop - start) * options["speed"] / 3600
    if not math.isclose(route_km, row["planned_active_km"], abs_tol=1e-10):
        raise ValueError("Exposure differs from plan")
    ue_km = route_km * ues
    traces = continuity(raw / "packet_receptions.csv", ues=ues, direction=options["trafficDirection"],
                        start=start, stop=stop, threshold_ms=config["gap_threshold_ms"],
                        scales=config["threshold_multipliers"])
    if traces["rx_pkts"] != metrics["rx_pkts"]:
        raise ValueError("Trace reception count does not match aggregate")
    ue_records = list(campaign.read_csv(raw / "ue_metrics.csv", ("ue_index", "traffic_direction", "tx_pkts", "rx_pkts", "throughput_mbps", "pdr", "mean_lat_ms", "p95_lat_ms")))
    if len(ue_records) != ues or {int(r["ue_index"]) for r in ue_records} != set(range(ues)):
        raise ValueError("Incomplete or duplicate UE metrics")
    tx_sum = 0
    for r in ue_records:
        ue = int(r["ue_index"])
        tx = campaign.number(r["tx_pkts"], "UE tx", integer=True)
        rx = campaign.number(r["rx_pkts"], "UE rx", integer=True)
        if r["traffic_direction"] != options["trafficDirection"] or rx != traces["per_ue_rx"].get(ue, 0) or rx > tx or tx == 0:
            raise ValueError("UE packet/direction mismatch")
        if not math.isclose(float(r["pdr"]), rx / tx, abs_tol=2e-9):
            raise ValueError("UE PDR inconsistent")
        if rx:
            campaign.number(r["mean_lat_ms"], "UE mean latency")
            campaign.number(r["p95_lat_ms"], "UE tail latency")
        tx_sum += tx
    if tx_sum != metrics["tx_pkts"]:
        raise ValueError("UE TX sum inconsistent")
    ho = handovers(raw / "handover_events.csv", start=start, stop=stop,
                   guarded=bool(options["guardedCorridor"]), ping_pong_window_s=config["ping_pong_window_s"])
    for key in ("handover_attempts", "handover_successes", "handover_failures"):
        if ho[key] != metrics[key]:
            raise ValueError(f"Handover trace/counter mismatch: {key}")
    # Offered CLI rate includes the 12-byte measurement header; delivered goodput excludes it.
    aggregate_offered = options["perUeOfferedMbps"] * ues
    payload_fraction = (options["appPktSize"] - 12) / options["appPktSize"]
    payload_offered = aggregate_offered * payload_fraction
    observed_offered = metrics["tx_pkts"] * options["appPktSize"] * 8 / (stop - start) / 1e6
    # Send scheduling rounds to integer nanoseconds and the first send is one interval late.
    tolerance = ues * options["appPktSize"] * 8 / (stop - start) / 1e6 + aggregate_offered * 1e-5
    if abs(observed_offered - aggregate_offered) > tolerance:
        raise ValueError("Observed TX rate inconsistent with planned offered load")
    ratio = metrics["throughput_mbps"] / payload_offered
    metrics.update(maximum_receive_gap_ms=traces["maximum_receive_gap_ms"],
                   unserved_edge_ms=traces["unserved_edge_ms"],
                   handover_failures_per_ue_km=ho["handover_failures"] / ue_km if ue_km else None,
                   ping_pongs_per_ue_km=ho["ping_pongs"] / ue_km if ue_km else None,
                   payload_delivery_to_offered_ratio=ratio)
    sensitivity = {}
    base_components = {"packet_loss": 1 - metrics["pdr"], "tail_latency_ms": metrics["p95_lat_ms"],
                       "receive_gap_ms": traces["maximum_receive_gap_ms"],
                       "ping_pongs_per_ue_km": metrics["ping_pongs_per_ue_km"],
                       "handover_failures_per_ue_km": metrics["handover_failures_per_ue_km"]}
    for scale in config["threshold_multipliers"]:
        components = {key: None if value is None else value / (config["reference_scales"][key] * scale)
                      for key, value in base_components.items()}
        worst = None if any(v is None for v in components.values()) else max(components.values())
        sensitivity[str(scale)] = {"reference_multiplier": scale, "normalized_components": components,
                                  "worst_normalized_score": worst,
                                  "exceeds_reference": None if worst is None else worst > 1,
                                  "gap_threshold_ms": config["gap_threshold_ms"] * scale,
                                  "internal_gap_count": traces["internal_gap_counts"][str(scale)],
                                  "internal_gap_excess_ms": traces["internal_gap_excess_ms"][str(scale)]}
        metrics[f"internal_gaps_scale_{scale}_per_ue_km"] = traces["internal_gap_counts"][str(scale)] / ue_km if ue_km else None
        metrics[f"worst_normalized_score_scale_{scale}"] = worst
    return {**{k: row[k] for k in ("row_id", "pair_id", "cell_id", "treatment", "seed", "run")},
            "status": terminal["status"], "binary_sha256": terminal["binary_sha256"],
            "source_bundle_sha256": terminal["source_bundle_sha256"],
            "active_route_km": route_km, "active_ue_km": ue_km, "metrics": metrics,
            "measurement_window": {"start_s": start, "stop_s": stop,
                                   "start_x_m": options["distance"] + start * options["speed"] / 3.6,
                                   "stop_x_m": options["distance"] + stop * options["speed"] / 3.6,
                                   "endpoint_rule": "application active [start, stop); trace rounding tolerance 1e-8 s",
                                   "spatial_direction": "positive-x only; no reverse-track claim" if route_km else "static; zero route exposure",
                                   "traffic_direction": options["trafficDirection"],
                                   "edge_rule": "unserved edges retained separately, excluded from internal event rates"},
            "options": options, "threshold_sensitivity": sensitivity,
            "event_counts": {"handover_failures": ho["handover_failures"], "ping_pongs": ho["ping_pongs"],
                             **{f"internal_gaps_scale_{k}": v for k, v in traces["internal_gap_counts"].items()}},
            "load": {"aggregate_offered_mbps_header_included": aggregate_offered,
                     "aggregate_payload_offered_mbps": payload_offered,
                     "observed_tx_mbps_header_included": observed_offered,
                     "offered_load_limited_flag": ratio >= config["saturation_fraction"],
                     "unmet_offered_load_possible_saturation_flag": ratio < config["saturation_fraction"],
                     "interpretation": "Near offered ceiling does not measure capacity; unmet load may be loss or saturation, not a proven bottleneck."},
            "zero_reception_ues": traces["zero_reception_ues"],
            "no_reception_run": metrics["rx_pkts"] == 0}


def paired_contrasts(records, bootstrap_seed=20260907):
    groups = defaultdict(dict)
    cells = defaultdict(list)
    for record in records:
        key = (record["cell_id"], record["pair_id"])
        if record["treatment"] in groups[key]:
            raise ValueError("Duplicate pair treatment")
        groups[key][record["treatment"]] = record
    for (cell, pair), treatments in groups.items():
        if "direct_composite" not in treatments or len(treatments) < 2:
            raise ValueError("Unmatched pair: missing direct or comparison treatment")
        direct = treatments["direct_composite"]
        for other in treatments.values():
            for key in ("seed", "run", "cell_id", "pair_id", "binary_sha256", "source_bundle_sha256"):
                if direct[key] != other[key]:
                    raise ValueError(f"Unmatched identifiers: {key}")
            # Treatment-specific bridge controls may differ, all experimental cell controls may not.
            for control in campaign.CSV_CONTROL:
                if control not in {"scenario", "passiveModel"} and direct["options"][control] != other["options"][control]:
                    raise ValueError(f"Unmatched cell control: {control}")
            for control in ("perUeOfferedMbps", "appPktSize", "saturatingLoad"):
                if direct["options"][control] != other["options"][control]:
                    raise ValueError(f"Unmatched load control: {control}")
        cells[cell].append((pair, treatments))
    results = []
    for cell, pairs in sorted(cells.items()):
        pairs.sort(key=lambda p: p[0])
        treatment_sets = {tuple(sorted(t)) for _, t in pairs}
        if len(treatment_sets) != 1:
            raise ValueError("Missing treatment in a run-pair; no intersection-only pairing")
        for treatment in sorted(pairs[0][1]):
            if treatment == "direct_composite":
                continue
            metric_names = sorted(pairs[0][1][treatment]["metrics"])
            pair_differences = []
            for pair, t in pairs:
                direct, other = t["direct_composite"], t[treatment]
                delta = {}
                for metric in metric_names:
                    left, right = direct["metrics"][metric], other["metrics"][metric]
                    delta[metric] = None if left is None or right is None else right - left
                pair_differences.append({"pair_id": pair, "seed": direct["seed"], "run": direct["run"],
                                         "differences": delta})
            estimates = {}
            for metric in metric_names:
                seed = int(campaign.digest([bootstrap_seed, cell, treatment, metric])[:16], 16)
                estimates[metric] = paired_bootstrap([p["differences"][metric] for p in pair_differences], seed=seed)
            results.append({"cell_id": cell, "contrast": f"{treatment} minus direct_composite",
                            "pairing": "identifier-matched only; matched channel streams unproven",
                            "run_pair_differences": pair_differences, "estimates": estimates})
    return results


def describe_all(values):
    """An undefined member makes the group estimator undefined; never filter it out."""
    missing = sum(v is None for v in values)
    base = {"n_runs": len(values), "undefined_runs": missing, "mean": None, "median": None,
            "sample_sd": None, "minimum": None, "maximum": None}
    if missing or not values:
        return base
    base.update(mean=statistics.mean(values), median=statistics.median(values),
                sample_sd=statistics.stdev(values) if len(values) > 1 else None,
                minimum=min(values), maximum=max(values))
    return base


def analyze_campaign(root):
    plan = campaign.load_plan(root)
    states = campaign.read_ledger(root, plan)
    audit = campaign.status_report(plan, states)
    report = {"audit": audit, "profile": plan["profile"], "evidence_boundary": campaign.BOUNDARY,
              "statistics": None, "provenance": plan["provenance"], "analysis_protocol": plan["analysis"],
              "ledger_sha256": campaign.sha256(Path(root) / "ledger.jsonl"),
              "analysis_code_sha256": campaign.sha256(__file__),
              "all_outcomes": [{"row_id": r["row_id"], **states[r["row_id"]]} for r in plan["rows"]]}
    if audit["campaign_status"] != "succeeded":
        report["reason"] = "No statistical summaries: every predetermined row must succeed. Failure and unfinished evidence retained."
        return report
    records = [analyze_row(root, plan, row, states[row["row_id"]]) for row in plan["rows"]]
    if campaign.sha256(Path(root) / "ledger.jsonl") != report["ledger_sha256"]:
        raise ValueError("Ledger changed during analysis")
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["cell_id"], record["treatment"])].append(record)
    groups = []
    for (cell, treatment), runs in sorted(grouped.items()):
        exposure = sum(r["active_ue_km"] for r in runs)
        groups.append({"cell_id": cell, "treatment": treatment, "n_runs": len(runs),
                       "total_route_km": sum(r["active_route_km"] for r in runs), "total_ue_km": exposure,
                       "completed_valid_route_km": sum(r["active_route_km"] for r in runs),
                       "principal_40km_exposure_met": (sum(r["active_route_km"] for r in runs) >= 40 - 1e-8)
                       if cell.startswith("principal-") else None,
                       "metrics": {key: describe_all([r["metrics"][key] for r in runs]) for key in runs[0]["metrics"]},
                       "poisson_rates": {key: poisson_bounds(sum(r["event_counts"][key] for r in runs), exposure) if exposure else None
                                         for key in runs[0]["event_counts"]},
                       "zero_reception_runs": sum(r["no_reception_run"] for r in runs),
                       "offered_load_limited_runs": sum(r["load"]["offered_load_limited_flag"] for r in runs),
                       "unmet_offered_load_runs": sum(r["load"]["unmet_offered_load_possible_saturation_flag"] for r in runs)})
    report["statistics"] = {"runs": records, "groups": groups,
                            "paired_contrasts": paired_contrasts(records, plan["analysis"]["bootstrap_seed"]),
                            "limitations": ["No packets-as-replicates; bootstrap resamples whole run-pairs.",
                                            "Pointwise exploratory intervals; no multiplicity-controlled superiority claim.",
                                            "Poisson process assumption unverified; clustered events may invalidate coverage.",
                                            "No available-case latency summaries; undefined is not zero.",
                                            "Reference-scale sensitivity is engineering convention, not calibrated thresholds or standards.",
                                            "No cross-channel pairing: different channel cells have fresh identifiers."]}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New JSON file; never overwrite a previous report")
    args = parser.parse_args(argv)
    try:
        report = analyze_campaign(args.campaign)
        campaign.write_json_new(args.output, report)
        print(f"{report['audit']['campaign_status']}: {args.output}")
        return 0 if report["statistics"] is not None else 2
    except (OSError, ValueError, KeyError) as exc:
        print(f"vehcom analysis refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
