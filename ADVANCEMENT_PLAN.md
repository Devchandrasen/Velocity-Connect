# Velocity Connect advancement plan

## Current baseline

Completed and verified locally on 2026-07-20:

- Ubuntu 22.04 WSL build environment installed.
- ns-3.46 and 5G-LENA NR v4.1.1 checked out together.
- NS-3 configured with NR, Eigen3, SQLite, GSL, XML, GTK, examples, and tests.
- `hsr_velocity_connect` builds successfully with GCC 11.4.
- A short single-run smoke simulation produces a valid `single_run.csv`.
- The Python campaign runner has multi-seed execution, failure accounting, and confidence intervals.

The first shell smoke attempt exceeded five minutes because its quoting dropped the single-run arguments and launched the original all-sweeps path. The corrected direct NS-3 invocation and two-run campaign completed successfully. Development and paper profiles are now separate so fast CI checks do not spend time on a full research matrix.

Paper audit completed on 2026-07-20:

- The submitted study uses a single serving cell, UMi LOS, shadowing disabled, 3.5 GHz, 100 MHz, 40 dBm, 2 s, 1024-byte UDP packets every 1 ms, and 10 UEs for the speed and distance studies.
- Its scenarios are 60 dB metal, 20 dB composite, and a component-derived 5 dB passive path: 8 dBi donor + 2 dBi service gain, 3 dB feeder, 8 dB coupling/connector, and 4 dB indoor distribution loss.
- The repository now exposes this contract through `--profile paper` and `run_paper_campaign.py`, with separate speed, distance, and scalability ledgers.
- A first live 10-UE check completed for the repeater case but triggered NS-3 scheduler assertions for the low-SINR metal/composite cases. Those failures are retained as a reproducibility defect until isolated; they are not paper-result evidence.

## Phase 1 — build and experiment hygiene

1. Add a checked-in WSL setup/sync script so the Windows checkout can be copied into the NS-3 scratch tree without manual commands.
2. Keep the explicit `dev` profile separate from the submitted-paper profile.
3. Generate paper-family plots directly from campaign summaries with confidence bands and no synthetic fallback.
4. Add a CI smoke gate: compile the target, run one repeater and one metal case, validate the CSV schema, and fail on missing/non-finite required fields.
5. Isolate and fix the 10-UE low-SINR scheduler assertion, or document a version/configuration boundary that makes the paper workload unsupported.

Acceptance gate: a clean machine can configure/build and complete the smoke matrix in under 60 seconds; all raw rows retain seed, run, scenario, and configuration provenance.

## Phase 2 — real mobility and handover model

The current model has one gNB and `AttachToClosestGnb`; it does not yet measure a real handover. Upgrade it to two or more gNBs along the track:

1. Place adjacent cells along the railway corridor.
2. Attach UEs and enable an NR handover algorithm.
3. Log handover request, execution, interruption duration, serving-cell changes, and failed handovers.
4. Compare metal, composite, and repeater cases at the same mobility traces.

Acceptance gate: every handover event is attributable to a UE, source cell, target cell, timestamp, and seed; throughput/PDR/latency are reported both overall and during handover windows.

## Phase 3 — stronger Velocity Connect physical model

Replace the current equivalent gNB transmit-power reduction with an explicit two-segment link budget:

1. Model donor antenna, feeder/coupler, in-coach distribution, and service antenna as named components.
2. Preserve the simple effective-loss mode as a controlled baseline.
3. Add sensitivity sweeps for each component and bounded uncertainty distributions.
4. Report when the relay improves coverage versus when it only improves in-coach penetration.

Acceptance gate: the model passes component-level conservation checks, never produces negative loss or impossible gain, and conclusions remain stable across repeated seeds and the declared uncertainty range.

## Phase 4 — research-grade evidence package

1. Run at least three seeds for smoke validation and a declared larger seed set for paper results.
2. Generate summary tables with mean, sample standard deviation, 95% confidence interval, and number of valid observations.
3. Add a machine-readable manifest containing source revisions, NS-3/NR revisions, compiler, configuration, and command line.
4. Remove or label all synthetic/hand-entered plotting fallbacks.
5. Publish only claims supported by completed terminal runs and retained raw CSVs.

## Recommended next implementation

Complete the paper-profile stability gate first. Then implement Phase 2 as the first substantive research advancement: real multi-cell mobility and handover interruption metrics are the clearest gap between the current framework and an advanced HSR connectivity study. The impact path is: reproducible parity -> field-calibrated passive link budget -> multi-cell handover robustness -> mixed passenger traffic and uplink -> coach-level pilot validation.
