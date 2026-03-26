# Velocity Connect: Passive In-Coach Relaying for 5G NR High-Speed Railway Evaluation

This repository contains the final reproducibility package for the paper:

**Passive In-Coach Relaying for 5G NR Connectivity in High-Speed Railways: A Reproducible System-Level Evaluation**

The code provides an ns-3 / 5G-LENA based system-level framework for evaluating in-coach 5G NR connectivity under coach penetration loss and high mobility. The final release focuses on three coach scenarios:

- metallic coach baseline
- composite coach baseline
- Velocity Connect passive in-coach relaying

---

## 1. What this repository provides

The repository includes:

- a reproducible ns-3 / 5G-LENA simulation setup for a single-cell high-speed railway downlink
- an effective-loss model for passive in-coach relaying
- a fixed-seed speed sweep at 500 m
- a multi-seed distance sweep at 300 km/h
- a scalability sweep with increasing UE count
- CSV logging for throughput, packet delivery ratio, latency and fairness
- plotting scripts used to regenerate the paper figures

---

## 2. Final paper configuration

The final paper results are based on the following configuration:

- Carrier frequency: 3.5 GHz
- Bandwidth: 100 MHz
- Subcarrier spacing: 30 kHz
- gNB transmit power: 40 dBm
- Traffic: UDP downlink
- Packet size: 1024 Bytes
- Offered load per UE: 8.19 Mbps
- Simulation time: 2 s
- Application start time: 0.5 s
- Channel model: 3GPP UMi street canyon
- LOS: enforced
- Shadowing: disabled
- Scheduler: `ns3::NrMacSchedulerOfdmaRR`
- RLC mode: UM

Coach assumptions used in the paper:

- metallic coach: 60 dB penetration loss
- composite coach: 20 dB penetration loss
- Velocity Connect: effective loss ≈ 5 dB

Velocity Connect effective-loss model:

\[
L_{\mathrm{eff}} = \max\left(0,\;L_{\mathrm{cable}} + L_{\mathrm{coupling}} + L_{\mathrm{indoor}} - (G_{\mathrm{donor}} + G_{\mathrm{service}})\right)
\]

Default component values:

- donor antenna gain = 8 dBi
- service antenna gain = 2 dBi
- feeder loss = 3 dB
- coupling / connector loss = 8 dB
- indoor distribution loss = 4 dB

---

## 3. Required simulator version

The final workflow was run with:

- ns-3.46
- 5G-LENA NR `5g-lena-v4.1.1`

---

## 4. Repository layout

```text
.
├── hsr_apps.h
├── hsr_io.h
├── hsr_nr.h
├── hsr_runner.h
├── hsr_stats.h
├── hsr_types.h
├── hsr_velocity_connect.cc
├── scripts
│   ├── run_hsr_campaign_singleproc.py
│   ├── run_distance_sweep_multiseed.py
│   ├── plot_hsr_results.py
│   └── plot_distance_multiseed.py
├── paper
│   ├── figures
│   └── results
├── legacy
└── README.md
