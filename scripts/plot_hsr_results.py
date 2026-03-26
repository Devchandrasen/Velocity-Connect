import os
import argparse
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

def plot_lines(df, xcol, ycol, title, xlabel, ylabel, outpath):
    plt.figure(figsize=(8, 5))
    for scenario in ["metal", "composite", "repeater"]:
        sdf = df[df["scenario"] == scenario].copy()
        if len(sdf) == 0:
            continue
        sdf = sdf.sort_values(xcol)
        plt.plot(sdf[xcol], sdf[ycol], marker="o", label=nice_label(scenario))
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(outpath, dpi=300)
    plt.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    ensure_dir(args.outdir)

    speed_csv = os.path.join(args.indir, "sweep_speed.csv")
    dist_csv = os.path.join(args.indir, "sweep_distance.csv")
    scal_csv = os.path.join(args.indir, "sweep_scalability.csv")

    if os.path.exists(speed_csv):
        df = pd.read_csv(speed_csv)
        plot_lines(
            df, "speed_kmph", "throughput_mbps",
            "Throughput vs Speed at 500 m",
            "Train speed (km/h)", "Throughput (Mbps)",
            os.path.join(args.outdir, "speed_throughput.png")
        )
        plot_lines(
            df, "speed_kmph", "pdr",
            "PDR vs Speed at 500 m",
            "Train speed (km/h)", "Packet delivery ratio",
            os.path.join(args.outdir, "speed_pdr.png")
        )
        plot_lines(
            df, "speed_kmph", "mean_lat_ms",
            "Latency vs Speed at 500 m",
            "Train speed (km/h)", "Mean latency (ms)",
            os.path.join(args.outdir, "speed_latency.png")
        )

    if os.path.exists(dist_csv):
        df = pd.read_csv(dist_csv)
        plot_lines(
            df, "distance_m", "throughput_mbps",
            "Throughput vs Distance at 300 km/h",
            "Distance (m)", "Throughput (Mbps)",
            os.path.join(args.outdir, "distance_throughput.png")
        )
        plot_lines(
            df, "distance_m", "pdr",
            "PDR vs Distance at 300 km/h",
            "Distance (m)", "Packet delivery ratio",
            os.path.join(args.outdir, "distance_pdr.png")
        )
        plot_lines(
            df, "distance_m", "mean_lat_ms",
            "Latency vs Distance at 300 km/h",
            "Distance (m)", "Mean latency (ms)",
            os.path.join(args.outdir, "distance_latency.png")
        )

    if os.path.exists(scal_csv):
        df = pd.read_csv(scal_csv)

        throughput_col = "aggregate_throughput_mbps" if "aggregate_throughput_mbps" in df.columns else "throughput_mbps"

        plt.figure(figsize=(8, 5))
        plt.plot(df["num_ues"], df[throughput_col], marker="o")
        plt.title("Aggregate Throughput vs Number of UEs")
        plt.xlabel("Number of UEs")
        plt.ylabel("Aggregate throughput (Mbps)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(args.outdir, "scalability_throughput.png"), dpi=300)
        plt.close()

        if "jain_fairness" in df.columns:
            plt.figure(figsize=(8, 5))
            plt.plot(df["num_ues"], df["jain_fairness"], marker="o")
            plt.title("Jain Fairness vs Number of UEs")
            plt.xlabel("Number of UEs")
            plt.ylabel("Jain fairness index")
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(os.path.join(args.outdir, "scalability_fairness.png"), dpi=300)
            plt.close()

    print("Plots saved in:", args.outdir)

if __name__ == "__main__":
    main()
