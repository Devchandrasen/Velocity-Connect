#!/usr/bin/env python3
"""Plot paper-profile campaign summaries without synthetic fallback data."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


SCENARIO_LABELS = {
    "metal": "Metal coach",
    "composite": "Composite coach",
    "repeater": "Velocity Connect",
}


def summary_path(value: str) -> Path:
    path = Path(value)
    if path.is_dir():
        path = path / "campaign_summary.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing campaign summary: {path}")
    return path


def load_summary(value: str) -> pd.DataFrame:
    frame = pd.read_csv(summary_path(value))
    required = {
        "scenario", "speed_kmph", "distance_m", "num_ues",
        "throughput_mbps_mean", "throughput_mbps_ci95",
        "pdr_mean", "pdr_ci95", "mean_lat_ms_mean", "mean_lat_ms_ci95",
        "jain_fairness_mean", "jain_fairness_ci95",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Summary is missing required columns: {missing}")
    frame = frame.copy()
    frame["label"] = frame["scenario"].map(SCENARIO_LABELS).fillna(frame["scenario"])
    return frame


def plot_metric(frame: pd.DataFrame, x: str, metric: str, ylabel: str, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.3))
    for label, group in frame.groupby("label", sort=False):
        group = group.sort_values(x)
        mean = group[f"{metric}_mean"]
        ci = group[f"{metric}_ci95"].fillna(0.0)
        ax.plot(group[x], mean, marker="o", linewidth=2, label=label)
        ax.fill_between(group[x], mean - ci, mean + ci, alpha=0.15)
    ax.set_xlabel("Train speed (km/h)" if x == "speed_kmph" else "Distance (m)")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=240)
    plt.close(fig)


def plot_scalability(frame: pd.DataFrame, output_dir: Path) -> None:
    frame = frame.sort_values("num_ues")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.1))
    axes[0].plot(frame["num_ues"], frame["throughput_mbps_mean"], marker="o")
    axes[0].fill_between(
        frame["num_ues"],
        frame["throughput_mbps_mean"] - frame["throughput_mbps_ci95"].fillna(0.0),
        frame["throughput_mbps_mean"] + frame["throughput_mbps_ci95"].fillna(0.0),
        alpha=0.15,
    )
    axes[0].set_xlabel("Number of UEs")
    axes[0].set_ylabel("Aggregate throughput (Mbps)")
    axes[1].plot(frame["num_ues"], frame["jain_fairness_mean"], marker="o")
    axes[1].fill_between(
        frame["num_ues"],
        frame["jain_fairness_mean"] - frame["jain_fairness_ci95"].fillna(0.0),
        frame["num_ues"] * 0 + frame["jain_fairness_mean"] + frame["jain_fairness_ci95"].fillna(0.0),
        alpha=0.15,
    )
    axes[1].set_xlabel("Number of UEs")
    axes[1].set_ylabel("Jain fairness")
    for ax in axes:
        ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "scalability.png", dpi=240)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", required=True, help="Speed-family output directory or campaign_summary.csv")
    parser.add_argument("--distance", required=True, help="Distance-family output directory or campaign_summary.csv")
    parser.add_argument("--scalability", required=True, help="Scalability-family output directory or campaign_summary.csv")
    parser.add_argument("--out-dir", default="out/paper_plots")
    args = parser.parse_args()

    sns.set_theme(style="whitegrid", context="paper")
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    speed = load_summary(args.speed)
    distance = load_summary(args.distance)
    scalability = load_summary(args.scalability)

    plot_metric(speed, "speed_kmph", "throughput_mbps", "Application throughput (Mbps)", output_dir / "speed_throughput.png")
    plot_metric(speed, "speed_kmph", "pdr", "Packet delivery ratio", output_dir / "speed_pdr.png")
    plot_metric(speed, "speed_kmph", "mean_lat_ms", "Mean one-way latency (ms)", output_dir / "speed_latency.png")
    plot_metric(distance, "distance_m", "throughput_mbps", "Application throughput (Mbps)", output_dir / "distance_throughput.png")
    plot_metric(distance, "distance_m", "pdr", "Packet delivery ratio", output_dir / "distance_pdr.png")
    plot_metric(distance, "distance_m", "mean_lat_ms", "Mean one-way latency (ms)", output_dir / "distance_latency.png")
    plot_scalability(scalability, output_dir)
    print(f"Wrote paper-profile plots to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
