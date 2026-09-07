# Evidence ledger

This ledger records completed terminal checks. A stability checkpoint is not a
multi-seed system result and must not be presented as one.

## 2026-09-07: Revision 05 implementation checks

The local workspace suite passed **147 tests**, including 43 manuscript-analysis
and packaging checks intentionally excluded from the implementation repository.
A fresh extracted implementation archive passed its **104 source-only tests**
and the 112-file manifest check on the same host. This is not a new-machine
HFSS or full network-campaign reproduction. A serial isolated build
against pinned ns-3.48 and 5G-LENA v5.0 passed 42 standalone complex-transfer
checks, per-resource-block PSD integration tests, four 0.4 s EM CLI smokes and
a scalar control. The three EM downlink cases each received 36/36 packets;
the V5 uplink smoke received 34/36. Different synthetic received spectra did
not imply a statistically established packet advantage.

The final binary SHA-256 is
`a57f40ab95bf1a3b4edb69dc564e7b39f4a821710b751898529adb8885755d8d`.
The validation driver completed a 16-row scalar smoke and a six-row static
bridge smoke. Two failed earlier bridge profiles remain excluded and are
documented in `reproducibility/vehcom_campaign_protocol.md`.
No expanded principal, load or channel-sensitivity campaign is complete.

The new channel supports one static SISO link with explicit external complex
operators and the solved four-port data. It rejects motion, missing operators,
multiple links and duplicate scalar channel attenuation. It is **not** a
calibrated moving-train co-design, full MIMO or an installed-device result.
The legacy 816-run study and separate 60-run loss sweep are not recomputed or
relabelled as matrix-coupled evidence.

A stricter first-order radiation-boundary HFSS solve converged in 11 passes,
with 34,585 tetrahedra and final maximum delta-S 0.0014877. Native radiation
efficiency remained 1.015502 and 1.015454, so power closure **fails**. Source
normalization diagnostics did not close the gap. A higher-order PML attempt
was stopped after memory exhaustion and is not a completed solve. Exact
commands and scope are in `reproducibility/radiator_power_revision05.md`.

These changes strengthen executable checks and provenance, not antenna
efficiency, A3 superiority, railway calibration or product readiness.

## Current guarded network campaign status

The boundary-controlled `transaction-v3` campaign uses six gNBs, an interior
1.75--3.75 ISD application window, simulation stop at 4 ISD, 5 ms channel
updates, non-ideal RRC, SRS disabled, and a predeclared scalar passive-loss
model. The repaired campaign completed 30 terminal ledgers containing 816
successful runs: 120 principal, 288 parametric, 360 tuning, and 48 load runs.
Exact factor multisets and unique seed/run pairs were checked. The accepted
campaign counts and provenance hashes are retained in
`provenance/accepted_campaigns.json`.

The first interrupted controller and the failed FqCoDel protocol attempt remain
explicitly excluded in the provenance records. They were not resumed, merged,
or relabelled as accepted runs. Bulk raw outputs are not stored in this source
repository; the scripts regenerate them under `out/`.

## 2026-07-28 — HFSS V3 installed-radome screening and AEDT 2024 gate

The selected V2 generator was extended with version/edition selection,
cylindrical roof-crown geometry, and common/split dielectric radomes. Eleven
V3 manifests were consolidated into
`hfss/results/n78_v3_installed/installed_candidate_summary.{csv,json}`.

The provisional installed screening candidate is
`Velocity_Connect_n78_V3_SplitRadomeFlat_E18_T1_G15_S160_PML_B30_B1`.
Its PML solve passes only the retained full-band S-parameter screening gates:
S11/S22 = -14.83/-14.91 dB, isolation = -21.53 dB, and worst-phase
TARC = -11.68 dB. S-parameter-derived ECC and CCL are retained as screening
diagnostics.

This is not a publication-ready or deployment-ready result. Its
field-integrated radiation efficiency is 101.997%/101.863%, which violates
the strict physical upper bound of 100%. Therefore absolute gain, radiation
efficiency, and the unweighted ideal-selection angular-grid diagnostic are
excluded from acceptance and publication claims; a one-percent proximity
diagnostic cannot override this failure. The B30 mesh has 45,313 elements and final
`Max Mag. Delta S = 0.0068579`. A tighter B25/0.005 attempt reached 64,890
volume elements and was rejected by AEDT Student's mesh limit.

An AEDT 2024 R1 commercial process was detected locally, but the configured
licence service did not provide the required HFSS features. No 2024 HFSS solve
is claimed. The exact licensed-2024 regeneration command and remaining mesh,
curved-roof, band-edge-field, and measurement gates are in `hfss/README.md`.

## Historical/superseded checkpoints

The records below preserve earlier ns-3.46/5G-LENA v4.1.1 capability and
single-seed checkpoints. They are not transaction-v3 submission evidence and
must not be combined with the guarded ns-3.48/5G-LENA v5.0 campaign.

## 2026-07-24 — local implementation verification

- 36 Python unit/integration tests passed.
- The pinned ns-3/5G-LENA target compiled after the final validation changes.
- All four revision-guarded dependency patches passed source-hash checks.
- Python campaign modules passed byte-code compilation and `git diff --check`.
- The campaign summary separates component configurations and uses a two-sided
  95% Student-t interval with sample standard deviation.

## 2026-07-24 — component-budget multi-cell handover checkpoint

Environment:

- ns-3 `3.46`
- CTTC 5G-LENA `v4.1.1` at
  `f29ebd33450c49af934ea5dde8606f855c22c2a6`
- Existing scheduler fixes plus revision-guarded handover wiring/lifetime
  patches derived from official CTTC revision
  `7706af4421e0405a11320aaa70b783547542cef4`
- Ideal RRC, A3-RSRP hysteresis 1.5 dB, time-to-trigger 128 ms

The v4.1.1 helper accepted a handover algorithm type but did not instantiate,
retain, and initialize the algorithm. The project patches only this missing
wiring/lifetime path. Patch SHA-256:

- wiring: `6692609CB0DC85838F529FA999433250F31417CB0B88ECE799115C3D5A49E354`
- lifetime: `28631B7E53136E7E4FC60D60A52163070C844C518E85DDCD6087A84AD42EF419`

Acceptance command:

```bash
python3 verify_corridor_checkpoint.py \
  --ns3 /home/codex/velocity-connect-ns3/ns3 \
  --workdir /home/codex/velocity-connect-ns3 \
  --out out/corridor-checkpoint-3seed
```

Configuration: component-budget passive path, 3 gNBs at 1000 m spacing,
500 km/h, initial along-track position 100 m, 30 kHz SCS. The persisted budget
is 11 dB network loss + 4 dB indoor loss - 10 dB aperture gain = 5 dB
equivalent loss.

| Seed | Throughput (Mbps) | PDR | Attempts / successes / failures | Mean protocol duration (ms) | Mean application gap (ms) |
|---:|---:|---:|---:|---:|---:|
| 21 | 3.950173 | 0.999317 | 2 / 2 / 0 | 2.034552 | 5.25 |
| 22 | 3.950173 | 0.999317 | 2 / 2 / 0 | 2.034552 | 5.25 |
| 23 | 3.910368 | 0.989247 | 2 / 2 / 0 | 2.034552 | 6.00 |

The strict validator confirmed, in every seed, completed event rows, a
serving-cell change, and neighbour-RSRP trigger evidence. The machine-readable
report is `out/corridor-checkpoint-3seed/corridor_checkpoint_report.json`.

Claim limit: this is a bounded three-seed software capability checkpoint under
ideal RRC. It proves that the advanced path executes simulator A3/X2 state
transitions and records application gaps. It is not the publication matrix,
non-ideal-RRC evidence, a hardware result, or a field handover-delay
measurement.

Diagnostic retained separately: non-ideal RRC on this dependency fails during
connection setup at `nr-ue-mac.cc:379` with an uplink HARQ-process assertion.
Those failed runs are not used as results.

## 2026-07-24 — post-rebuild paper-profile parity gate

The paper profile now sets 5G-LENA numerology 1 explicitly and records both the
numerology and derived 30 kHz subcarrier spacing in every simulator result.

```bash
python3 verify_paper_checkpoint.py \
  --ns3 /home/codex/velocity-connect-ns3/ns3 \
  --workdir /home/codex/velocity-connect-ns3 \
  --out out/paper-checkpoint-post-rebuild
```

Configuration shared by all three runs: 500 km/h, 500 m, 10 UEs, seed 7,
2 s simulation, 1024-byte UDP packets, 8.19 Mbps offered load per UE,
numerology 1, and 30 kHz SCS.

| Scenario | Status | Throughput (Mbps) | PDR | Mean latency (ms) | P95 latency (ms) |
|---|---:|---:|---:|---:|---:|
| metal | completed | 0.000000 | 0.000000 | unavailable | unavailable |
| composite | completed | 80.699129 | 0.997332 | 3.429259 | 5.484005 |
| repeater | completed | 80.784587 | 0.998388 | 2.817360 | 3.045493 |

The checkpoint validator passed only after reading numerology 1 and 30 kHz SCS
from all three raw result rows. The metal run again received no packets, so its
latency is undefined rather than zero. This closes the configuration-parity
item, but it remains a single-seed execution gate rather than publication-level
evidence. The full multi-seed campaign has not yet been run.

Dependency regression:

```text
PASS: TestSuite nr-test-numerology-delay
1 of 1 tests passed (1 passed, 0 skipped, 0 failed, 0 crashed)
```

## 2026-07-20 — scheduler stability gate (diagnostic numerology 0)

Environment:

- ns-3 `3.46`
- CTTC 5G-LENA `v4.1.1` at `f29ebd33450c49af934ea5dde8606f855c22c2a6`
- Backported upstream production fixes:
  - beam-order heap overflow: `81892efac84f2aef0a962b9da176ea7d7b6912b0`
  - DL HARQ symbol-budget underflow: `a1aa32c757e0f834a4e40654853ce56dee13eca3`
- GCC `11.4`

Dependency regression:

```text
PASS: TestSuite nr-test-sched-harq
1 of 1 tests passed (1 passed, 0 skipped, 0 failed, 0 crashed)
```

Project checkpoint:

```bash
python3 verify_paper_checkpoint.py \
  --ns3 /home/codex/velocity-connect-ns3/ns3 \
  --workdir /home/codex/velocity-connect-ns3 \
  --out out/paper-checkpoint-fixed2
```

All three runs use 500 km/h, 500 m, 10 UEs, seed 7, 2 s simulation, 1024-byte
UDP packets, and 8.19 Mbps offered load per UE.

| Scenario | Status | Throughput (Mbps) | PDR | Mean latency (ms) | P95 latency (ms) |
|---|---:|---:|---:|---:|---:|
| metal | completed | 0.000000 | 0.000000 | unavailable | unavailable |
| composite | completed | 80.478738 | 0.994608 | 8.787140 | 12.688281 |
| repeater | completed | 80.694631 | 0.997276 | 4.756367 | 5.011483 |

The metal run received no packets, so latency is undefined rather than zero.
The result is evidence that the scheduler path is stable, not evidence that the
metal link provides service. This older run used 5G-LENA's default numerology 0
and is retained as diagnostic history; it is superseded by the numerology-1
parity gate above for paper-profile execution evidence.
