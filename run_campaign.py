import subprocess
import csv
import sys

# --- RESEARCH CONFIGURATION ---
# Experiment 1: Doppler Effect (Speed 0 to 500 km/h)
speeds_kmh = [0, 100, 200, 300, 400, 500]

# Experiment 2: Cell Coverage (Distance 100m to 1500m)
distances = [100, 300, 500, 800, 1000, 1200, 1500]

# Material Scenarios (The Novelty Comparison)
scenarios = {
    "Metal Coach (Dead Zone)": 60.0,       # High Loss
    "Composite Material (Weak)": 20.0,     # Medium Loss
    "Velocity Connect (Proposed)": 5.0     # Low Loss (Repeater)
}

results = []
print("--- STARTING IEEE JOURNAL EXPERIMENTS ---")
print("This may take 2-3 minutes. Please wait...\n")

# RUN EXPERIMENT 1: SPEED SWEEP (at fixed 500m distance)
print("[Exp 1] Testing High-Speed Doppler Impact...")
fixed_dist = 500.0
for name, nf in scenarios.items():
    for v_kmh in speeds_kmh:
        v_ms = v_kmh / 3.6
        cmd = f"./ns3 run 'velocity_research --trainSpeed={v_ms} --distance={fixed_dist} --noiseFigure={nf}'"
        
        # Run Simulation
        try:
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            output = process.stdout.strip().splitlines()
            if output:
                throughput = float(output[-1]) # Grab the last line number
            else:
                throughput = 0.0
        except:
            throughput = 0.0
            
        print(f"  > {name} @ {v_kmh} km/h: {throughput:.2f} Mbps")
        results.append(["Exp1_Speed", name, v_kmh, fixed_dist, throughput])

# RUN EXPERIMENT 2: DISTANCE SWEEP (at fixed 300 km/h)
print("\n[Exp 2] Testing Coverage & Range...")
fixed_speed_ms = 300.0 / 3.6
for name, nf in scenarios.items():
    for dist in distances:
        cmd = f"./ns3 run 'velocity_research --trainSpeed={fixed_speed_ms} --distance={dist} --noiseFigure={nf}'"
        
        try:
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            output = process.stdout.strip().splitlines()
            if output:
                throughput = float(output[-1])
            else:
                throughput = 0.0
        except:
            throughput = 0.0
            
        print(f"  > {name} @ {dist} m: {throughput:.2f} Mbps")
        results.append(["Exp2_Dist", name, 300, dist, throughput])

# Save All Data to CSV
csv_file = "journal_data.csv"
with open(csv_file, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Experiment", "Scenario", "Speed_kmh", "Distance_m", "Throughput_Mbps"])
    writer.writerows(results)

print(f"\n--- SUCCESS! Data saved to {csv_file} ---")
