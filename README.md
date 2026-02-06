# ns3-5g-hsr-velocity-connect

NS-3 (5G-LENA NR) reproducible simulation framework for evaluating **5G NR connectivity inside High-Speed Railway (HSR) coaches** under **vehicle penetration loss (VPL)** and **high mobility (Doppler)**, including the proposed **Velocity Connect** passive relaying architecture and an optional **tabular Q-learning** mobility-tuning workflow.

---

## What this repository provides

This project contains:
- A clean **system-level** NS-3/5G-LENA setup (EPC + NR stack) for an HSR corridor
- Three coach scenarios: **metal**, **composite**, **Velocity Connect (passive relay)**
- Parametric sweeps:
  - **Speed sweep** (0–500 km/h) at fixed distance
  - **Distance sweep** (100–1500 m) at fixed speed
  - **Scalability sweep** (UE load) with aggregate throughput + fairness
- CSV logging for:
  - UE/application throughput (Mbps)
  - Packet Delivery Ratio (PDR)
  - One-way application latency (mean, P95) over successfully received packets
  - Optional debug breakdown of the passive loss budget (`--verbose=1`)
- Plot scripts to regenerate all figures used in the paper

---

## Key modelling choices (paper-consistent)

### Coach scenarios
- **Metal coach:** penetration loss = **60 dB**
- **Composite coach:** penetration loss = **20 dB**
- **Velocity Connect (passive relaying):** effective loss ≈ **5 dB**

### Velocity Connect effective loss model
The passive path is mapped to an equivalent loss:
\[
L_{\mathrm{eff}} = \max\left(0,\; L_{\mathrm{cable}} + L_{\mathrm{coupling}} + L_{\mathrm{indoor}} - (G_{\mathrm{donor}} + G_{\mathrm{service}})\right)
\]

Default component values (used to reach ≈ 5 dB):
- Donor antenna gain: **8 dBi**
- Service antenna gain: **2 dBi**
- Feeder/cable insertion loss: **3 dB**
- Connector/coupling loss: **8 dB**
- Indoor distribution loss: **4 dB**

### Radio + traffic configuration
- Carrier: **3.5 GHz** (FR1, n78)
- Bandwidth: **100 MHz**
- Subcarrier spacing: **30 kHz**
- Scheduler: **PF (Proportional Fair)**
- RLC mode: **UM**
- HARQ: **Enabled** (Stop-and-Wait)
- Channel: **3GPP UMi-Street Canyon**
- Condition: **LOS enforced**
- Shadowing: **disabled** (to isolate VPL and mobility trends)
- Traffic: **UDP downlink**
  - Packet size: **1024 Bytes**
  - Inter-packet interval: **1 ms**
  - Offered rate per UE ≈ **8.19 Mbps**

---

## Repository layout (typical)

