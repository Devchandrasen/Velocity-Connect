# VehCom expanded validation protocol (2026-09-07)

Status: tooling, synthetic-fixture tests, and bounded simulator smokes completed.
The principal, load, channel-sensitivity, and expanded campaigns have not run.
No installed validation is established: calibrated external coupling operators are
missing. Neither UMi nor RMa LOS is railway-calibrated; **RMa alone is not railway
validation**. A successful software run or exposure gate does not change this.

## Frozen, separable designs

Baseline treatments are `direct_composite` (20 dB assumed composite VPL) and
`scalar_passive_legacy_reference` (`repeater`, `declared_scalar`, predeclared
6.5 dB). The latter is a legacy reference role, **not** the old CLI
`legacy_scalar` 5 dB mode and not device calibration. Values are inherited
engineering assumptions, not fitted here. Candidate bridge treatments are
additional, not substitutions for either baseline.

| Profile | Design | Baseline rows | Candidate-inclusive rows |
| --- | --- | ---: | ---: |
| `principal` | UMi LOS, DL and UL, 1 UE, 4 Mbps/UE, 40 replicates/cell | 160 | 240* |
| `load` | UMi LOS, DL, 1/4/16 UEs x 4/20/50 Mbps/UE, 20 replicates/cell | 360 | 540* |
| `channel-sensitivity` | UMi vs RMa LOS, DL and UL, 1 UE, 4 Mbps/UE, 20 replicates/cell | 160 | 240* |
| `expanded` | Union of the preceding three independently defined families | 680 | 1,020* |
| `smoke` | UMi/RMa x DL/UL x 2 replicates; 0.4 s, one gNB, no handover | 16 | 24* |
| `bridge-smoke` | Static UMi-labelled DL, one gNB/UE, 0.4 s, 2 replicates | requires candidate | 6 |

*These are arithmetic counts for a future admitted moving/multi-link bridge.
The current `em_complex` interface is restricted to `bridge-smoke`; it rejects
motion/multiple links. Do not treat its fixed single-stream Jones projection as
full MIMO. Its external operators replace stock channel/pathloss: a UMi label
on that static row is context, not proof that the EM path is UMi-calibrated.
Candidate planning requires advertised options, an explicit passive model, a
reviewed binary/source pin, and input artifact hashes. Synthetic operator inputs
remain fixtures. The builder invents no operators or calibration.

Focused plans equal the corresponding expanded-plan subset, including RNG IDs.
Execute **either** focused plans **or** expanded, never both. Every focused plan
has its own complete row ledger and analysis gate. Completion of principal must
not be described as completion of load or channel sensitivity. These are fixed
profiles, not result-selected subsets of an unfinished expanded campaign.

Principal uses six sites, 500 m spacing, gNB height 10 m, lateral offset 10 m,
UE height 1.5 m, 500 km/h, shadowing enabled, 5 ms channel updates, numerology 1,
SRS off, non-ideal RRC, A3 hysteresis 1.5 dB and TTT 128 ms. RMa sensitivity
keeps the same geometry to isolate the generic model choice; this is neither
a calibrated railway geometry nor a model-domain validity claim.

The source's guarded window is x=875..1875 m, time [6.3,13.5) s, with stop at
14.4 s / x=2000 m. Thus each completed valid run supplies **1 km active route
exposure**, and 40 completed valid runs supply **40 km per treatment per traffic
direction**. Warm-up/cool-down distance is excluded. Traffic direction means
DL/UL, **not** reverse train travel: all moving runs travel positive x. The
analysis records temporal/spatial endpoints and direction explicitly. The
channel sensitivity has only 20 km/cell/treatment and is labelled separately.
Static bridge smoke has zero route exposure and undefined per-km rates.

## Random identities, pairing, and fixed outcomes

Default expanded/focused seed base is 760001, run base 76000001; independent
family offsets are principal=0, load=1000, channel-sensitivity=2000. Smoke bases
are 780001/78000001; static bridge smoke 790001/79000001. Within a family, the
fixed cell order and replicate index advance both seed and run once per pair.
All treatments of that cell/replicate share those identifiers. They are fresh
relative to the inspected legacy v3 seed ranges. Global historical uniqueness
is not asserted: supply every relevant `--prior-plan` to collision-check prior
VehCom plans, and choose new explicit bases before any independent rerun.

Do **not** call this proven common-random-number matched channel simulation.
Equal seed/run IDs, even explicit `nrRngStream`/`channelRngStream`, do not show
equal stream allocation, consumption, fading state, or channel realizations.
That stronger assertion requires separately reviewed state evidence. Current
analysis refuses an unreviewed `common_channel_realizations_verified=1` claim.

`plan.json` contains every row, control, treatment identity, full binary help,
binary SHA-256, source-file SHA-256 bundle and originating build provenance,
candidate artifact hashes, driver hash, and analysis constants. Its digest
guards accidental modification. `ledger.jsonl` contains all planned identities
before execution and append-only transitions:

`planned -> running -> succeeded | failed | timeout | interrupted`

Each event repeats plan/source/binary hashes and seed/run/cell/treatment IDs.
The runner is serial and directly invokes the binary with argv, never `ns3 run`,
`shell=True`, a rebuild, or an automatic retry. The running event records exact
arguments and operational timeout. Outputs are isolated under `raw/<row_id>`;
pre-existing directories are refused, not cleared. Process logs are isolated
under `logs/<row_id>` so the simulator receives an empty result directory.
Success binds all output files (including bridge audits/snapshots) and process
logs by hash. Failed-run logs are also retained; the analyzer checks their
recorded hashes when present.

Resume skips every terminal row, including failures. A crash-left `running`
row requires explicit `--recover-interrupted`, after the operator confirms no
orphan simulator remains; this appends `interrupted`, **never** retries it. OS
locks prevent concurrent cooperating runners. Truncated/malformed ledgers fail
closed and are not silently repaired. Ctrl+C kills only the launched process
group, records interruption, and leaves pending rows for later continuation.
Source/binary/driver/input drift blocks additional execution. Keep original
source tree, binary dependencies and driver immutable through a campaign.

No statistical result drives stopping, extra replication, tuning, or dropping
rows. An operational timeout (default 1800 s/run) is not a statistical stopping
rule. Fix the resource-appropriate timeout before starting; high-load cells may
need much more than 1800 s. A terminal failed campaign is retained. New work
requires a new directory and fresh IDs, not deletion of failure history.

`status` reports only operational counts, never partial performance summaries.
Analysis requires every planned row to have succeeded and all raw hashes,
controls, packet counts, durations and handover counters to reconcile. Otherwise
it writes only an audit (`statistics: null`), including all outcomes. It cannot
pass the 40 km gate using planned, failed, incomplete, static or invalid exposure.
Outputs are new files only; previous analyses are never overwritten.

## Real metric contract and estimands

Source inspected: `hsr_velocity_connect.cc`, `hsr_types.h`, `hsr_runner.h`,
`hsr_apps.h`, `hsr_io.h`; live legacy pin help was inspected on 2026-09-07.
The inspected executable SHA-256 was
`1141752880eabb979bbcbb73eb33835a1160700b1cf146d611d55a4b0f1d30be`.
This legacy binary is not the new bridge binary. Use a matching versioned pin
and immutable source tree. The provenance check intentionally refuses mismatch.

Final bridge-capable pin inspected and smoke-tested:
`/home/codex/buildprovenance/velocity-em-bridge-r05-portable-20260907/em_bridge_build_pin_v1.json`,
binary beside it named `hsr_velocity_connect`, SHA-256
`a57f40ab95bf1a3b4edb69dc564e7b39f4a821710b751898529adb8885755d8d`.
All nine source hashes match the immutable `source/` beside the pin; 62 CLI
options were advertised. This stable pin supports the legacy baseline profiles
as well as static bridge integration. A diagnostic additionally checked 144
existing accepted v3 principal/load `single_run.csv` files against this Python
parser's control, header, packet/PDR and payload-throughput consistency rules.
No new campaign statistics or simulator runs were produced by that diagnostic.

- `single_run.csv`: controls plus `tx_pkts`, `rx_pkts`, `throughput_mbps`, `pdr`,
  `mean_lat_ms`, `p50_lat_ms`, `p95_lat_ms`, UE throughput quantiles, Jain fairness,
  handover counts/durations/application gaps and robustness counters.
- `ue_metrics.csv`: `ue_index,traffic_direction,tx_pkts,rx_pkts,throughput_mbps,pdr,mean_lat_ms,p95_lat_ms`.
- `packet_receptions.csv`: `ue_index,traffic_direction,receive_time_s,latency_ms`.
- `handover_events.csv`: `imsi,source_cell_id,target_cell_id,final_cell_id,start_time_s,end_time_s,protocol_duration_ms,application_gap_ms,success,completed`.
- Serving-cell and RSRP CSVs must exist and are hashed. No invented offered-rate,
  outage/RLF, channel-calibration, or per-run wall-time CSV columns are assumed.
- Optional new bridge/RNG echo fields are checked if supplied in CLI controls;
  additional bridge outputs are retained and hashed, not promoted to physical
  validation evidence.

Offered rate is a planned CLI control (`perUeOfferedMbps`), not an aggregate CSV
column. The 1024-byte packet includes a 12-byte measurement header; payload-only
goodput uses 1012 bytes. Analysis checks observed transmitted packet rate against
the offered rate with one-packet-per-UE and nanosecond scheduling tolerance.
Aggregate offered traffic spans 4..800 Mbps for the load matrix. Near 95% of
the **payload** offered ceiling is flagged offered-load-limited, not capacity
evidence. Below 95% is flagged unmet offered load / possible saturation, which
cannot distinguish congestion, losses, handover gaps or other bottlenecks.

Conditional latency is JSON `null` for zero reception, never zero. A partially
undefined metric has its valid/undefined run-pair counts reported but **no
available-case paired mean or interval**. This avoids survivor-only latency
comparisons; reception probability and unserved time remain separate outcomes.
Run means/medians describe the equal-weight run distribution, not a pooled
packet distribution or pooled packet p95.

Paired differences are comparison minus direct-composite and require exact
cell, pair, seed, run, source and binary identities and matched non-treatment
controls. They are not formed by list position, or across different channel
cells. Every metric has `n_pairs`, `valid_pairs`, `undefined_pairs`. Fixed
20,000-resample percentile-bootstrap 95% intervals resample whole seed/run
blocks (paired differences), not packets, UEs, or individual treatment arms.
The bootstrap seed is deterministic per cell/contrast/metric. Intervals are
**pointwise exploratory**, not simultaneous superiority claims. No
multiplicity-controlled familywise conclusion is implemented.

Garwood Poisson rate bounds use event counts divided by completed UE-km (route
km multiplied by UEs). For count k and exposure E, the equal-tailed 95% interval
is `[chi2(.025,2k)/(2E), chi2(.975,2(k+1))/(2E)]` (lower bound zero at k=0).
The separate one-sided 95% upper bound uses `chi2(.95,2(k+1))/(2E)`.
Zero events over 40 UE-km therefore give one-sided upper 0.0748933 events/UE-km,
**not zero risk**; the two-sided upper is 0.0922220. These are exact only under
the homogeneous Poisson assumption, not proof of event independence. Repeated
handover clusters may violate it. See the
[NIST constant-rate inference reference](https://www.itl.nist.gov/div898/handbook/apr/section4/apr451.htm)
and [SciPy's paired resampling definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html).

Receive gaps use strictly greater than 20 ms, repeated at fixed multipliers
0.5/1/2 (10/20/40 ms). First/last unserved edges and complete no-reception windows
contribute to max gap and unserved-edge time, **not** internal gap event counts.
Ping-pong is a completed successful reversed cell transition within 1 s of the
previous successful completion on the same IMSI, excluding overlaps and failed
transitions. Packet gaps are not radio-link-failure labels.

Threshold sensitivity separately scales all declared engineering reference
levels by 0.5/1/2: loss .05, p95 latency 20 ms, max receive gap 200 ms,
ping-pongs .5/UE-km and handover failures .1/UE-km. Report every component and
their maximum; do not choose the most favorable threshold or use it to tune,
stop, or declare standards compliance. Missing latency or zero exposure leaves
the corresponding score undefined.

## Resource estimate from existing evidence (not a new timing run)

The old logs do not contain elapsed-per-run columns. Read-only inspection used
consecutive `single_run.csv` completion mtimes within the four accepted v3
principal/load directories under `/home/codex/velocity-connect-ns3-v5/out`.
Campaign order and logs were cross-checked against
`output/logs/transaction_v3_repaired_campaign_20260731T132941.log` and
`output/logs/transaction_v3_resume_20260801T101543.log`. Mtime spacings include
wrapper/I/O/scheduling time, not isolated CPU timings; concurrency differed
(old launcher default six, resumed campaign documented serial). Do not treat
these as matched contemporary benchmarks.

- Principal: 59 completion spacings each, mean DL 39.66 s and UL 31.32 s
  (observed ranges DL 26.55..59.65 s, UL 25.27..43.99 s).
- Old **1 Mbps/UE** downlink load, composite + repeater: 1 UE mean 40.32 s
  (4 spacings), 4 UEs mean 139.98 s (6), 16 UEs mean 736.76 s (6;
  684.97..803.23 s). Three seeds per UE/treatment are not 20-replicate evidence.
- Holding those spacings constant gives principal ~1.58 h, generic sensitivity
  ~1.58 h (RMa cost unmeasured), load ~30.57 h, total **~33.7 h serial**.
  This is an optimistic planning scenario, not an ETA or a lower confidence bound.
- A deliberately crude packet-proportional sensitivity scales load cost by
  `(4+20+50)/3 = 24.67` relative to old 1 Mbps/UE: load ~754 h, total ~31.6 days.
  This is an alternate cost scenario, not an empirically established upper bound;
  channel scheduling and packet/trace costs need not scale linearly.

Consequently there is no defensible narrow full-campaign ETA for the inspected
16 GB host. The estimate was made under concurrent workloads and is not a
current resource snapshot. Schedule one simulator process at a time,
check memory/trace storage and choose timeout before admission. The short smoke
checks IO and execution, **not** the expensive high-load throughput/time model.
No candidate runtime estimate is established and the current bridge cannot run
the moving profiles at all. Faster completion, even if observed, is not a
scientific result or an installed-coupling validation.

## Reproduction commands

Use the runner in WSL. It uses only the Python standard library; analysis needs
NumPy/SciPy already available in the inspected Windows Python (2.3.5/1.18.0).
The inspected WSL ns3-v5 venv lacks SciPy. Either use Windows analysis via the
WSL UNC path below, or supply a suitable WSL analysis environment.
No dependency installation is needed for planning/running. Do not silently
change a shared venv during the other jobs.

```bash
# In WSL. Final versioned pin inspected successfully; keep its sources immutable.
P=/mnt/c/Users/devel/OneDrive/Documents/Velocity-Connect
S=/home/codex/velocity-connect-ns3-v5
V=/home/codex/buildprovenance/velocity-em-bridge-r05-portable-20260907
B="$V/hsr_velocity_connect"
PIN="$V/em_bridge_build_pin_v1.json"
python3 "$P/scripts/run_vehcom_validation.py" inspect --binary "$B" --source-root "$V/source" --pin-file "$PIN"
python3 "$P/scripts/run_vehcom_validation.py" plan --profile smoke --binary "$B" --source-root "$V/source" --pin-file "$PIN" --out "$S/out/vehcom-smoke-v1"
# Execute only after reviewing the immutable plan:
python3 "$P/scripts/run_vehcom_validation.py" run --out "$S/out/vehcom-smoke-v1" --timeout 120
python3 "$P/scripts/run_vehcom_validation.py" status --out "$S/out/vehcom-smoke-v1"

# Focused plans; these commands do NOT execute simulations.
python3 "$P/scripts/run_vehcom_validation.py" plan --profile principal --binary "$B" --source-root "$V/source" --pin-file "$PIN" --out "$S/out/vehcom-principal-v1" --prior-plan "$S/out/vehcom-smoke-v1"
python3 "$P/scripts/run_vehcom_validation.py" plan --profile load --binary "$B" --source-root "$V/source" --pin-file "$PIN" --out "$S/out/vehcom-load-v1" --prior-plan "$S/out/vehcom-principal-v1"
python3 "$P/scripts/run_vehcom_validation.py" plan --profile channel-sensitivity --binary "$B" --source-root "$V/source" --pin-file "$PIN" --out "$S/out/vehcom-channel-v1" --prior-plan "$S/out/vehcom-principal-v1" --prior-plan "$S/out/vehcom-load-v1"
# After smoke and resource admission, execute a chosen complete focused plan.
# run --out <focused-directory> --timeout <predeclared-operational-timeout-seconds>
# Reusing run resumes only pending rows; --recover-interrupted never retries a started row.
```

```powershell
# Windows: fixture tests, then analysis of completed WSL smoke evidence.
python -m pytest tests/test_vehcom_validation.py -q
python scripts/analyze_vehcom_validation.py --campaign '\\wsl.localhost\Ubuntu-22.04\home\codex\velocity-connect-ns3-v5\out\vehcom-smoke-v1' --output '\\wsl.localhost\Ubuntu-22.04\home\codex\velocity-connect-ns3-v5\out\vehcom-smoke-v1\analysis-v1.json'
```

Candidate example (new final pin only, no supplied calibration):

```bash
python3 "$P/scripts/run_vehcom_validation.py" plan --profile bridge-smoke \
  --binary "$B" --source-root "$V/source" --pin-file "$PIN" --out "$S/out/vehcom-bridge-smoke-v1" \
  --candidate-arg=--passiveModel=em_complex \
  --candidate-arg=--emTouchstone=/absolute/reviewed/cross.s4p \
  --candidate-arg=--emOperators=/absolute/reviewed/external-operators.csv \
  --candidate-arg=--emMapping=cross \
  --candidate-artifact /absolute/reviewed/cross.s4p \
  --candidate-artifact /absolute/reviewed/external-operators.csv
```

An optional `--extra-arg=--nrRngStream=1000` is accepted only when advertised by
that pin; extras cannot override seed/run, timing, load, output directory, or
other frozen experimental controls. Input arguments remain literal argv tokens,
including paths with spaces. Artifacts must be immutable and explicitly hashed.
Current bridge-smoke geometry is gNB (0,0,10), UE (500,0,1.5), static; external
operators must describe that exact geometry or the binary must refuse them.
The argument schema hook is not admission for a moving R05 candidate campaign.

## Verification

The tests in `tests/test_vehcom_validation.py` are explicitly **synthetic
fixtures only**. They test counts, fresh identities, focused/expanded consistency,
whole-block bootstrap against an independent NumPy calculation, Poisson tail
inversion, threshold/boundary accounting, failure/timeout/crash retention,
raw/source/binary integrity, candidate admission, and null handling. Passing
tests are not radio simulations, HFSS evidence, or railway validation. Checks
specifically prevent survivor-only summaries, wrong exposure denominators,
packets-as-replicates, process-log tampering and nonempty result directories.

On 2026-09-07 the full local workspace suite passed 147 tests, including 43
manuscript checks that are not part of the implementation-only repository.
A fresh implementation extraction passed 104 tests and its source manifest
on the same host; no new-machine full-science reproduction is implied. The final
portable binary also completed the 16-row UMi/RMa, DL/UL smoke profile and the
6-row static bridge-smoke profile. The bridge used synthetic external operators.
The successful bridge campaign directory is
`vehcom-bridge-smoke-r05-logging-20260907` under the simulator's `out/` directory,
plan SHA-256 `03076d3f333d257a8eb22ceebbb0d8bbb37892a09f080d904b69200a47fc2a15`.

Two earlier bridge-smoke attempts are retained as failed, not pooled with the
success: `vehcom-bridge-smoke-r05-portable-20260907` rejected dynamic channel
updates, and `vehcom-bridge-smoke-r05-static-20260907` rejected output directories
containing runner logs. Both ended with four scalar successes and two EM
failures. The fixed profile disables channel updates for the static bridge and
writes logs outside result directories. Each new attempt used a new directory
and seed/run bases. These are integration corrections, not candidate retuning.
