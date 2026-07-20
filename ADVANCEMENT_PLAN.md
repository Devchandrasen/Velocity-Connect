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
- A first live 10-UE check completed for the repeater case but triggered NS-3 scheduler assertions for the low-SINR metal/composite cases. Those failures were retained as diagnostic evidence and were not used as paper results.
- Root causes were isolated to two HARQ scheduler defects fixed upstream after v4.1.1: beam-order heap overflow (`81892efa`) and issue #278's double-debited `uint8_t` symbol budget (`a1aa32c7`). The repository carries revision-guarded production-code backports for the required v4.1.1 dependency.
- After both backports, the exact 500 km/h, 500 m, 10-UE, seed-7 checkpoint completed 3/3 scenarios and the packaged `nr-test-sched-harq` suite passed. These are stability results, not multi-seed paper evidence.
- The paper profile now explicitly configures numerology 1 (30 kHz SCS), persists it in raw CSV/config/manifest provenance, and rejects mismatched results. The parity checkpoint completed 3/3 scenarios and `nr-test-numerology-delay` passed.

## Phase 1 — build and experiment hygiene

1. Keep the checked-in WSL sync script and dependency patch aligned with the pinned NS-3/5G-LENA revisions.
2. Keep the explicit `dev` profile separate from the submitted-paper profile.
3. Generate paper-family plots directly from campaign summaries with confidence bands and no synthetic fallback.
4. Add a CI smoke gate: compile the target, run one repeater and one metal case, validate the CSV schema, and fail on missing/non-finite required fields.
5. Require `verify_paper_checkpoint.py` to pass metal, composite, and repeater before starting a full paper campaign.

Acceptance gate: a pinned environment can sync/build and complete the three-run
checkpoint in under five minutes on the validated WSL host; all raw rows retain
seed, run, scenario, numerology, SCS, and configuration provenance. This gate
is now met locally.

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

Implement Phase 2 as the next substantive research advancement: real multi-cell
mobility and handover interruption metrics are the clearest gap between the
current framework and an advanced HSR connectivity study. The impact path is:
reproducible parity -> field-calibrated passive link budget -> multi-cell
handover robustness -> mixed passenger traffic and uplink -> coach-level pilot
validation.
