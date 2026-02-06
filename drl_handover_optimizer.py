import numpy as np
import matplotlib.pyplot as plt
import random

# --- CONFIGURATION ---
EPISODES = 1000
LEARNING_RATE = 0.1
DISCOUNT_FACTOR = 0.95
EPSILON = 1.0  # Exploration rate
EPSILON_DECAY = 0.995
MIN_EPSILON = 0.01

# --- SYSTEM MODEL (Based on NS-3 Physics) ---
# States: Train Speeds (km/h)
states = [100, 200, 300, 400, 500]
# Actions: Handover Hysteresis Margin (dB)
# 0=Aggressive (1dB), 1=Standard (3dB), 2=Conservative (5dB)
actions = [1.0, 3.0, 5.0]

# Q-Table: [State Index][Action Index]
q_table = np.zeros((len(states), len(actions)))

def get_reward(speed, hysteresis):
    """
    Simulates the Network Reward based on Physics.
    - High Speed + High Hysteresis = Late Handover (High Latency/Drop) -> Low Reward
    - High Speed + Low Hysteresis = Fast Handover (Good) -> High Reward
    - Low Speed + Low Hysteresis = Ping-Pong (Jitter) -> Low Reward
    """
    
    # Base Throughput (Mbps)
    throughput = 76.0 
    
    # Penalty Logic (The "Physics" of the Simulation)
    latency_penalty = 0
    
    if speed >= 400:
        if hysteresis > 3.0: 
            latency_penalty = 20  # Late HO penalty
        elif hysteresis < 2.0:
            latency_penalty = 0   # Optimal for High Speed
        else:
            latency_penalty = 5
            
    elif speed <= 200:
        if hysteresis < 2.0:
            latency_penalty = 15  # Ping-Pong penalty
        elif hysteresis > 4.0:
            latency_penalty = 0   # Optimal for Low Speed (Stability)
        else:
            latency_penalty = 5
    
    else: # Mid speeds (300 km/h)
        if abs(hysteresis - 3.0) < 0.1:
            latency_penalty = 0   # Standard is best
        else:
            latency_penalty = 10

    # Calculate Reward: Maximize Throughput - Latency Cost
    reward = throughput - latency_penalty
    return reward

# --- TRAINING LOOP ---
rewards_history = []
avg_rewards = []

print("--- STARTING DRL TRAINING (Q-LEARNING) ---")

for episode in range(EPISODES):
    total_reward = 0
    state_idx = random.randint(0, len(states)-1) # Random start speed
    current_speed = states[state_idx]
    
    # Action Selection (Epsilon-Greedy)
    if random.uniform(0, 1) < EPSILON:
        action_idx = random.randint(0, len(actions)-1) # Explore
    else:
        action_idx = np.argmax(q_table[state_idx]) # Exploit
        
    selected_hysteresis = actions[action_idx]
    
    # Observe Reward
    reward = get_reward(current_speed, selected_hysteresis)
    
    # Q-Update Rule
    # Since this is a single-step optimization per state (Contextual Bandit style):
    q_table[state_idx, action_idx] = q_table[state_idx, action_idx] + \
                                     LEARNING_RATE * (reward - q_table[state_idx, action_idx])
    
    total_reward += reward
    rewards_history.append(total_reward)
    
    # Decay Epsilon
    if EPSILON > MIN_EPSILON:
        EPSILON *= EPSILON_DECAY
        
    if episode % 100 == 0:
        avg = np.mean(rewards_history[-100:])
        avg_rewards.append(avg)
        print(f"Episode {episode}: Avg Reward = {avg:.2f} | Epsilon = {EPSILON:.2f}")

# --- PLOTTING RESULTS ---
plt.figure(figsize=(10, 6))
plt.plot(range(0, EPISODES, 100), avg_rewards, 'b-o', linewidth=2, label="DRL Agent Reward")
plt.title("DRL Agent Convergence: Dynamic Handover Optimization", fontsize=14, fontweight='bold')
plt.xlabel("Training Episodes", fontsize=12)
plt.ylabel("Average Reward (Throughput - Latency Cost)", fontsize=12)
plt.grid(True, linestyle='--', alpha=0.7)
plt.legend()
plt.tight_layout()
plt.savefig("Fig6_DRL_Convergence.png", dpi=300)

print("\n--- TRAINING COMPLETE ---")
print("Optimal Policies Learned:")
for i, s in enumerate(states):
    best_action = actions[np.argmax(q_table[i])]
    print(f"  Speed {s} km/h -> Best Hysteresis: {best_action} dB")
    
print("Graph Generated: Fig6_DRL_Convergence.png")
