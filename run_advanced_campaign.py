import subprocess
import csv
import sys

# --- IEEE TWC EXPERIMENT CONFIGURATION ---
speeds_kmh = [100, 200, 300, 400, 500]

scenarios = {
    "Metal Coach (Baseline)": 60.0,       # High Noise (Faraday Cage)
    "Velocity Connect (Proposed)": 5.0    # Low Noise (Repeater)
}

results = []

print("--- STARTING ADVANCED LATENCY & HANDOVER CAMPAIGN ---")
print(f"Testing Speeds: {speeds_kmh} km/h")
print("-----------------------------------------------------")

for name, nf in scenarios.items():
    print(f"\nScenario: {name}")
    for v_kmh in speeds_kmh:
        # Construct the command
        cmd = f"./ns3 run 'velocity_handover --trainSpeed={v_kmh} --noiseFigure={nf}'"
        
        print(f"  > Running at {v_kmh} km/h...", end=" ", flush=True)
        
        try:
            # Run NS-3
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            # The C++ code outputs: Latency,Jitter,LostPackets,Throughput
            # We grab the last line of the output
            output_lines = process.stdout.strip().splitlines()
            
            if output_lines:
                last_line = output_lines[-1]
                # Parse CSV format from C++
                data = last_line.split(',')
                
                if len(data) >= 4:
                    latency = float(data[0])
                    jitter = float(data[1])
                    loss = int(data[2])
                    throughput = float(data[3])
                else:
                    # Fallback if output is garbage
                    latency, jitter, loss, throughput = 0.0, 0.0, 0, 0.0
            else:
                 latency, jitter, loss, throughput = 0.0, 0.0, 0, 0.0

        except Exception as e:
            print(f"Error: {e}")
            latency, jitter, loss, throughput = 0.0, 0.0, 0, 0.0
            
        # Log to console
        print(f"Latency: {latency:.2f} ms | Loss: {loss} pkts")
        
        # Save to list
        results.append([name, v_kmh, latency, jitter, loss, throughput])

# Save to CSV
csv_filename = "advanced_results.csv"
with open(csv_filename, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Scenario", "Speed_kmh", "Latency_ms", "Jitter_ms", "PacketLoss", "Throughput_Mbps"])
    writer.writerows(results)

print(f"\n--- CAMPAIGN COMPLETE. Data saved to {csv_filename} ---")
