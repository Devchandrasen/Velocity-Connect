# Velocity Connect implementation experiment protocol

## 1. Dependency gate

The current guarded implementation is pinned to:

- ns-3.48 commit `d2add90b452d600cfb4859baed8e9ea633519447`;
- 5G-LENA v5.0 commit `47a3adc263f773556eaadac5a5341458dbc61c47`;
- the byte-checked ns-3 robustness patch recorded in
  `environment/simulator-revisions.json`; and
- Ubuntu 22.04 with CMake 3.22 or newer and g++ 11.4 or newer.

Bootstrap and verify a new checkout:

```bash
bash scripts/bootstrap_ns3_v5.sh "$HOME/ns-3.48-velocity-connect" "$PWD"
bash scripts/sync_wsl_ns3_v5.sh --check-only \
  "$HOME/ns-3.48-velocity-connect" "$PWD"
```

Any dependency revision, patch hash, or tracked-tree mismatch is a hard stop.

## 2. CPU-only source gate

Before invoking external simulators or solvers:

```powershell
python scripts\verify_source_manifest.py
python -m pytest -q
```

This validates campaign construction, passive link budgets, four-port mapping,
Touchstone fixtures, statistical helpers, evidence-store behavior, and the
corridor checkpoint parser. It is not an ns-3 or HFSS solve.

## 3. Official ns-3 and 5G-LENA gate

Build the project and execute the upstream handover and regression suites:

```bash
bash scripts/sync_wsl_ns3_v5.sh --run-tests \
  "$HOME/ns-3.48-velocity-connect" "$PWD"
```

The gate includes the local short-transport-header regression plus the pinned
X2, measurement, delay, handover-scenario, and interference suites. A failed
suite blocks campaign execution.

## 4. Guarded 816-run network contract

The current campaign contract uses:

- six gNBs with an interior 1.75 to 3.75 ISD measurement window;
- non-ideal RRC and X2 handover;
- 5 ms channel updates;
- dynamic TDD with SRS disabled as a declared limitation;
- downlink and uplink traffic;
- 300, 400, and 500 km/h train speeds;
- 300, 500, and 800 m site spacing;
- 1, 4, 8, and 16 UEs in the load screen;
- development-only A3 selection seeds and separate secondary seeds; and
- declared total passive-path loss, never donor-array isolation relabelled as
  end-to-end transmission.

Run from the pinned simulator checkout:

```bash
cd "$HOME/ns-3.48-velocity-connect"
bash velocity_connect_tools/run_transaction_campaigns_v7.sh
```

The controller refuses non-empty partial output directories. A campaign is
accepted only when every expected row exists and every run status is `ok`.
The terminal contract is 30 campaign ledgers and 816 successful rows.

## 5. Declared-loss sensitivity and official regression

Run these only after the main campaign is terminal:

```bash
bash velocity_connect_tools/run_publication_loss_sweep_v7.sh
bash velocity_connect_tools/run_official_test_gate_v5.sh
```

The loss sweep evaluates 1.5, 6.5, 12, 20, 22.5, and 26 dB in both link
directions with five seeds per point. It remains a declared scalar sensitivity
study, not an HFSS-derived installed-coach result.

## 6. HFSS four-port gate

The selected native projects are committed for inspection. Re-solving requires
a compatible Ansys Electronics Desktop licence. For each four-port export:

1. validate the design before solving;
2. solve the named n78 setup and sweep;
3. export the ordered `D1, D2, S1, S2` Touchstone matrix;
4. check reciprocity and maximum singular value at every frequency;
5. report intended `S41` and `S32` transfer, return loss, leakage, and group
   delay; and
6. keep radiated gain and efficiency outside acceptance claims when strict
   power closure fails.

The checked-in Touchstone fixtures support deterministic matrix tests without
pretending that a solver was executed in continuous integration.

## 7. Measurement calibration gate

`measurement_template.csv` contains only a header. A hardware expert must add
calibrated VNA or OTA records; no synthetic measurement row is supplied.

```bash
python calibrate_passive_model.py measured_passive_components.csv \
  --out out/passive-calibration
```

The converter rejects positive passive S21, non-finite values, missing fields,
and a net-gain scalar budget. Generated campaign arguments remain traceable to
the measurement row that produced them.

## 8. Evidence release gate

Retain the exact Git commit, dependency revisions, source manifest, campaign
configuration, attempt ledger, failed-run disposition, and output hashes.
Never merge interrupted or failed protocol rows into accepted evidence. A
passing implementation gate does not establish hardware, coach, route, or
moving-train validation.
