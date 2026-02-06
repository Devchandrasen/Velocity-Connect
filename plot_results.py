import os
import pandas as pd
import matplotlib.pyplot as plt

OUT = "out"
FIG = "fig"
os.makedirs(FIG, exist_ok=True)

def savefig(name):
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, name + ".png"), dpi=300)
    plt.savefig(os.path.join(FIG, name + ".pdf"))
    plt.close()

def plot_speed():
    path = os.path.join(OUT, "sweep_speed.csv")
    df = pd.read_csv(path)

    plt.figure()
    for scen in ["metal", "composite", "repeater"]:
        d = df[df["scenario"] == scen].sort_values("speed_kmph")
        plt.plot(d["speed_kmph"], d["throughput_mbps"], marker="o", label=scen)
    plt.xlabel("Train speed (km/h)")
    plt.ylabel("Throughput (Mbps)")
    plt.title("Throughput vs Speed (single UE, saturation)")
    plt.legend()
    savefig("Fig1_Throughput_vs_Speed")

    # Also PDR
    plt.figure()
    for scen in ["metal", "composite", "repeater"]:
        d = df[df["scenario"] == scen].sort_values("speed_kmph")
        plt.plot(d["speed_kmph"], d["pdr"], marker="o", label=scen)
    plt.xlabel("Train speed (km/h)")
    plt.ylabel("Packet delivery ratio (PDR)")
    plt.title("PDR vs Speed (delivery conditioning)")
    plt.legend()
    savefig("Fig1b_PDR_vs_Speed")

    # Latency (mean and p95) for delivered packets
    plt.figure()
    for scen in ["metal", "composite", "repeater"]:
        d = df[df["scenario"] == scen].sort_values("speed_kmph")
        plt.plot(d["speed_kmph"], d["mean_lat_ms"], marker="o", label=f"{scen} mean")
        plt.plot(d["speed_kmph"], d["p95_lat_ms"], marker="x", linestyle="--", label=f"{scen} p95")
    plt.xlabel("Train speed (km/h)")
    plt.ylabel("Latency (ms) [delivered packets only]")
    plt.title("Latency vs Speed (delivered packets)")
    plt.legend(ncol=2)
    savefig("Fig5_Latency_vs_Speed")

def plot_distance():
    path = os.path.join(OUT, "sweep_distance.csv")
    df = pd.read_csv(path)

    plt.figure()
    for scen in ["metal", "composite", "repeater"]:
        d = df[df["scenario"] == scen].sort_values("distance_m")
        plt.plot(d["distance_m"], d["throughput_mbps"], marker="o", label=scen)
    plt.xlabel("Distance from gNB (m)")
    plt.ylabel("Throughput (Mbps)")
    plt.title("Throughput vs Distance (single UE, saturation)")
    plt.legend()
    savefig("Fig2_Throughput_vs_Distance")

    plt.figure()
    for scen in ["metal", "composite", "repeater"]:
        d = df[df["scenario"] == scen].sort_values("distance_m")
        plt.plot(d["distance_m"], d["pdr"], marker="o", label=scen)
    plt.xlabel("Distance from gNB (m)")
    plt.ylabel("Packet delivery ratio (PDR)")
    plt.title("PDR vs Distance")
    plt.legend()
    savefig("Fig2b_PDR_vs_Distance")

def plot_scalability():
    path = os.path.join(OUT, "scalability.csv")
    df = pd.read_csv(path).sort_values("num_ues")

    plt.figure()
    plt.plot(df["num_ues"], df["aggregate_throughput_mbps"], marker="o", label="Actual")
    # Ideal linear scaling line (up to max shown)
    ideal = df["num_ues"] * df["per_ue_offered_mbps"].iloc[0]
    plt.plot(df["num_ues"], ideal, linestyle="--", label="Ideal (sum offered)")
    plt.xlabel("Number of active UEs")
    plt.ylabel("Aggregate throughput (Mbps)")
    plt.title("Aggregate Throughput vs User Load")
    plt.legend()
    savefig("Fig7_Scalability")

    plt.figure()
    plt.plot(df["num_ues"], df["jain_fairness"], marker="o")
    plt.xlabel("Number of active UEs")
    plt.ylabel("Jain fairness index")
    plt.title("Fairness vs User Load")
    savefig("Fig7b_Fairness")

def plot_drl():
    rpath = os.path.join(OUT, "drl_reward.csv")
    ppath = os.path.join(OUT, "drl_policy.csv")
    epath = os.path.join(OUT, "drl_eval.csv")

    if not os.path.exists(rpath):
        return

    df = pd.read_csv(rpath)
    plt.figure()
    plt.plot(df["episode"], df["reward"])
    plt.xlabel("Training episode")
    plt.ylabel("Reward")
    plt.title("Q-learning Convergence (Reward vs Episode)")
    savefig("Fig6_DRL_Reward")

    pol = pd.read_csv(ppath)
    print("\nLearned policy (speed -> hyst):")
    print(pol)

    ev = pd.read_csv(epath)
    # Compare learned vs baseline throughput and latency
    plt.figure()
    for mode in ["baseline", "learned"]:
        d = ev[ev["mode"] == mode].sort_values("speed_kmph")
        plt.plot(d["speed_kmph"], d["throughput_mbps"], marker="o", label=mode)
    plt.xlabel("Speed (km/h)")
    plt.ylabel("Throughput (Mbps)")
    plt.title("Baseline vs Learned Policy: Throughput")
    plt.legend()
    savefig("Fig6b_DRL_Throughput_Compare")

    plt.figure()
    for mode in ["baseline", "learned"]:
        d = ev[ev["mode"] == mode].sort_values("speed_kmph")
        plt.plot(d["speed_kmph"], d["mean_lat_ms"], marker="o", label=mode)
    plt.xlabel("Speed (km/h)")
    plt.ylabel("Mean latency (ms)")
    plt.title("Baseline vs Learned Policy: Latency")
    plt.legend()
    savefig("Fig6c_DRL_Latency_Compare")

def main():
    plot_speed()
    plot_distance()
    plot_scalability()
    plot_drl()
    print(f"\nFigures saved under ./{FIG}/")

if __name__ == "__main__":
    main()
