import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load the Research Data
try:
    df = pd.read_csv("journal_data.csv")
except:
    print("Error: Could not find 'journal_data.csv'. Run the campaign script first!")
    exit()

# Set IEEE Paper Style
sns.set_style("whitegrid")
sns.set_context("paper", font_scale=1.4)
colors = ["#d62728", "#ff7f0e", "#2ca02c"] # Red, Orange, Green

# --- FIGURE 1: SPEED ANALYSIS ---
plt.figure(figsize=(10, 6))
exp1 = df[df["Experiment"] == "Exp1_Speed"]
sns.lineplot(data=exp1, x="Speed_kmh", y="Throughput_Mbps", hue="Scenario", 
             style="Scenario", palette=colors, markers=True, markersize=9, linewidth=2.5)

plt.title("Impact of Train Speed on Throughput (Doppler Effect)", fontweight='bold')
plt.xlabel("Train Speed (km/h)")
plt.ylabel("Throughput (Mbps)")
plt.ylim(-5, 100)
plt.legend(title="Configuration", loc="lower left")
plt.savefig("Fig1_Doppler_Analysis.png", dpi=300, bbox_inches='tight')
print("Generated Fig1_Doppler_Analysis.png")

# --- FIGURE 2: COVERAGE ANALYSIS ---
plt.figure(figsize=(10, 6))
exp2 = df[df["Experiment"] == "Exp2_Dist"]
sns.lineplot(data=exp2, x="Distance_m", y="Throughput_Mbps", hue="Scenario", 
             style="Scenario", palette=colors, markers=True, markersize=9, linewidth=2.5)

plt.title("Coverage Analysis at 300 km/h (Path Loss)", fontweight='bold')
plt.xlabel("Distance from Tower (m)")
plt.ylabel("Throughput (Mbps)")
plt.ylim(-5, 100)
plt.legend(title="Configuration", loc="upper right")
plt.savefig("Fig2_Coverage_Analysis.png", dpi=300, bbox_inches='tight')
print("Generated Fig2_Coverage_Analysis.png")
