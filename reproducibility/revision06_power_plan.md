# Revision 06 power-closure correction protocol

The target is a physically consistent energy budget, not a forced ratio below
100 percent. Changing materials to add arbitrary loss, clipping efficiencies,
or replacing accepted power by radiated-plus-loss power would hide the defect.

## Executable corrections

- `hfss/power_balance.py` integrates explicit theta/phi coordinates, independent
  of row order. It checks full-sphere support, duplicate/nonfinite points and
  angular units, using peak-phasor power conventions. It does not guess the
  ordering of a flattened export.
- `hfss/export_power_budget_revision06.py` uses explicit 1 V incident terminal
  excitation, zero on the other terminal and raw port postprocessing for both
  native powers and field exports. The legacy generic modal-source helper is
  not used. The geometry and original saved project are not changed.
- Native powers, surface conductor losses, dielectric volume losses, signed
  boundary Poynting flux and coordinate-labelled complex far fields are queried
  separately. Both sheet sides are retained for expert accounting; they are
  not blindly summed. An unavailable export is an error, not zero loss.
- The offline budget evaluator reports raw radiation efficiency, field-derived
  efficiency, input-balance residual and a separate loss-based ratio. The last
  ratio never overrides a raw efficiency or closure failure.

## Predeclared gates

The diagnostic input-closure and native/field agreement tolerance is 0.5 percent
of accepted power. This is an engineering numerical-accuracy gate, not a
measurement uncertainty or standard. Raw passive power ratios still must not
exceed unity. Passing one solve would establish only necessary numerical checks;
mesh/boundary independence and an independent cross-check remain separate.

For the present 15.4 GiB host, unguarded postprocessing defaults to 4 GiB
available RAM. A separate read-only process guard admits at 1.5 GiB, caps the
owned process-tree working set at 1.25 GiB, requires a 0.5 GiB host reserve and
stops on a 600-second wall limit. This narrower policy was adopted before the
read-only run, not to change a scientific acceptance threshold. It has no solve
command. The first two unguarded attempts were refused at 1.970 and 1.808 GiB
available. Source bytes remained unchanged.

The first guarded export identified an actual HFSS format mismatch: real-valued
expressions were exported as complex wrappers in millivolts. The reader now
checks that wrapper imaginary components are zero and explicitly converts voltage
units. The failed attempt is retained. The second guarded export completed with
a 0.895 GiB peak owned working set and 2.990 GiB minimum available host RAM.

For port 1, incident power is 0.010000 W, accepted power 0.009537843 W, native
radiated power 0.009686701 W and coordinate-integrated radiation 0.010002943 W.
Primary-side conductor plus dielectric losses total approximately 0.000024368 W.
The input closure residual is +1.8162 percent; native/field disagreement is
3.3157 percent of accepted power. Port 2 gives the same qualitative failure.
The 99.749 percent loss-based diagnostic is **not** an efficiency correction:
it has a different denominator and cannot repair the accepted-power imbalance.
The raw native efficiencies remain 101.5607 and 101.5568 percent under the
explicit incident-voltage source context. This differs slightly from the old
total-voltage context and does not overwrite those earlier values.

Native radiated power and directly integrated signed boundary flux agree much
more closely (port-1 flux 0.009681774 W). This narrows the diagnosis but does
not yet establish whether the remaining accepted-power/field error is caused by
mesh, reference-plane treatment or their interaction. The next controlled test
changes boundary maximum edge length from 25 to 15 mm only; its first launch
was refused for 1.32 GiB host memory before any new model was created.

After free memory recovered, that same 15 mm refinement was admitted. It failed
because Ansys Student refused its 64,394 volume elements, not because of the
resource guard. The run used a 1.056 GiB peak owned working set and retained
3.068 GiB minimum host memory. Its failed project and complete error manifest
are retained at `W:/Velocity-Connect-Revision06/hfss_boundary15_01`. There is no
solved power result from this attempt. An intermediate 20 mm boundary mesh is
the next single-factor comparison; it must obey the same physical gates.

The 20 mm attempt was subsequently admitted at
`W:/Velocity-Connect-Revision06/hfss_boundary20_01`. The process guard stopped it
after 105.19 seconds when its sampled owned working set reached 2.808 GiB,
above the predeclared 2.75 GiB cap. Minimum free host memory was 0.918 GiB.
The partial model is **not solved evidence**; its builder manifest still says
`started` because the guard interrupted the process. The authoritative terminal
state for this attempt is `resource_guard.json` with
`interruption_reason: owned_working_set_cap`. It is not resumed or overwritten.
No refined efficiency or gain has been obtained. A future fresh repeat requires
adequate RAM and a declared resource envelope; it must not relax the physical
acceptance gates or bypass the Student solver limit.

```powershell
.venv-hfss/Scripts/python.exe hfss/export_power_budget_revision06.py `
  --project hfss/Velocity_Connect_Vehcom_R05_PowerClosure_B1_Radiation.aedt `
  --out output/vehcom_revision06/power_budget_new_attempt
```

Use a new destination for each attempt. Do not discard the earlier reports.

Guarded commands (fresh destinations; no unrelated process is stopped):

```powershell
hfss/run_power_audit_guarded.ps1 `
  -Project hfss/Velocity_Connect_Vehcom_R05_PowerClosure_B1_Radiation.aedt `
  -OutputDirectory output/vehcom_revision06/guarded_power_new

hfss/run_boundary_refinement_revision06.ps1 `
  -OutputDirectory W:/Velocity-Connect-Revision06/hfss_boundary15_new

hfss/run_boundary_refinement_revision06.ps1 -BoundaryMeshMm 20 `
  -OutputDirectory W:/Velocity-Connect-Revision06/hfss_boundary20_new
```

The adaptive refinement requires 3 GiB available RAM before launch, caps its own
process tree at 2.75 GiB and stops at a 0.5 GiB host reserve or 900 seconds.
Creating `STOP_REQUESTED` inside its new output directory requests a stop.
Any interrupted partial project is retained and excluded from solved evidence.

## Subsequent correction depends on the observed budget

1. If explicit-coordinate far-field integration disagrees with the legacy
   flattened result, correct the export/integration pipeline and regenerate
   every dependent quantity without modifying the historical artifacts.
2. If port power disagrees with boundary flux plus independently checked losses,
   audit terminal reference planes, impedance/source conventions and conductor
   boundary accounting before design optimization.
3. If the remaining discrepancy is mesh/boundary sensitive, compare the same
   geometry with refined absorbing boundaries and higher-order or mixed-order
   elements under sufficient licensed resources. Stop on memory or Student
   limits; do not call an interrupted solve converged.
4. Admit absolute gain/efficiency only after the above checks pass at the
   frequencies and excitations being claimed. A single center-frequency check
   is not full-band validation.

Primary technical basis:
[Ansys peak/RMS convention](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/Subsystems/HFSS/Content/HFSS/PeakVersusRMSPhasors.htm),
[field loss quantities](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v252/en/Subsystems/HFSS/Content/ReportsandPostProc/QuantityCommand.htm).
