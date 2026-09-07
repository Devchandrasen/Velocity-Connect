# Velocity Connect

Velocity Connect is a fail-closed ns-3/5G-LENA and HFSS research workflow for
testing the **conditional feasibility** of a passive roof-to-cabin RF
feedthrough for 5G NR high-speed-rail connectivity. It deliberately keeps
three evidence classes separate:

- radiator coupons and guided four-ports are solved separately, not as a complete
  donor-feeder-service product;
- the moving network experiment uses reciprocal scalar-loss hypotheses, while
  an optional static interface imports complex transfers with explicit external
  coupling operators; and
- hardware, coach, route, and moving-train validation remain external gates.

This GitHub repository is implementation-only. It contains executable source,
tests, pinned dependency metadata, selected native HFSS projects, and compact
machine-readable fixtures. Manuscript sources, generated PDFs and figures,
bulk solver trees, patent material, and local campaign outputs are excluded.
Start with [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for the clean-clone gates.

## Revision 05 implementation

The opt-in `em_complex` channel evaluates the actual V4/V5 four-port matrices
per resource block, including coherent direct/passive addition and reciprocal
single-stream projections. It requires explicit absolute external operators and
rejects motion, missing coupling inputs and unsupported geometries. It is a
static software interface, not a railway channel or full MIMO implementation.
See the [interface contract and tests](reproducibility/em_bridge_v1_audit.md).

A [frozen validation driver](reproducibility/vehcom_campaign_protocol.md) adds
matched run identities, complete-ledger analysis, threshold sensitivity and
separate principal/load/channel profiles. Those expanded profiles are plans,
not completed scientific results. Short integration checks use synthetic
external operators and must not be interpreted as device performance.

HFSS power auditing checks raw powers and convergence without clipping.
The stricter radiation-boundary diagnostic still exceeds the passive power
bound; absolute efficiency and gain remain inadmissible. See [RESULTS.md](RESULTS.md).

The repository models three coach configurations:

- `metal`: a 60 dB scalar penetration comparator;
- `composite`: a 20 dB scalar penetration comparator; and
- `repeater`: a declared total passive-path loss (6.5 dB in the principal
  transaction contract, with separate 1.5-26 dB sensitivity points).

The simulator reports application-payload throughput, packet delivery ratio,
mean/P50/P95 latency, Jain fairness, and—on corridor runs—A3-RSRP/X2 handover
events, success/failure, protocol duration, application packet gaps, serving
cell changes, and RSRP measurement reports.

## Canonical transaction-v3 workflow

The submission workflow is pinned to:

- ns-3.48 commit `d2add90b452d600cfb4859baed8e9ea633519447`;
- 5G-LENA v5.0 commit `47a3adc263f773556eaadac5a5341458dbc61c47`;
- Ubuntu 22.04 directly or under WSL2; and
- 64-bit CPython 3.12.10 on Windows for frozen analysis and packaging.

Bootstrap and sync the pinned simulator:

```bash
bash scripts/bootstrap_ns3_v5.sh "$HOME/ns-3.48-velocity-connect" "$PWD"
bash scripts/sync_wsl_ns3_v5.sh --check-only \
  "$HOME/ns-3.48-velocity-connect" "$PWD"
```

Run the guarded 816-run contract:

```bash
cd "$HOME/ns-3.48-velocity-connect"
bash velocity_connect_tools/run_transaction_campaigns_v7.sh
```

The contract contains six gNBs, a 10 m track offset, a fixed
1.75-3.75-ISD interior measurement window, a 4-ISD simulation stop, 5 ms
channel updates, non-ideal RRC, all-flexible dynamic TDD, SRS disabled as a
declared limitation, DL/UL traffic, 300-500 km/h, 300-800 m ISD, and 1-16 UEs.
The A3 screen uses development seeds only for selection and reserves separate
simulator seeds for a nonconfirmatory secondary audit.

Run the separate 60-run declared-loss sweep and the official 5G-LENA gate only
after the main campaign is terminal:

```bash
bash velocity_connect_tools/run_publication_loss_sweep_v7.sh
bash velocity_connect_tools/run_official_test_gate_v5.sh
```

The official gate covers dynamic-TDD pattern generation plus the pinned X2,
handover-delay, handover-scenario, measurement, and interference suites. See
`REPRODUCIBILITY.md` for the clean-machine build and verification contract.

The simulator also supports a parameterized single-run endpoint:

```text
velocity_connect --singleRun=1 --scenario=repeater --speed=300 --distance=500 \
  --numUes=1 --seed=7 --run=11 --outDir=out/raw/example
```

It writes one machine-readable row to `single_run.csv`.
`research_campaign.py` builds a scenario/speed/distance/UE-count/seed matrix,
runs each configuration in an isolated output directory, preserves failures
in a run ledger, and produces sample standard deviations and 95% confidence
intervals.

## Requirements

- Linux campaign runtime: Python 3.10.12, CMake 3.22.1, g++ 11.4.0.
- Windows analysis runtime: CPython 3.12.10, 64-bit, pip 26.2, hash-locked
  dependencies.
- HFSS re-solving: compatible licensed AEDT. The repository includes selected
  native projects and compact four-port exports, but no licence and no measured
  product.

The current v5.0 campaign records two upstream applicability audits. The
v5.1-development handover-RACH fix does not alter this homogeneous contract
because all gNBs use identical RACH defaults. The v5.0 FDD/NLOS patch warning
does not apply to the one-BWP all-flexible TDD setup. Neither assessment
extends the claim to heterogeneous RACH or FDD.

Run the current project tests with the exact Windows environment:

```powershell
py -3.12 -m venv .venv-reproduction
.\.venv-reproduction\Scripts\python.exe -m pip install -r environment\requirements-lock.txt
.\.venv-reproduction\Scripts\python.exe scripts\verify_source_manifest.py
.\.venv-reproduction\Scripts\python.exe -m pytest -q
```

## Legacy and generic campaign utilities

The sections below document older ns-3.46/5G-LENA v4.1.1 and generic
development workflows retained for provenance. They are **not** the
transaction-v3 submission evidence and must not be mixed with it.

From Linux or WSL, using paths chosen by the operator:

```bash
python3 research_campaign.py \
  --ns3 "$HOME/ns-3.48-velocity-connect/ns3" \
  --workdir "$HOME/ns-3.48-velocity-connect" \
  --program hsr_velocity_connect \
  --scenarios metal,composite,repeater \
  --speeds 0,100,200,300,400,500 \
  --distances 500 \
  --seeds 1,2,3 \
  --out out/campaign
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

## Legacy single-cell reproduction profile

`run_paper_campaign.py` runs the paper's three separate experiment families:

- speed: 0-500 km/h at 500 m, 10 UEs
- distance: 100-1500 m at 300 km/h, 10 UEs
- scalability: 10/20/30/40/50 UEs at 300 km/h and 500 m

The profile uses 3.5 GHz, 100 MHz, numerology 1 (30 kHz SCS), UMi LOS,
shadowing disabled, 2 s simulation, 1024-byte UDP packets, 1 ms inter-packet
spacing (8.19 Mbps/UE), and the metal/composite/repeater loss cases from the
paper. Numerology is applied explicitly to the gNB PHY; 5G-LENA propagates it
to attached UEs. Every raw result row records both `numerology` and `scs_khz`.

```bash
python3 run_paper_campaign.py \
  --ns3 "$HOME/ns-3.48-velocity-connect/ns3" \
  --workdir "$HOME/ns-3.48-velocity-connect" \
  --out out/legacy_single_cell
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
python3 verify_paper_checkpoint.py \
  --ns3 "$HOME/ns-3.48-velocity-connect/ns3" \
  --workdir "$HOME/ns-3.48-velocity-connect" \
  --out out/legacy_checkpoint
```

This runs metal, composite, and repeater with 10 UEs at 500 km/h and 500 m,
then rejects failed, internally inconsistent, or non-30-kHz results and writes
`paper_checkpoint_report.json`.

Completed checkpoints and their claim limits are recorded in `RESULTS.md`.

## Advanced multi-cell corridor

The rejected-paper profile remains a one-cell `legacy_scalar` baseline. New
work uses the `corridor` profile and `component_budget` model:

```bash
python3 run_corridor_campaign.py \
  --ns3 "$HOME/ns-3.48-velocity-connect/ns3" \
  --workdir "$HOME/ns-3.48-velocity-connect" \
  --out out/corridor-smoke \
  --scenarios repeater \
  --speeds 500 \
  --seeds 1,2,3 \
  --num-ues 1 \
  --sim-time 13 \
  --max-runs 3
```

5G-LENA v4.1.1 corridor runs are currently validated with ideal RRC. The
recorded A3/X2 events and application packet gaps are simulator evidence;
ideal-RRC protocol duration is not a real signalling-delay claim.

Use the stricter bounded checkpoint before accepting the corridor capability:

```bash
python3 verify_corridor_checkpoint.py \
  --ns3 "$HOME/ns-3.48-velocity-connect/ns3" \
  --workdir "$HOME/ns-3.48-velocity-connect" \
  --out out/corridor_checkpoint
```

Every seed must contain a completed handover, a serving-cell change, and a
neighbour-RSRP trigger record. Passing it is still not OTA, hardware,
random-access, or field validation.

## Measurement-calibrated component budget

Copy `measurement_template.csv`, replace the header-only file with calibrated
VNA/OTA rows, then run:

```bash
python3 calibrate_passive_model.py measured_passive_components.csv \
  --out out/passive-calibration
```

Each calibrated row includes ready-to-pass `campaign_arguments`; those
arguments are accepted by `research_campaign.py` and
`run_corridor_campaign.py`. The summary uses a two-sided 95% Student-t
interval, including for small measurement sets.

The calibration pipeline contains no synthetic measurements. It rejects
positive passive S21, non-finite values, and unsupported net-gain budgets.
See `EXPERIMENT_PROTOCOL.md`.

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

The `paper` compatibility profile follows the legacy single-cell configuration:

- 3.5 GHz carrier, 100 MHz bandwidth, 30 kHz SCS
- 40 dBm gNB transmit power and 7 dB UE noise figure
- 3GPP UMi LOS channel with shadowing disabled
- UDP downlink, 1024-byte packets, 2 s simulation, 0.2 s application start
- proportional-fair NR scheduling and RLC UM

The default `dev` campaign remains a one-UE, saturating-load smoke profile so
fast checks do not accidentally consume the full legacy matrix. Select the
compatibility contract with `--profile paper`.

For the new component-budget repeater case, the effective loss is computed as:

```text
coupling + feeder + indoor - donor_gain - service_gain
```

Indoor loss appears exactly once, and invalid negative equivalent loss is
rejected rather than silently clamped. All terms are exposed as ns-3
command-line parameters. The single-run
endpoint also accepts `--numerology`, `--nrScenario`, `--nrCondition`,
`--nrChannelModel`, `--shadowing`, `--scheduler`, `--gnbTxPowerDbm`,
`--ueNoiseFigureDb`, and traffic controls.

## Tests

### Revision 06 validation work

The revision adds a same-excitation HFSS power-budget audit and an offline replay
of its retained numerical failure. The raw native efficiencies in that
**simulation export**, not a physical measurement, remain above 100%; the
implementation does not clip them or substitute a more favorable denominator.

```powershell
python hfss/replay_power_budget_revision06.py
```

See [the power correction protocol](reproducibility/revision06_power_plan.md),
[the serial campaign launcher](reproducibility/vehcom_revision06_execution.md),
and [the moving-link data admission contract](calibration/README.md).
The launcher separates the fixed 680-run expansion from resource-only pilots
and software tests. The data contract checks completeness and integrity but
does not certify measurements, fit a channel or enable moving EM coupling.
These additions do not establish calibrated railway performance or submission
readiness. Earlier accepted scalar results remain separate and unchanged.
The [Revision 06 status record](reproducibility/REVISION06_STATUS.md) distinguishes
the completed audit, interrupted refinements, running queue and unresolved data.

### CPU-only checks

The CPU-only implementation tests do not require ns-3 or HFSS:

```powershell
python scripts\verify_source_manifest.py
python -m pytest -q
```

Before making research claims, run the actual NS-3 campaign, retain `campaign_config.json` and `campaign_runs.csv`, and report the terminal simulator results. Plotting scripts are convenience visualization tools; they do not replace the raw run ledger or repeated-seed analysis.
