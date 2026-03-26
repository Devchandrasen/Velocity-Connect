import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# Load Data
filename = "advanced_results.csv"
try:
    df = pd.read_csv(filename)
except:
    # Fallback if file read fails (using your manual data)
    data = {
        "Scenario": ["Metal Coach"]*5 + ["Velocity Connect"]*5,
        "Speed_kmh": [100, 200, 300, 400, 500]*2,
        "Latency_ms": [20.92, 23.93, 21.43, 26.93, 25.92, 
                       1.68, 1.75, 1.68, 1.70, 1.69]
    }
    df = pd.DataFrame(data)

# Separate Data
metal = df[df["Scenario"].str.contains("Metal")]
velocity = df[df["Scenario"].str.contains("Velocity")]

# Plotting
plt.figure(figsize=(10, 6))

# Plot Lines
plt.plot(metal["Speed_kmh"], metal["Latency_ms"], 'r-o', linewidth=3, markersize=10, label="Metal Coach (Baseline)")
plt.plot(velocity["Speed_kmh"], velocity["Latency_ms"], 'g-s', linewidth=3, markersize=10, label="Velocity Connect (Proposed)")

# Styling
plt.title("End-to-End Latency vs. Train Speed", fontsize=16, fontweight='bold')
plt.xlabel("Train Velocity (km/h)", fontsize=14)
plt.ylabel("Average Latency (ms)", fontsize=14)
plt.grid(True, which='both', linestyle='--', alpha=0.7)
plt.legend(fontsize=12)
plt.ylim(0, 30)

# Annotation for Impact
plt.annotate('12x Latency Reduction', xy=(300, 1.7), xytext=(320, 10),
             arrowprops=dict(facecolor='black', shrink=0.05),
             fontsize=12, fontweight='bold', color='green')

plt.tight_layout()
plt.savefig("Fig5_Latency_Analysis.png", dpi=300)
print("Graph Generated: Fig5_Latency_Analysis.png")
