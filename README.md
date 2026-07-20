# Velocity Connect

Velocity Connect is an NS-3 / 5G-LENA system-level simulation framework for evaluating passive in-coach relaying for 5G NR connectivity on high-speed railways.

The repository models three coach configurations:

- `metal`: 60 dB penetration loss
- `composite`: 20 dB penetration loss
- `repeater`: the proposed passive Velocity Connect link budget, approximately 5 dB with the default components

The simulator reports application-payload throughput, packet delivery ratio, mean/P50/P95 latency, and Jain fairness for multi-UE runs.

## What is new in the advanced workflow

The simulator now supports a parameterized single-run endpoint and an explicit paper profile:

```text
velocity_connect --singleRun=1 --scenario=repeater --speed=300 --distance=500 \
  --numUes=1 --seed=7 --run=11 --outDir=out/raw/example
```

It writes one machine-readable row to `single_run.csv`. `research_campaign.py` builds a scenario/speed/distance/UE-count/seed matrix, runs each configuration in an isolated output directory, preserves failures in a run ledger, and produces sample standard deviations and 95% confidence intervals.

## Requirements

- ns-3.46
- 5G-LENA NR `v4.1.1`
- Python 3.10 or newer for the campaign runner and tests

The ns-3 source tree and 5G-LENA are intentionally not vendored here. The validated local setup uses Ubuntu 22.04 under WSL with an ns-3.46 tree at `/home/codex/velocity-connect-ns3` and the application target `hsr_velocity_connect`.

The upstream compatibility pair is ns-3.46 with 5G-LENA NR `v4.1.1`. From WSL, configure and build it with:

```bash
cd /home/codex/velocity-connect-ns3
./ns3 configure --enable-examples --enable-tests

bash /mnt/c/Users/devel/OneDrive/Documents/Velocity-Connect/scripts/sync_wsl_ns3.sh
```

The sync script revision-checks the NR tree and applies the production portions
of CTTC upstream fixes `81892efa` (HARQ beam-order heap overflow) and `a1aa32c7`
(the symbol-budget defect tracked as
[5G-LENA issue #278](https://gitlab.com/cttc-lena/nr/-/work_items/278)),
copies the application sources into the NS-3 scratch tree, and builds the
target. It is idempotent. Use `--check-only` to inspect readiness without
changing the dependency.

## Reproducible campaign

From WSL, using the shared Windows checkout for campaign code and results:

```bash
python3 /mnt/c/Users/devel/OneDrive/Documents/Velocity-Connect/research_campaign.py \
  --ns3 /home/codex/velocity-connect-ns3/ns3 \
  --workdir /home/codex/velocity-connect-ns3 \
  --program hsr_velocity_connect \
  --scenarios metal,composite,repeater \
  --speeds 0,100,200,300,400,500 \
  --distances 500 \
  --seeds 1,2,3 \
  --out /mnt/c/Users/devel/OneDrive/Documents/Velocity-Connect/out/campaign
```

Use `--dry-run` to inspect the exact commands without spending simulation time. Use `--max-runs` as a guardrail for larger matrices. A nonzero exit code indicates at least one failed run unless `--allow-failures` is supplied.

Outputs:

```text
out/campaign/
├── campaign_config.json   # exact matrix and runner settings
├── campaign_runs.csv      # one row per attempt, including failures
├── campaign_summary.csv   # mean, sample SD, and 95% CI per metric
└── raw/<run-id>/single_run.csv
```

The summary intentionally ignores non-finite latency values when a run receives no valid timestamped packets; the run remains visible in `campaign_runs.csv`.

## Submitted-paper reproduction profile

`run_paper_campaign.py` runs the paper's three separate experiment families:

- speed: 0-500 km/h at 500 m, 10 UEs
- distance: 100-1500 m at 300 km/h, 10 UEs
- scalability: 10/20/30/40/50 UEs at 300 km/h and 500 m

The profile uses 3.5 GHz, 100 MHz, UMi LOS, shadowing disabled, 2 s simulation,
1024-byte UDP packets, 1 ms inter-packet spacing (8.19 Mbps/UE), and the
metal/composite/repeater loss cases from the paper.

```bash
python3 /mnt/c/Users/devel/OneDrive/Documents/Velocity-Connect/run_paper_campaign.py \
  --ns3 /home/codex/velocity-connect-ns3/ns3 \
  --workdir /home/codex/velocity-connect-ns3 \
  --out /mnt/c/Users/devel/OneDrive/Documents/Velocity-Connect/out/paper_campaign
```

Generate figures only from completed campaign summaries:

```bash
python3 plot_paper.py \
  --speed out/paper_campaign/speed \
  --distance out/paper_campaign/distance \
  --scalability out/paper_campaign/scalability \
  --out-dir out/paper_plots
```

The paper profile is an experiment contract, not a guarantee that a different
ns-3/5G-LENA build will reproduce every numeric value. A failed simulator run
stays in `campaign_runs.csv` and must be investigated before making a claim.

Before a full campaign, run the deterministic stability checkpoint:

```bash
python3 /mnt/c/Users/devel/OneDrive/Documents/Velocity-Connect/verify_paper_checkpoint.py \
  --out /mnt/c/Users/devel/OneDrive/Documents/Velocity-Connect/out/paper_checkpoint
```

This runs metal, composite, and repeater with 10 UEs at 500 km/h and 500 m,
then rejects failed or internally inconsistent results and writes
`paper_checkpoint_report.json`.

Completed checkpoints and their claim limits are recorded in `RESULTS.md`.

## Built-in sweeps

The original all-in-one sweeps remain available:

```bash
./ns3 run hsr_velocity_connect -- --doSpeed=1 --doDistance=1 --doScalability=1 --outDir=out
```

Disable individual sweeps for a shorter smoke run:

```powershell
./ns3 run hsr_velocity_connect -- --doSpeed=1 --doDistance=0 --doScalability=0 --simTime=0.5 --outDir=out/smoke
```

## Model configuration

The `paper` profile follows the submitted configuration:

- 3.5 GHz carrier, 100 MHz bandwidth, 30 kHz SCS
- 40 dBm gNB transmit power and 7 dB UE noise figure
- 3GPP UMi LOS channel with shadowing disabled
- UDP downlink, 1024-byte packets, 2 s simulation, 0.2 s application start
- proportional-fair NR scheduling and RLC UM

The default `dev` campaign remains a one-UE, saturating-load smoke profile so
fast checks do not accidentally consume the full paper matrix. Select the
paper contract with `--profile paper`.

For the repeater case, the effective loss is computed as:

```text
max(0, coupling + feeder + indoor - donor_gain - service_gain)
```

All of these terms are exposed as ns-3 command-line parameters. The single-run endpoint also accepts `--nrScenario`, `--nrCondition`, `--nrChannelModel`, `--shadowing`, `--scheduler`, `--gnbTxPowerDbm`, `--ueNoiseFigureDb`, and traffic controls.

## Tests

The campaign helper tests do not require NS-3:

```powershell
python -m unittest discover -s tests -v
```

Before making research claims, run the actual NS-3 campaign, retain `campaign_config.json` and `campaign_runs.csv`, and report the terminal simulator results. Plotting scripts are convenience visualization tools; they do not replace the raw run ledger or repeated-seed analysis.
