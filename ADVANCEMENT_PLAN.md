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

Implemented on 2026-07-24 as an advanced corridor path while retaining the
single-cell paper baseline:

1. Adjacent cells are placed along the railway corridor.
2. UEs begin on cell 0 and use A3-RSRP X2 handover.
3. The simulator logs start/end/error, protocol duration, application packet
   gap, serving-cell changes, and RSRP measurement reports.
4. `run_corridor_campaign.py` compares coach scenarios on identical traces.

The strict 500 km/h, three-gNB, one-UE checkpoint completed seeds 21, 22, and
23 with two successful handovers per seed and no failures. This is a bounded
protocol-event gate under ideal RRC, not publication-level or field evidence.

Protocol-event acceptance is met: every handover is attributable to a UE,
source cell, target cell, timestamp, and seed, and every run has serving-cell
and neighbour-RSRP evidence. Per-window throughput/PDR/latency remain a
publication-matrix item; the current event metric is application packet gap.

## Phase 3 — stronger Velocity Connect physical model

The first component-budget gate is implemented:

1. Donor gain, feeder loss, feedthrough/coupling loss, indoor loss, and service
   gain are named and persisted.
2. `legacy_scalar` is preserved only as the rejected-paper baseline.
3. Invalid component budgets fail instead of being silently clamped.
4. `calibrate_passive_model.py` converts measured VNA/OTA rows to simulator
   parameters without synthetic fallback.

Remaining: calibrated measurements, uncertainty sweeps, and a higher-fidelity
two-segment propagation implementation beyond the current equivalent
system-level application.

Acceptance gate: the model passes component-level conservation checks, never produces negative loss or impossible gain, and conclusions remain stable across repeated seeds and the declared uncertainty range.

## Phase 4 — research-grade evidence package

1. The three-seed protocol gate is complete; run the declared 20-seed
   principal matrix only after hardware calibration.
2. Summary tables now report mean, sample standard deviation, two-sided 95%
   Student-t interval, and number of valid observations.
3. Add a machine-readable manifest containing source revisions, NS-3/NR revisions, compiler, configuration, and command line.
4. Remove or label all synthetic/hand-entered plotting fallbacks.
5. Publish only claims supported by completed terminal runs and retained raw CSVs.

## Recommended next implementation

Run the VNA/OTA calibration gate with the hardware expert, then replace the
equivalent Tx-power abstraction with explicit outdoor-donor and
service-antenna-to-seat propagation segments. After that, execute the declared
mixed-load, uplink/downlink, multi-seed matrix and only then begin a parked-coach
pilot. The impact path is: reproducible parity -> measured component budget ->
two-segment propagation -> multi-cell robustness -> coach-level pilot.
