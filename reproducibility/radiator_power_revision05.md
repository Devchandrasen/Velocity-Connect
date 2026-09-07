# Radiator power audit, Revision 05

## Decision and scope

Radiation-efficiency and absolute-gain claims remain excluded. A stricter
adaptive solve converged but did not satisfy passive power bounds. Matching,
isolation, and guided four-port properties cannot override this failure.
These are simulation diagnostics, not measurements or product qualification.

The compact native projects retained with the implementation are:

- `hfss/Velocity_Connect_n78_V4_PTF_DualSlant_A45_H24_W16_B22_N4_G08_S160_E18_T1_G15_PML_B25_R12_B1.aedt`:
  exact legacy B25/R12 radiator, not the separate B30 geometry.
- `hfss/Velocity_Connect_Vehcom_R05_PowerClosure_B1_Radiation.aedt`:
  completed stricter radiation-boundary diagnostic.

They contain editable models, not bundled solver binaries or complete solved
field databases. Regenerate results with a compatible installed, licensed
Ansys Electronics Desktop. The tested edition was Student 2025 R2 (2025.2),
using PyAEDT 1.3.0. No commercial 2024 solve is claimed. Student limits and
numerical results may depend on solver release and resources.

## Completed comparison

| Model | Adaptive passes | Tetrahedra | Final maximum delta-S | Native efficiency, ports 1 / 2 |
| --- | ---: | ---: | ---: | ---: |
| Legacy B25/R12 PML | 7 | 46,528 | 0.0099823 | 1.016281 / 1.017029 |
| Revision05 first-order Radiation | 11 | 34,585 | 0.0014877 | 1.015502 / 1.015454 |

The second solve required two consecutive converged passes at delta-S 0.005,
up to 18 passes, 10 percent refinement, first-order elements and a 2.5 degree
far-field grid. It is a boundary/refinement diagnostic, not independent solver
validation or established mesh independence. Ratios are raw and not clipped.

A second-order PML attempt was stopped after exhausting available host memory.
Its partial project and interruption audit remain local, excluded from solved
evidence. This failure does not establish a Student licensing or mesh-limit
failure; no such solver conclusion was obtained from the interrupted attempt.

## Regeneration

Use a fresh destination. The following command preserves the completed model
by generating a new one; it may use substantial RAM and takes a valid license.
Do not run concurrently with other memory-heavy solvers.

```powershell
python hfss/build_n78_v2_dualport.py `
  --output hfss/R05_Power_Reproduction.aedt `
  --aedt-version 2025.2 --aedt-edition student --solve --non-graphical --cores 2 `
  --finite-conductivity --open-boundary Radiation `
  --polarization-layout dual-slant --slant-angle-deg 45 `
  --height 24 --top-w 16 --base-w 22 --neck-w 4 --shoulder-h 5 `
  --feed-gap 0.8 --blade-t 0.5 --separation 160 `
  --ground-x 360 --ground-y 180 --ground-t 1 `
  --radome --radome-layout split --radome-permittivity 1.8 `
  --radome-loss-tangent 0.001 --radome-wall-mm 1 --radome-air-gap-mm 15 `
  --maximum-passes 18 --minimum-converged-passes 2 --max-delta-s 0.005 `
  --percent-refinement 10 --basis-order 1 `
  --absorbing-boundary-mesh-mm 25 --far-field-step-deg 2.5

python hfss/audit_radiator_power.py `
  --manifest hfss/R05_Power_Reproduction_manifest.json `
  --convergence hfss/results/n78_v2_dualport/R05_Power_Reproduction/convergence_v2_dualport.conv `
  --output output/R05_Power_Reproduction_audit.json
```

The audit exits with code 2 for failed necessary checks. That is a recorded
negative result, not permission to clip the ratios or omit the run. It checks
convergence, raw powers, finite values, and consistency of reported ratios. It
does not export all conductor/dielectric loss terms or demonstrate full energy
closure. The manifest binds the actual solver controls and exported evidence.

## Source-normalization diagnostic

`hfss/audit_terminal_sources.py` reads a solved terminal project and compares
two active terminals, total/incident voltage sources, and port postprocessing
enabled/disabled: eight contexts. It uses volts explicitly and does not invoke
a new solve or save changes to the source project. Run it only after the
corresponding field database has been generated:

```powershell
python hfss/audit_terminal_sources.py `
  --project hfss/R05_Power_Reproduction.aedt `
  --output output/R05_Terminal_Source_Audit.json
```

The completed Revision05 audit left source-project bytes unchanged. Native
efficiency remained nonphysical in all eight contexts. A generic modal
field-export helper and terminal excitation should not be mixed without
checking conventions, but correcting units alone did not resolve this model.
The sampled integral differs from the native power report and remains only a
same-solver diagnostic; it cannot establish independent energy closure.

Ansys documents the terminal/modal source conventions and the treatment of
accepted power separately:
[source scaling](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/Subsystems/HFSS/Content/ReportsandPostProc/ScalingSourcesforHFSS.htm),
[antenna parameters](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/Subsystems/HFSS/Content/ReportsandPostProc/ComputingAntennaParameters.htm).

Next admissible steps are independent power-term accounting, boundary and
mesh refinement with adequate resources, and expert validation of terminal
reference planes and field-export conventions. No outcome is guaranteed.
