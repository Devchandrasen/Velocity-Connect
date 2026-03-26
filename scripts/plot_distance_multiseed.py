import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def nice_label(x):
    return {
        "metal": "Metal coach",
        "composite": "Composite coach",
        "repeater": "Velocity Connect",
    }.get(x, x)

def plot_metric(df, mean_col, ci_col, ylabel, title, outpath):
    plt.figure(figsize=(8, 5))

    for scenario in ["metal", "composite", "repeater"]:
        sdf = df[df["scenario"] == scenario].copy()
        if len(sdf) == 0:
            continue
        sdf = sdf.sort_values("distance_m")

        y = sdf[mean_col]
        yerr = sdf[ci_col].fillna(0)

        mask = y.notna()
        plt.errorbar(
            sdf.loc[mask, "distance_m"],
            y.loc[mask],
            yerr=yerr.loc[mask],
            marker="o",
            capsize=3,
            label=nice_label(scenario),
        )

    plt.title(title)
    plt.xlabel("Distance (m)")
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(outpath, dpi=300)
    plt.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    ensure_dir(args.outdir)
    df = pd.read_csv(args.summary)

    plot_metric(
        df,
        "throughput_mbps_mean",
        "throughput_mbps_ci95",
        "Throughput (Mbps)",
        "Throughput vs Distance (mean ± 95% CI)",
        os.path.join(args.outdir, "distance_throughput_mean_ci.png"),
    )

    plot_metric(
        df,
        "pdr_mean",
        "pdr_ci95",
        "PDR",
        "PDR vs Distance (mean ± 95% CI)",
        os.path.join(args.outdir, "distance_pdr_mean_ci.png"),
    )

    plot_metric(
        df,
        "mean_lat_ms_mean",
        "mean_lat_ms_ci95",
        "Latency (ms)",
        "Latency vs Distance (mean ± 95% CI)",
        os.path.join(args.outdir, "distance_latency_mean_ci.png"),
    )

    print("Plots saved in:", args.outdir)

if __name__ == "__main__":
    main()
