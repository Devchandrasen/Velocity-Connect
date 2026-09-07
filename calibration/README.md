# Moving-link measurement admission (revision06)

This directory stages **complete records for independent review**, not calibrated
channels. `measurement_contract.py` is an offline, standard-library-only Python
3.10+ validator. It reads a JSON manifest, an exact-header CSV, raw files and
supporting evidence. It does not fit a model, calculate holdout performance,
convert RSSI into path loss, generate phase/operators, run HFSS/ns-3, or publish.

Every successful result includes:

```json
{
  "status": "admitted_for_review",
  "calibration_granted": false,
  "source_authenticity_verified": false,
  "bridge_export_authorized": false,
  "support_policy": "exact_samples_only"
}
```

`--purpose calibration` means screening a proposed calibration input. It is NOT
a calibration label. Only `source.kind=measured` can enter that screening;
synthetic data can exercise `--purpose plumbing` only. Neither route grants
calibration. Even a plausible measured label plus matching SHA-256 values is
insufficient: hashes establish byte identity, not experimental truth, licensing,
independence, or metrological validity. Supporting files are checked for existence,
nonzero length and digest, **not authenticated or semantically certified**.
All test fixtures are invented, including tests that deliberately claim measured
provenance. They demonstrate the trust boundary, never field calibration.

## Usage and precise outcome

From the repository root:

```powershell
python -B calibration/measurement_contract.py C:/measurement-bundle/manifest.json --purpose calibration
python -B -m unittest discover -s tests -p test_calibration_contract.py -v
```

The CLI prints JSON to stdout; it writes no files. Exit 0 means admission for
review only. Exit 2 means rejection, with the first failing condition. No partial
dataset is silently accepted. Correct the original package or document exclusions
in a separately prepared, newly pinned package; never fill absent measurements.
Manifest limit: 4 MiB; CSV limit: 64 MiB. Raw/evidence files are hashed in 1 MiB
chunks without loading them wholesale. The tool never fetches remote URLs.

Python API:

```python
from calibration.measurement_contract import admit, CONTEXT_COLUMNS

admission = admit("C:/measurement-bundle/manifest.json")
fitting_records = admission.partition("calibration")
# This call is deliberately separate: do not tune on held-out observations.
evaluation_records = admission.partition("holdout")
row = fitting_records[0]
context = {key: row[key] for key in CONTEXT_COLUMNS}  # power_gain profile
same_record = admission.require_support(
    row["sample_id"], partition="calibration", context=context
)
```

For `em_operators`, query context must also contain every `PROJECTION_COLUMNS`
entry. Changing route, run, time, frequency, resolution bandwidth, either antenna
position/orientation, speed or projection is rejected. A request between known
points is rejected too, even inside their bounding box. There is no interpolation,
frequency clamping, nearest-neighbour substitution or extrapolation. Bandwidth is
measurement resolution, not permission to synthesize all frequencies in a band.
`require_support` retrieves observations, not calibrated predictions.

The returned rows/splits are immutable snapshots. A modified on-disk file needs
a fresh admission; an old report must not authorize new bytes. Consumers can
ignore a Python API, so this is not a sandbox or enforcement of researcher conduct.
The validator does not verify that someone has not already trained on the holdout.

## File contract

One manifest represents one homogeneous source kind, observable, antenna/setup
reference and clock/coordinate convention. Separate incompatible setups, clock
origins, source kinds and quantities into separate packages; do not hide changes
inside free text. Preserve the unmodified source files separately from derived CSV.

All objects use exactly the documented keys; unknown/duplicate JSON keys fail.
Numbers are JSON numbers, not strings/booleans; CSV numeric cells must parse as
finite numbers. No NA, blank, NaN, infinity or omitted cell is repaired. Explicit
numeric zero is allowed where physically meaningful; negative coordinates and
negative dB gains are valid. Reference text must be nonempty, not `unknown`/`TBD`.

### Manifest keys

| Key | Required content |
| --- | --- |
| `schema` | `hsr-moving-link-admission-v1` |
| `dataset_id` | Stable source/version identifier, not a calibration assertion |
| `quantity` | `power_gain` or `em_operators` |
| `normalization` | `absolute_power_waves_50ohm`; other reference impedances/units must be independently converted and documented before admission |
| `units` | Exact object below; no automatic conversion |
| `source` | Exact object described below |
| `references` | Exact object described below |
| `uncertainty` | Strictly positive finite numbers: `power_db`, `position_m`, `time_s`, `frequency_hz`, `orientation_deg`; also `phase_deg` for complex operators only |
| `routes` | Map of every CSV `route_id` to a canonical physical railway route ID |
| `split` | Exactly `calibration` and `holdout`, each containing nonempty, duplicate-free `route_ids` and `sample_ids` lists |
| `support_policy` | `exact_samples_only` |
| `samples` | Local file reference to the derived CSV |

The exact units object is:

```json
{
  "frequency": "Hz", "bandwidth": "Hz", "time": "s", "position": "m",
  "speed": "m/s", "orientation": "deg", "power_gain": "dB", "operator": "1"
}
```

A file reference is exactly `{"path": "relative/path", "sha256": "<64 lowercase hex digits>"}`.
Supply an actual digest computed from the actual file, not that placeholder.
Paths are relative to the manifest directory, with forward slashes. Absolute,
drive-relative, parent-traversal and resolved symlink/junction escapes are rejected.
An evidence attachment is not downloaded merely because a citation is a URL.

`source` contains exactly:

- `kind`: `measured` or `synthetic`. `calibrated`, `measured_calibrated`, mixed
  source kinds and model names masquerading as source kinds are rejected.
- `citation`: source URL/DOI, version and acquisition attribution.
- `license_id`: explicit applicable data-license/permission identifier, not an
  inference from article access or a public GitHub repository.
- `raw_files`: nonempty map of `raw_file_id` to file reference. Every raw ID must
  be used in the CSV; a second raw ID cannot relabel identical file bytes.
- `evidence`: exactly eight file references, with these roles:

| Role | What an independent reviewer must establish from it |
| --- | --- |
| `license` | Rights cover the actual raw data and proposed use; record restrictions |
| `acquisition` | Physical railway, train, dates, speed, instruments/settings, frequency and time synchronization, raw record locations, and measured versus generated origin |
| `instrument_calibration` | Traceable amplitude/frequency/time calibration, before/after checks, TX power and receiver gains/noise floor, uncertainty and validity interval |
| `processing` | Exact code/version/commands, raw record-to-CSV mapping, averaging/bandwidth, units, gain/reference-plane conversion, exclusions; no imputation represented as measurement |
| `antenna_reference` | Actual installed antennas, patterns/effective lengths, efficiency, polarization/basis, orientations, cable loss/load/de-embedding, physical reference planes; complex profiles also require phase/coherence evidence |
| `route_identity` | Canonical railway geometry and provenance, including aliases, overlapping segments and repeated traversals |
| `uncertainty` | Meaning/coverage of reported positive uncertainties, systematic/correlated errors, censoring and sensitivity; numbers are not assigned here |
| `split_plan` | Dated, independently pinned pre-fit plan, holdout isolation, model/metric and acceptance criteria; file presence does not verify preregistration |

Synthetic plumbing packages still supply these attachments, explicitly describing
the synthetic construction and assumptions. They cannot enter calibration screening.

`references` contains exactly these nonempty strings:

```text
coordinate_frame, time_origin_utc, clock_reference, basis, phase_reference,
tx_antenna, rx_antenna, tx_reference_plane, rx_reference_plane, orientation_convention
```

`time_origin_utc` must be a parseable UTC date/time with `T` and trailing `Z`.
CSV `time_s` is elapsed time from it, not a timezone-free timestamp. Coordinate
origin/axes must locate all positions and antenna reference planes in metres.
Orientation convention must describe axes, rotation order, handedness and whether
angles rotate a body or its coordinate frame; yaw/roll lie in [-180,180] degrees,
pitch in [-90,90]. The validator checks numeric bounds, not convention truth.
For `power_gain`, `phase_reference` must be exactly `not_observed`; this prevents
claiming a measured phase from scalar power. Complex operators require an explicit
coherent phase convention and a positive `phase_deg` uncertainty.

### CSV header and observable profiles

Obtain the exact header without creating any data:

```powershell
python -B -c "from calibration.measurement_contract import csv_columns; print(','.join(csv_columns('power_gain')))"
python -B -c "from calibration.measurement_contract import csv_columns; print(','.join(csv_columns('em_operators')))"
```

Common columns, in order:

```text
sample_id,route_id,run_id,raw_file_id,raw_record_id,time_s,frequency_hz,bandwidth_hz,gnb_x_m,gnb_y_m,gnb_z_m,ue_x_m,ue_y_m,ue_z_m,speed_mps,tx_yaw_deg,tx_pitch_deg,tx_roll_deg,rx_yaw_deg,rx_pitch_deg,rx_roll_deg
```

`raw_record_id` identifies the exact observation in its raw file, including
snapshot/subcarrier/polarization indices as needed. The pair `(raw_file_id,
raw_record_id)` may appear only once; duplicating one observation into different
routes or partitions is forbidden. Raw formats are not parsed here: the processing
record and independent reviewer must establish that these locators are real.
At most one row per `(route_id, run_id, time_s, frequency_hz)` is accepted.
Aggregate modes externally with documented processing or separate their packages.

`frequency_hz` is the observed RF frequency; `bandwidth_hz` is its positive
effective measurement/resolution bandwidth. The whole interval
`frequency_hz +/- bandwidth_hz/2` must lie strictly inside (0, 6 GHz). Metadata
does not imply continuous frequency coverage. Time/speed must be nonnegative.
Each run must have at least two distinct times and UE positions and some positive
speed. Geometry/speed/orientation must agree across frequencies at the same time.
This is a minimal moving-record check, not proof of high-speed-rail operation or
kinematic consistency; actual motion, speeds and synchronization require review.

`power_gain` appends `power_gain_db`, the absolute received/transmitted power-wave
ratio in dB at the declared installed reference planes. It must be finite and
at most 0 dB for this passive-link profile. This is not raw RSSI, RSRP, Rxqual,
an arbitrary fitted path loss, or an antenna gain. Censored/below-noise-floor data
cannot be replaced with zero gain; retain raw censoring evidence and make explicit
exclusions in the preparation record. Scalar power cannot determine any of the
three complex operators.

`em_operators` instead appends:

```text
tx0_re,tx0_im,tx1_re,tx1_im,rx0_re,rx0_im,rx1_re,rx1_im
```

then the 24 `OPERATOR_COLUMNS`, exactly the existing C++ order: each of `d`, `in`,
`out`, then `00`, `01`, `10`, `11`, then `_re`, `_im`. They represent direct D,
donor coupling C_donor and service coupling C_service, respectively; output row,
input column. Jones projections must already have unit power norm. Each 2x2
operator is checked by its maximum squared singular value against the existing
1 + 1e-8 passive-power tolerance, not by individual entries alone. Explicit zero
coefficients are required; no zero/direct-path phase is synthesized. This check
does not establish passivity of the composed D + C_service T C_donor channel,
loaded-network physics, causality, reciprocity or installed calibration.

### Exact route holdout

Both partitions must consist of complete routes, with the exact sample lists for
those routes. All rows/routes are assigned once. A physical route ID, a route ID,
a sample ID or a run reused across partitions is rejected. Repeated passes of one
railway route stay together; different train IDs are not independent routes.
Distinct aliases mapping to one canonical physical route cannot evade the check.
Invented canonical IDs or overlapping geometries with different IDs cannot be
detected from labels alone: independently check `route_identity` before fitting.

Conceptual split, using identifiers only (not a measurement fixture):

```json
{
  "routes": {"route-A": "canonical-railway-A", "route-B": "canonical-railway-B"},
  "split": {
    "calibration": {"route_ids": ["route-A"], "sample_ids": ["A-0", "A-1"]},
    "holdout": {"route_ids": ["route-B"], "sample_ids": ["B-0", "B-1"]}
  }
}
```

Two distinct routes are a minimum mechanical check, not adequate statistical
power. The split is deterministic and its exact membership plus all input hashes
are reported. This module never selects a random split, retunes using holdout,
or claims that holdout routes are calibrated. Later model validation needs a
pre-specified applicability domain and must reject unsupported frequency/speed/
geometry/antenna configurations; admission alone authorizes no prediction.

## Existing workspace evidence and bridge boundary

Read-only inspection, 2026-09-07, excluded unrelated `research/`:

- `measurement_template.csv`: header only, containing scalar component-budget
  terms (`feeder_s21_db`, `feedthrough_s21_db`, `coupling_loss_db`,
  `indoor_path_loss_db`, `donor_gain_dbi`, `service_gain_dbi`). No observations,
  moving geometry/time, route split, antenna references or measurement provenance.
- `fixtures/hfss/PTF_V4_Balanced_Cross.s4p` and
  `fixtures/hfss/PTF_V5_Delay25ps_Cross.s4p`: their README explicitly identifies
  HFSS simulation exports, not VNA or installed moving-channel measurements.
- No separate moving-link/operator measurement fixture surfaced in the scoped
  filename inventory. `tests/test_em_channel.py` supplies synthetic bridge-test
  operators; that is plumbing evidence only, not an admitted field dataset.

`hsr_em_channel.h` and `reproducibility/em_bridge_v1_audit.md` remain unchanged.
The C++ schema is `hsr-em-operators-v1`, static single-link, with nine comment
metadata keys and at least two increasing frequencies. Its evidence remains
`synthetic` or `external_unvalidated`; neither means calibrated. This new moving
CSV is deliberately a separate schema, **not a drop-in C++ input or export**.
It may stage one measured frequency per timestamp; that does not satisfy the
existing bridge's multi-frequency occupied-band requirement. Motion, handover,
orientation evolution and Doppler are not enabled by this tooling.

## Primary-source availability audit (checked 2026-09-07)

Scope: a bounded primary-paper/official-repository search for accessible sub-6
railway measurement data. Metadata, papers and small text documentation were
read; no measurement archive was downloaded, repository cloned, author contacted,
permission assumed or public write performed. **No ready-to-admit calibrated HSR
package was verified in these sources.** This is not a claim that none exists.

| Primary source | Observations and download/terms check | Suitability / unresolved gate |
| --- | --- | --- |
| [EURECOM, *Broadband Wireless Channel Measurements for High Speed Trains*](https://www.eurecom.edu/publication/4408/download/comsys-publi-4408.pdf) | Open institutional paper: IRIS320 on LGV Atlantique, about 300 km/h; 771.5 MHz and 2.590/2.605 GHz. Raw IQ acquisition is described; 2.6 GHz recordings save one second in two. No raw archive link or raw-data reuse license was established from the reviewed source. | Best direct train-to-ground acquisition lead here. Obtain raw IQ/derived complex responses, synchronized position/time, actual antenna/reference calibration, gap masks and permitted use. Paper plots and nominal antenna gains alone are insufficient. |
| [DLR, *Wide Band Propagation in Train-to-Train Scenarios*](https://elib.dlr.de/111876/) and its [author paper](https://elib.dlr.de/111876/1/Wide%20Band%20Propagation%20in%20Train-to-Train%20Scenarios%20-%20Measurement%20Campaign%20and%20First%20Results.pdf) | Institutional paper is downloadable; two ETR 500 trains on Naples-Rome, sounding at 5.2 GHz with 120 MHz bandwidth and railway speeds up to 300 km/h. The inspected record exposes the paper, not a verified raw CIR archive/data license. | Genuine HSR sounding lead, but primarily train-to-train, not the installed train-to-ground/coach link. Raw access, calibrated references and applicability remain unresolved; do not transfer its coefficients to another link class. |
| [Raw_BPL_RailNet author repository](https://github.com/kulemandev/Raw_BPL_RailNet), [feature dictionary](https://github.com/kulemandev/Raw_BPL_RailNet/blob/922ce87ab882174b3c177b2db482995cc583d76b/BPL_Dataset_feature_dictionary.csv) | Public raw railway trace files, 107 train folders; small dictionary reviewed, archive not downloaded. Fields include timestamp, speed, cell/balise IDs and dimensionless ordinal UL/DL Rxqual; missing values are preserved. No explicit applicable license established from the reviewed README/root; GitHub API SPDX license field was null. Linked DataPort DOI could not be opened in this check. | Useful potential mobility/handover context, not absolute sub-6 channel gain or complex operator calibration. Dictionary lacks RF frequency/bandwidth and antenna/reference-plane calibration. Do not convert Rxqual to dB or treat many trains on one route as route-disjoint holdout. |
| [Vienna author repository](https://github.com/fpasic1/vienna-channel-sounding) | Public measured time-varying transfer functions at 2.55, 5.9 and 25.5 GHz, controlled indoor rotating-antenna apparatus. README describes shared frequency reference/position trigger. No explicit data license established in the reviewed README/root; API SPDX field null. Reported repository size approximately 5.2 GiB; no bulk download. | Potential high-mobility instrumentation/processing comparison, **not railway field calibration**. Sub-6 subset needs terms and its own metrological review. Lab trajectories cannot be renamed as HSR routes. |
| [SIRADEL railway ray-tracing dataset, Zenodo](https://zenodo.org/records/21113731) | Explicitly synthetic 1900 MHz trajectories, 20 and 100 km/h; CSVs approximately 1.6 MB and 913 kB; total listed package 4.6 MB. Record explicitly states CC BY-NC-SA 4.0. No measurement download performed. | Useful future synthetic parser/trajectory fixture only, subject to terms. Record says raw propagation excludes applied TX power, antenna pattern and bandwidth. Cannot fill those fields or promote simulated paths to measured calibration, even if a related model was validated elsewhere. |

Repository metadata snapshots from read-only GitHub API checks:

- Vienna `main`: `e5000108558cc88a4a45364b5b06a30726783be9` (2023-05-02).
- Raw BPL `main`: `922ce87ab882174b3c177b2db482995cc583d76b` (2026-05-22).

Public availability is not a data reuse grant. License conclusions above mean
“not established in this check,” not a legal determination. A paper's open-access
license must not silently be extended to absent raw measurements. Generic 3GPP
RMa, fitted paper curves and HFSS/ray-traced channels remain synthetic/model
evidence, never a substitute for route-specific installed measurements.

## Evidence required to advance actual moving-train calibration

1. Obtain a permitted, versioned raw **train-to-ground/installed-coach** campaign
   covering the intended RF band, motion and antenna configuration, with independent
   routes for holdout. The EURECOM/DLR papers are acquisition leads, not downloads
   accepted here. Existing four-port fixture coverage does not license frequency
   extrapolation of a 2.6 or 5.2 GHz measurement to another band.
2. Establish synchronized clocks/GNSS/trajectory, calibrated RF gain and noise
   floor, uncertainty budgets, installed antenna patterns/reference planes,
   cable/load/de-embedding, polarization and coherent phase where actually measured.
   Preserve missing/censored samples and document why any observation is excluded.
3. Reproduce raw-to-observable processing. Power-only measurements may support a
   bounded scalar model, but cannot identify D, C_donor and C_service separately.
   Those operators require independently supported measurements/validated EM
   derivation in a common absolute normalization, geometry and phase reference.
4. Independently review acquisition truth, terms, canonical route independence and
   split preregistration. Pin the estimator/parameters/code, calibration-only fit,
   residuals and pre-specified route-held-out metrics with uncertainty and failure
   cases. No such fit or validation has been performed by this work.
5. Only then design and separately validate a time/position/orientation-dependent
   provider, per-link identity, frequency support and appropriate Doppler sampling.
   Do not duplicate a static C++ operator across moving links or label its output
   calibrated. HFSS solver/power validation remains a separate acceptance gate.

## Verification boundary

The isolated standard-library test suite checks admission/denial mechanics,
including synthetic-label rejection, same-physical-route holdout leakage,
exact membership, malformed/finite/positive metadata, missing-value preservation,
hash mutation, unsafe paths, no out-of-support lookup, passive operator bounds and
explicit projections. It runs no HFSS, C++ compiler, ns-3 or campaign. The Windows
symlink-creation test skips if the host denies creating the test link; the remaining
path checks still run. These tests prove software checks, not scientific calibration.
