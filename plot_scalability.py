import matplotlib.pyplot as plt
import numpy as np

# Data from your simulation
users = [10, 20, 30, 40, 50]
throughput = [63.10, 126.16, 189.19, 248.85, 272.53]

# Ideal Linear Growth (Reference Line)
ideal = [x * (63.10/10) for x in users]

plt.figure(figsize=(10, 6))

# Plot Ideal vs Actual
plt.plot(users, ideal, 'k--', linewidth=1.5, label="Ideal Linear Scaling")
plt.plot(users, throughput, 'b-o', linewidth=3, markersize=10, label="Velocity Connect (Actual)")

# Fill area to show efficiency
plt.fill_between(users, throughput, color='blue', alpha=0.1)

# Styling
plt.title("System Scalability: Aggregate Throughput vs. User Load", fontsize=16, fontweight='bold')
plt.xlabel("Number of Active Users", fontsize=14)
plt.ylabel("Aggregate Throughput (Mbps)", fontsize=14)
plt.grid(True, which='both', linestyle='--', alpha=0.7)
plt.legend(fontsize=12)
plt.xticks(users)

# Annotation for Capacity
plt.annotate('Cell Capacity Saturation\n(~275 Mbps)', xy=(50, 272.5), xytext=(35, 200),
             arrowprops=dict(facecolor='red', shrink=0.05),
             fontsize=12, fontweight='bold', color='red')

plt.tight_layout()
plt.savefig("Fig7_Scalability_Analysis.png", dpi=300)
print("Graph Generated: Fig7_Scalability_Analysis.png")
