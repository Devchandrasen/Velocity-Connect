# EM bridge v1: bounded installed-transfer interface

## Scientific status and exact blocker

Implemented: an opt-in, frequency-dependent complex 2x2 **transfer-to-SISO-PSD** bridge.
The V4/V5 HFSS fixtures are matched four-terminal networks, not installed radiating
channels. Their transfer submatrix alone cannot determine received power in a coach.
No donor aperture gain, service radiation gain, propagation loss, polarization
conversion, or direct-path phase is invented by this implementation.

**Full physical-coupling blocker:** independently supported complex external
operators mapping the transmitter modes to the donor reference planes, service
reference planes to receiver modes, and the direct radio path in one common
normalization, coordinate system, geometry, and coherent phase reference are absent
from the fixtures. Installed embedded patterns/effective lengths, radiation
efficiency, mutual coupling, terminal loads/de-embedding, cavity/coach interaction,
and calibration or a validated full-wave/ray-wave model are needed to derive these
operators. Arbitrary synthetic test operators are executable plumbing evidence only.
V5's additional terminal phase is not proof of an installed polarization or MIMO benefit.

The current contract accepts **one static gNB/UE link and one BWP**. It rejects
motion, handover, corridors, and multiple nodes because there is no per-link,
time-/orientation-dependent installation-operator provider. A larger study must
be explicitly generic/conditional and extend that provider before reusing this
mode; duplicating one static operator across all links is not implemented.

## Pinned source/API audit

Read directly in `/home/codex/velocity-connect-ns3-v5` on Ubuntu-22.04:

- ns-3.48 commit `d2add90b452d600cfb4859baed8e9ea633519447`.
- 5G-LENA v5.0 commit `47a3adc263f773556eaadac5a5341458dbc61c47`.
- `src/spectrum/model/multi-model-spectrum-channel.cc`: the generic spectrum
  and phased-array models are mutually exclusive `if / else if` branches in
  receive processing. Adding a generic model alongside ThreeGpp would bypass
  the latter. This bridge therefore makes replacement explicit.
- `contrib/nr/helper/nr-channel-helper.cc`: `AssignChannelsToBands(bands, 0)`
  creates channels without scalar propagation or fading, and retains the NR
  CSI-RS filter. `GetChannel()->AddSpectrumPropagationLossModel(model)` installs
  the custom model; no dependency source edits are needed.
- `src/spectrum/model/spectrum-propagation-loss-model.h`: override
  `DoCalcRxPowerSpectralDensity(Ptr<const SpectrumSignalParameters>,
  Ptr<const MobilityModel>, Ptr<const MobilityModel>) const`; return a new
  `SpectrumValue`, never mutate the transmitted PSD.
- `contrib/nr/model/nr-spectrum-phy.cc` and `nr-interference.cc`: the scalar
  path operates without a `spectrumChannelMatrix`. The bridge does not populate
  one. SISO CQI feedback is selected explicitly, with one non-dual-polarized
  isotropic array element/port; ideal beamforming is not installed.
- `contrib/nr/helper/nr-helper.cc`: `AssignStreams` assigns device and channel
  streams; the channel helper returns safely when no ThreeGpp scalar path exists.
  Explicit separate channel blocks are applied after device helper assignment.
  `ThreeGppSpectrumPropagationLossModel::DoAssignStreams` itself returns zero:
  the underlying `ThreeGppChannelModel` must be assigned directly.

The installed ns-3 tree already contains the project's IPv4 robustness changes;
it is not an unmodified upstream checkout. This work leaves those changes and
all dependencies untouched. The versioned build pin records actual tracked diff,
API-file and library hashes in addition to both upstream commits. C++20 is
required for ns-3.48; the independent transfer header/tests also compile as C++17.

Primary documentation checked: [NR channel helper](https://cttc-lena.gitlab.io/nr/html/classns3_1_1_nr_channel_helper.html)
(online page is newer than v5.0; installed source controls the API decision), and
[IBIS Touchstone 2.0 specification](https://ibis.org/touchstone_ver2.0/touchstone_ver2_0.pdf)
(original/1.0 syntax, full 3-/4-port row-major ordering, complex formats and real
reference resistance). The loader intentionally supports a strict subset:
explicit unit/S/RI-or-MA-or-DB/R-50 options and full four-port 1.0 data only.
Unsupported keywords, mixed-mode/reference variants, missing/duplicate frequencies,
non-finite values, malformed rows, extrapolation, nonreciprocity, and nonpassivity
are rejected; unsupported formats are never guessed.

## Transfer, mappings, reciprocity, and energy accounting

All matrices are row-major: output mode is the row and input mode the column.
The physical fixture order is donor terminals 1/2, service terminals 3/4. These
terminal names are **not** an assertion that they are calibrated orthogonal
radiating polarizations.

```text
T_cross(f) = S[service rows 3,4 ; donor columns 1,2]
P = [[0,1],[1,0]]
T_straight(f) = P T_cross(f)
H_DL(f) = D(f) + C_service(f) T_mapping(f) C_donor(f)
a_DL(f) = q^H H_DL(f) p
PSD_RX[k] = PSD_TX[k] |a_DL(f_k)|^2
```

`straight` is a counterfactual service-terminal permutation of a supplied cross
fixture, including its complex residual terms; it is **not** a separately solved
straight HFSS geometry. The external service basis stays fixed. A coordinate
relabeling would also transform the operator/projection and would be invariant.

For reciprocal, equal-real-impedance ports:

```text
H_UL = H_DL^T                   # transpose, NOT Hermitian adjoint
p_UL = conjugate(q_DL)
q_UL = conjugate(p_DL)
```

This gives the same reciprocal complex scalar amplitude even for elliptical
Jones vectors. Simply swapping unconjugated elliptical vectors need not do so.
The entire composed matrix is transposed, reversing the operator order correctly.
The model classifies DL/UL using the actual configured mobility identities;
known same-role links pass through unchanged and unknown links fail closed.
There is no coach attenuation broadcast to all transmitters or same-role links.

In `em_complex`, both transmit powers retain their configured values. Stock NR
pathloss, fading, scalar coach attenuation, component gains/losses, and ideal
array beamforming are not applied. Therefore no scalar loss is counted twice.
The external operator must include **all** corresponding end-to-end effects.
`eff_loss_db` and component budget fields are `nan` for EM runs, because no one
frequency-independent equivalent loss is asserted. The scalar default remains
`component_budget`, with unchanged 5 dB default attenuation and normal NR path.

The four-port check tests positive semidefiniteness of `I-S^H S` by Cholesky with
1e-8 numerical power tolerance, not just individual entries/column energies.
Input operators and the evaluated total matrix must be contractions in their
declared normalized power-wave bases. Inconsistent coherent sums are rejected,
not clipped or rescaled. These local checks do not prove a globally passive,
causal loaded radiating network. All ports are assumed matched; multiple
reflections/load feedback are not solved by a simple forward transfer cascade.

Complex values are linearly interpolated in Cartesian coordinates; this preserves
phase-sensitive interference without phase-wrap mistakes but may underestimate
amplitude between sparse rotating samples. Every configured band edge must be
covered; every actual ns-3 band centre is evaluated independently. PSD within an
RB is approximated by that centre value. No time-domain impulse response, group
delay packet shift, ISI, Doppler, or within-symbol nonstationarity is inferred.

## External operator CSV contract

CLI fields (only `em_complex` activates them):

```text
--singleRun=1 --passiveModel=em_complex --speed=0 --numUes=1 --numGnbs=1
--emTouchstone=<path to V4/V5 cross .s4p>
--emOperators=<path to required external operator CSV>
--emMapping=cross|straight
--outDir=<fresh empty directory>
```

The CSV begins with exactly these nine metadata keys, before its header:

```text
# schema=hsr-em-operators-v1
# provenance=<source dataset/measurement/model identifier and derivation>
# evidence=synthetic
# normalization=absolute_power_waves_50ohm
# basis=<terminal and radio modal coordinates, coherent phase/reference-plane convention>
# gnb_position_m=0,0,10
# ue_position_m=500,0,1.5
# tx_projection=1,0,0,0
# rx_projection=0.6,0,0.8,0
```

The displayed projections/geometry illustrate the **synthetic test** only; none
is a model default. `evidence` may alternatively be `external_unvalidated`;
the simulator cannot certify an input as measured/calibrated. Each projection
is `p0_re,p0_im,p1_re,p1_im` and must already have unit power norm. Positions
must equal the configured gNB and UE positions, including heights/lateral offset.

The exact header is generated by `hsr::em::OperatorHeader()`:

```text
frequency_hz,d00_re,d00_im,d01_re,d01_im,d10_re,d10_im,d11_re,d11_im,in00_re,in00_im,in01_re,in01_im,in10_re,in10_im,in11_re,in11_im,out00_re,out00_im,out01_re,out01_im,out10_re,out10_im,out11_re,out11_im
```

`d` is D, `in` is C_donor, `out` is C_service. Supply at least two strictly
increasing frequencies covering the occupied bandwidth, with twelve complex
coefficients per row. Matrices may be nondiagonal and frequency-dependent.
Zeros, including a zero direct path, must be supplied explicitly. Every numeric
value is finite. No implicit normalization, extra gain, missing-value fill,
frequency clamping, or automatic external operator synthesis is performed.

## Output and RNG coordination

`single_run.csv` appends `channel_path,em_mapping,em_touchstone,em_operators,
nr_rng_stream,channel_rng_stream,common_channel_realizations_verified` while
retaining earlier columns. EM's `channel_path` is `em_absolute_static_siso`.
The old `nr_scenario`/`nr_condition` configuration fields remain for schema
continuity but are **inactive** on this replacement path.

Each EM output directory contains:

- `em_bridge_audit.md`: formula, evidence tier, normalization and limitations.
- `em_bridge_input.s4p`, `em_bridge_operators.csv`: exact input bytes.
- `em_bridge_bands.csv`: first active transmission per direction/RB, actual band
  boundaries, complex amplitude, gain, input and output PSD in W/Hz.
- `em_bridge_runtime.csv`: actual DL/UL channel call and band-evaluation counts.
- The existing packet/UE metrics; PSD differences need not cause different
  packet outcomes at a given MCS/load/SINR operating point.

Optional `--nrRngStream=N` applies `NrHelper::AssignStreams` to gNB then UE
devices. `--channelRngStream=M` overrides the scalar ThreeGpp path, condition,
and matrix-channel RNG block after helper assignment. Blocks must not overlap.
`-1` preserves automatic/helper assignment. An EM channel is deterministic and
rejects a separate channel RNG override as inapplicable. `rng_stream_audit.csv`
records starts/counts. Device counts, access order and treatment paths can alter
draw consumption: **same seed/run/stream IDs are not verified common channel
realizations**. That output flag remains zero. No claim is made to assign every
Internet/EPC/application RNG or produce event-by-event common random numbers.

## Bounded verification and reproducible build pin

Initial verification passed: 42 standalone numerical/config checks (both actual
21-frequency V4/V5 fixtures), pinned ns-3 PSD/reciprocity/role/geometry tests,
and a 0.4 s CLI V4-cross smoke. That smoke sent/received 36/36 packets, executed
145 DL and 71 UL channel calls and 114600 band evaluations. These numbers prove
execution mechanics for the synthetic operator fixture, not physical validity.

Numerical coverage includes Cartesian interpolation; cross/straight mapping;
candidate/frequency effects; destructive cancellation and constructive coherent
addition; complex transpose reciprocity with elliptical modes; singular-value
and complete-receive-basis invariance under a unitary mapping; common unitary
coordinate invariance; malformed/unsupported inputs; passivity (including a
matrix with safe individual column powers but unsafe spectral norm); no duplicate
scalar attenuation; and bounded geometry/config rejection. Packet differences
are never required by the tests.

Reproduce the standalone numerical suite on Linux with
`python3 tests/test_em_channel.py` (or pytest). For a serial isolated build plus
four 0.4 s EM smokes and one 0.4 s scalar control, use:

```sh
python3 tests/test_em_channel.py \
  --ns3 /home/codex/velocity-connect-ns3-v5 \
  --work-dir /home/codex/buildprovenance/velocity-em-bridge-v1-NEW
```

The destination must not exist. The script compiles an immutable snapshot of all
`hsr_*` inputs against existing installed headers/libraries; it never invokes the
ns-3 dependency build or a campaign. It checks the snapshot still matches the
authoritative sources before writing `em_bridge_build_pin_v1.json`. This pin
contains `binary.sha256`, `synced_source_sha256` keyed by relative `hsr_*`
filenames, both upstream commits, compiler/header/library paths and hashes,
commands, synthetic input hashes, actual smoke results and audit paths. It is
compatible with `inspect_binary` in the validation driver.
Old build pins and shared results are never overwritten.

### Final execution evidence, 2026-09-07

Serial build and all bounded tests completed successfully with GCC 11.4.0 against
the installed ns-3.48/5G-LENA v5.0 libraries. Final pin:

`/home/codex/buildprovenance/velocity-em-bridge-r05-portable-20260907/em_bridge_build_pin_v1.json`

Binary:
`/home/codex/buildprovenance/velocity-em-bridge-r05-portable-20260907/hsr_velocity_connect`

Binary SHA-256:
`a57f40ab95bf1a3b4edb69dc564e7b39f4a821710b751898529adb8885755d8d`

The validation driver's `inspect_binary` accepted this pin and all nine current
authoritative `hsr_*` source hashes. No old v3 pin was overwritten. Tests passed:

- 42 standalone numerical/config checks and the pinned per-band PSD integration test.
- V4-cross DL, V4-straight DL, V5-cross DL, and V5-cross UL; each 0.4 s, one
  static link, seed 41/run 1, NR streams starting at 1000, synthetic operators.
- The three DL cases each received 36/36 packets: **different received PSDs did
  not force different packet outcomes**. UL received 34/36; this is a direction
  smoke, not a paired candidate advantage. Every smoke exercised both directions
  of the reciprocal channel through NR data/control signalling.
- Scalar `component_budget` control, 0.4 s, 36/36 received, 5 dB attenuation,
  35 dBm effective gNB power; explicit channel RNG block starting at 100000.
- Missing operators and reused non-empty EM output directories rejected.
- No dependency rebuild or full campaign was part of this bounded verification.

This pin supersedes the initial same-day build after a Windows GCC portability
fix: named arrays now own the parsed projection/position descriptors, avoiding
a dangling-reference warning from a temporary initializer list. All numerical
and pinned integration tests were rerun. Subsequent campaign-driver smokes are
documented in `vehcom_campaign_protocol.md`; they are not scientific campaigns.

Each treatment's audit is under the pin's parent directory, e.g.
`v4-cross/em_bridge_audit.md`. Exact commands, runtime call counts, PSD samples,
operator bytes and input hashes are preserved. HFSS physical convergence is a
separate gate; these successes do not imply convergence, installed radiation
efficiency, calibrated coupling, full MIMO, or a complete installed product.
