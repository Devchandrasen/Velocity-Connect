import matplotlib.pyplot as plt
import numpy as np

# --- DATA CONFIGURATION ---
labels = ['Throughput', 'Low Latency', 'Energy Efficiency', 'Cost Effectiveness', 'Simplicity']
num_vars = len(labels)

# Scores (0 to 10 scale, where 10 is BEST)
# Velocity Connect: High Throughput, Best Latency, Zero Power (Best EE), Low Cost, Simple
velocity_scores = [9, 10, 10, 9, 9]

# Active Relay: High Throughput, Med Latency (Processing), High Power (Bad EE), Expensive
active_scores = [9, 6, 2, 3, 4]

# LEO Satellite: Med Throughput, Poor Latency, Med Power, Very Expensive
satellite_scores = [6, 2, 5, 2, 8]

# --- PLOTTING LOGIC ---
angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
angles += angles[:1] # Close the loop

# Close the data loops
velocity_scores += velocity_scores[:1]
active_scores += active_scores[:1]
satellite_scores += satellite_scores[:1]

fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

# Plot Velocity Connect
ax.plot(angles, velocity_scores, color='green', linewidth=3, label='Velocity Connect (Proposed)')
ax.fill(angles, velocity_scores, color='green', alpha=0.15)

# Plot Active Relay
ax.plot(angles, active_scores, color='red', linewidth=2, linestyle='dashed', label='Active Mobile Relay')
ax.fill(angles, active_scores, color='red', alpha=0.05)

# Plot Satellite
ax.plot(angles, satellite_scores, color='blue', linewidth=2, linestyle='dotted', label='LEO Satellite (STIN)')
ax.fill(angles, satellite_scores, color='blue', alpha=0.05)

# Formatting
ax.set_theta_offset(np.pi / 2)
ax.set_theta_direction(-1)
ax.set_xticks(angles[:-1])
ax.set_xticklabels(labels, size=12, weight='bold')

# Y-Axis Labels (Hide generic numbers, use qualitative)
ax.set_rlabel_position(0)
plt.yticks([2, 4, 6, 8, 10], ["2", "4", "6", "8", "10"], color="grey", size=10)
plt.ylim(0, 10)

plt.title("Multi-Dimensional Performance Comparison", size=16, weight='bold', y=1.05)
plt.legend(loc='lower right', bbox_to_anchor=(1.3, 0.0))

plt.tight_layout()
plt.savefig("Fig8_Radar_Comparison.png", dpi=300)
print("Graph Generated: Fig8_Radar_Comparison.png")
