# Velocity Connect HFSS workspace

This folder contains the Ansys Electronics Desktop Student models for the
sub-6 GHz passive railway feedthrough.

## Baseline design contract

- NR band: n78
- Analysis band: 3.3-3.8 GHz
- Centre frequency: 3.5 GHz
- Reference impedance: 50 ohm
- First model: single-port, vertically polarised roof donor antenna
- Baseline family: low-profile blade/monopole with quasi-omnidirectional
  azimuth coverage
- Later models: service antenna, passive two-port feedthrough, simplified
  metal enclosure

The donor baseline is intentionally not a narrow-beam patch. A train can pass
a serving site in either direction and over a wide range of azimuth angles, so
the first prototype prioritises n78 bandwidth and azimuth coverage. Directional
or diversity variants can be compared after the baseline is measured.

## Local automation

Create an isolated Python environment in the repository with:

```powershell
py -3.12 -m venv .venv-hfss
.\.venv-hfss\Scripts\python.exe -m pip install -r hfss\requirements-hfss.txt
```

The generator creates
`hfss\Velocity_Connect_n78_Student.aedt` with a parameterised donor design,
radiation region, port, solution setup, and an n78 frequency sweep. Generation
and solving are separate operations so the model can be inspected before a
potentially long solve.

```powershell
.\.venv-hfss\Scripts\python.exe hfss\build_n78_donor.py
.\.venv-hfss\Scripts\python.exe hfss\solve_n78_donor.py
.\.venv-hfss\Scripts\python.exe hfss\analyze_n78_matching.py
```

## Current solved checkpoint

The Student 2025 R2.4 project has been generated and solved as
`VC_Donor_n78 / Setup_n78 / Sweep_n78` over 3.3–3.8 GHz at 51 points. The
baseline bare blade is not acceptably matched:

- S11 at 3.5 GHz: -6.26 dB
- best sampled S11: -6.53 dB at 3.69 GHz
- points at or below -10 dB: 0 of 51

A circuit cascade derived from the solved terminal impedance uses an initial
low-pass pi network of 2.4 pF shunt at the antenna, 1.8 nH series, and 1.5 pF
shunt at the connector. With the component-Q assumptions recorded in the
matching manifest, its nominal predicted worst-band S11 is -12.57 dB and all
51 points meet -10 dB. A 5000-sample, +/-5% Monte Carlo predicts 99.78%
full-band pass, but the worst explicit tolerance corner is -9.63 dB. These are
post-processed circuit predictions, not a 3-D matching-board co-simulation or
measurement.

Controlled evidence:

- `Velocity_Connect_n78_Student_solve_manifest.json`
- `results\n78_baseline\s11_n78.csv`
- `Velocity_Connect_n78_Student_matching_manifest.json`
- `results\n78_matching\matching_network_response.csv`
- `results\n78_matching\matching_network_response.png`

The `.prof` and `.conv` files are solver diagnostic/convergence files, not
Touchstone exports. The current evidence establishes only single-solve,
centre-frequency adaptive S-parameter convergence. It does not establish mesh,
field, gain, efficiency, or boundary independence.

## V2 native-match dual-port checkpoint

The V2 work replaces the external matching-network approach with a 21 mm
quarter-wave tapered monopole and then places two elements in orthogonal
vertical planes. The selected numerical-validation project is:

`Velocity_Connect_n78_V2_DualPort_S150_PowerQA_B25_B1.aedt`

It uses finite-conductivity metal, a PML open boundary, a 360 x 180 mm roof
coupon, 150 mm element separation, idealized lumped-sheet feeds, and a 25 mm
PML-interface mesh seed. Its single adaptive S-parameter solve reached eight
passes and 54,035 elements with final
`Max Mag. Delta S = 0.0039501`. Across 3.3-3.8 GHz, the solved result has:

- worst S11/S22: -15.25/-15.23 dB;
- worst S12/S21 isolation: -21.32 dB;
- worst-phase TARC: -11.79 dB;
- maximum S-parameter ECC: 0.000903;
- minimum diversity gain: 9.999996 dB;
- maximum channel-capacity loss: 0.1109 bit/s/Hz.

On the selected 1-degree full-sphere grid, cached complex embedded-field
postprocessing gives diagnostic values:

- embedded-field ECC: 0.000314;
- embedded-field diversity gain: 9.9999995 dB;
- raw peak realized gain: 5.73/5.55 dBi;
- raw field-integrated total-efficiency ratio: 98.44%/98.35%;
- unweighted ideal-selection upper-horizon grid samples at or above 0 dBi:
  95.64%.

Strict physical power closure fails on both ports because the
field-integrated radiation-efficiency ratios are 101.013% and 100.929%.
Therefore absolute gain, efficiency, and installed coverage are excluded from
acceptance gates and network inputs. The 5-degree, 2.5-degree, and 1-degree
results close only the angular-integration check; the residual is
solve/boundary-level. A finer independent HFSS solve and measurement are
required.

Generate or post-process the V2 models with:

```powershell
.\.venv-hfss\Scripts\python.exe hfss\build_n78_v2_element.py --solve
.\.venv-hfss\Scripts\python.exe hfss\build_n78_v2_dualport.py --solve --separation 150 --ground-x 360 --ground-y 180 --finite-conductivity --open-boundary PML --absorbing-boundary-mesh-mm 25 --maximum-passes 8 --minimum-converged-passes 1 --max-delta-s 0.01 --percent-refinement 15 --output hfss\Velocity_Connect_n78_V2_DualPort_S150_PowerQA_B25_B1.aedt
.\.venv-hfss\Scripts\python.exe hfss\postprocess_n78_v2_fields.py hfss\Velocity_Connect_n78_V2_DualPort_S150_PowerQA_B25_B1.aedt --far-field-step-deg 1 --output hfss\results\n78_v2_dualport\Velocity_Connect_n78_V2_DualPort_S150_PowerQA_B25_B1\embedded_pattern_metrics_1deg.json
.\.venv-hfss\Scripts\python.exe hfss\summarize_n78_v2_field_convergence.py
.\.venv-hfss\Scripts\python.exe hfss\compare_n78_v2_candidates.py
```

The engineering interpretation, literature benchmark, product architecture,
and remaining evidence gates are documented in
`N78_V2_DESIGN_AND_LITERATURE_BENCHMARK.md`.

## V3 installed-radome screening checkpoint

The generator now supports AEDT release/edition selection, a cylindrical roof
surrogate, and common or split open-bottom radomes with explicit dielectric
and dimensional controls.

The selected installed screening model is
`Velocity_Connect_n78_V3_SplitRadomeFlat_E18_T1_G15_S160_PML_B30_B1.aedt`.
It uses two separated low-loading radome pods, 160 mm element spacing, a
finite-conductivity flat roof coupon, PML, and a 30 mm PML-interface seed.
Across 3.3-3.8 GHz it gives:

- worst S11/S22: -14.83/-14.91 dB;
- worst S12/S21 isolation: -21.53 dB;
- worst-phase TARC: -11.68 dB;
- maximum S-parameter ECC: 0.000873;
- maximum channel-capacity loss: 0.1179 bit/s/Hz;
- centre-frequency normalized embedded-field correlation diagnostic: 0.0137.

This is a **provisional two-port S-parameter screening candidate**, not a
final antenna. Its field-integrated radiation efficiencies are 101.997% and
101.863%, so strict physical power closure fails. Raw gain and the unweighted
ideal-selection angular-grid diagnostic are not acceptance evidence. The B30
mesh has 45,313 elements
and final `Max Mag. Delta S = 0.0068579`. A tighter B25,
`MaxDeltaS <= 0.005` attempt reached 64,890 volume elements and was rejected
by AEDT Student's mesh limit.

Regenerate the machine-readable candidate ledger with:

```powershell
.\.venv-hfss\Scripts\python.exe hfss\summarize_n78_v3_installed.py
```

The outputs are
`results\n78_v3_installed\installed_candidate_summary.csv` and
`installed_candidate_summary.json`.

### AEDT 2024 R1 commercial continuation

AEDT 2024 R1 can be selected through `ANSYSEM_ROOT241`. A valid
institutional or commercial entitlement must be configured before claiming a
2024 solve. No licence configuration is stored in this repository.

After the licence is fixed, regenerate a 2024-native project rather than
opening a 2025 project backward:

```powershell
$env:ANSYSEM_ROOT241 = 'C:\Program Files\AnsysEM\v241\Win64'
.\.venv-hfss\Scripts\python.exe hfss\build_n78_v2_dualport.py --overwrite --solve --non-graphical --aedt-version 2024.1 --aedt-edition commercial --separation 160 --ground-x 360 --ground-y 180 --finite-conductivity --open-boundary PML --roof-radius-mm 1500 --radome --radome-layout split --radome-permittivity 1.8 --radome-loss-tangent 0.001 --radome-wall-mm 1 --radome-air-gap-mm 15 --absorbing-boundary-mesh-mm 25 --maximum-passes 12 --minimum-converged-passes 2 --max-delta-s 0.005 --percent-refinement 15 --output hfss\Velocity_Connect_n78_V3_Installed_R1500_SplitRadome_E18_T1_G15_S160_AEDT2024_B25_D005_B2.aedt
```

The licensed run still needs a B20 or approximately 1.5x mesh-density check,
band-edge embedded fields, radome tolerances, and VNA/OTA measurement.

## Native projects and compact exports

The repository retains selected small `.aedt` projects for inspection and
regeneration. The solved four-port Touchstone copies in `fixtures\hfss` allow
path-independent numerical checks without committing the large AEDT result
trees. Hardware handoff documents and fabrication outputs are intentionally
outside the implementation repository.

## Evidence boundary

HFSS results are electromagnetic design evidence, not physical validation.
Final S-parameters, gain, efficiency, and cabin fields must be checked with
calibrated VNA and OTA measurements before they are used as product claims.

The Student edition is suitable for component and simplified-enclosure models.
It does not provide the SBR+/Hybrid workflow required for a realistic
full-coach installed-antenna model.
