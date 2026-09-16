# Experiment reference

This reference describes the public experiment surfaces in Velocity Connect.
Use each command with `--help` for its complete option list and current defaults.

## Simulator entry point

The ns-3 program is `hsr_velocity_connect`. Its parameterized mode writes one
machine-readable result row:

```text
velocity_connect --singleRun=1 --scenario=repeater --speed=300 --distance=500 \
  --numUes=1 --seed=7 --run=11 --outDir=out/raw/example
```

### Scenarios

| Value | Meaning |
|---|---|
| `metal` | 60 dB scalar vehicle penetration comparator |
| `composite` | 20 dB scalar vehicle penetration comparator |
| `repeater` | passive feedthrough scenario using the selected passive model |

### Passive models

| Value | Required inputs | Scope |
|---|---|---|
| `legacy_scalar` | `legacyRepeaterLossDb` | historical compatibility |
| `declared_scalar` | `declaredPassiveLossDb` | moving reciprocal scalar hypothesis |
| `component_budget` | gains and feeder/coupling/indoor losses | moving scalar equivalent loss |
| `em_complex` | `.s4p`, external operator file, mapping | static single-stream validation |

The component budget is:

```text
equivalent loss = feeder + coupling + indoor - donor gain - service gain
```

Negative equivalent loss is rejected. The implementation does not silently
clamp a passive system into net gain.

### Network controls

The main controls cover carrier and bandwidth configuration, numerology,
channel model, LOS/NLOS condition, shadowing, scheduler, gNB and UE transmit
power, train speed, gNB spacing, UE count, channel update period, traffic
direction, offered load, A3 hysteresis, A3 time to trigger, and ideal/non-ideal
RRC selection.

The exact C++ option names are registered in `hsr_velocity_connect.cc`.

## Generic campaign runner

```text
python research_campaign.py [options]
```

### Profiles

| Profile | Purpose |
|---|---|
| `dev` | short one-UE development smoke |
| `paper` | retained legacy single-cell paper configuration |
| `corridor` | multi-cell railway corridor with mobility controls |

### Matrix controls

`--scenarios`, `--speeds`, `--distances`, `--seeds`, and
`--num-ues-list` define the experiment matrix. `--max-runs` is an operational
guardrail. `--dry-run` prints commands without starting ns-3.

### Outputs

| File | Contents |
|---|---|
| `campaign_config.json` | exact matrix and runner settings |
| `campaign_runs.csv` | one row per attempted run, including failures |
| `campaign_summary.csv` | grouped means, sample standard deviations, and 95 percent confidence intervals |
| `raw/<run-id>/single_run.csv` | simulator output for one isolated run |

Non-finite latency is excluded from latency aggregation when no timestamped
packet is received. The failed run remains visible in the attempt ledger.

## Frozen validation driver

```text
python scripts/run_vehcom_validation.py {inspect,plan,run,status} ...
```

| Command | Behavior |
|---|---|
| `inspect` | verifies binary, source, and dependency pins |
| `plan` | creates an immutable predeclared run plan |
| `run` | executes unattempted rows with append-only status records |
| `status` | reports plan and ledger state without simulation |

Terminal failures are not retried. Crash recovery requires explicit operator
action and still does not relaunch an already attempted scientific identity.

## Revision 06 resource-guarded launcher

```text
python scripts/run_vehcom_revision06.py \
  {prepare,resource-pilot,inspect,status,admit,run} ...
```

`prepare`, `inspect`, `status`, and `admit` do not simulate. `run` requires the
explicit `--execute` flag and finite row/time limits. The resource pilot has
separate identities and cannot be pooled with scientific evidence.

## Calibration commands

### Component-budget calibration

```text
python calibrate_passive_model.py measured_passive_components.csv \
  --out out/passive-calibration
```

The input must follow `measurement_template.csv`. The command rejects empty
data, non-finite values, positive passive S21, and unsupported net-gain budgets.

### Moving-link data admission

`calibration/measurement_contract.py` checks a supplied bundle against the
schema in [calibration/README.md](../calibration/README.md). Admission proves
format, integrity, and declared coverage. It does not prove calibration quality
or enable the moving complex channel by itself.

## HFSS command families

| Command family | Purpose |
|---|---|
| `hfss/build_n78_*.py` | parameterized n78 antenna geometry and solve setup |
| `hfss/build_ptf_v4_feedthrough.py` | balanced four-port feedthrough |
| `hfss/ptf_v5_delay25ps_*.py` | physical-delay four-port construction and export |
| `hfss/audit_radiator_power.py` | fail-closed native radiator audit |
| `hfss/export_power_budget_revision06.py` | same-excitation power and field export |
| `hfss/replay_power_budget_revision06.py` | offline replay of retained power evidence |

HFSS scripts require the version and licence described in
[hfss/README.md](../hfss/README.md). The committed fixtures support software
checks but do not replace a solver run.

## Reported metrics

The simulator can report application-payload throughput, packet delivery
ratio, mean/P50/P95 latency, Jain fairness, packet gaps, A3 measurement events,
handover attempts, successes, failures, protocol duration, serving-cell
changes, and RSRP reports. Availability depends on the selected profile and
traffic direction.

Read [Evidence model](evidence-model.md) before using a metric as a scientific
claim.

[Back to the project overview](../README.md)
