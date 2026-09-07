# Revision 06: retained nonphysical HFSS power budget

These are unchanged exports from the completed read-only audit in
`output/vehcom_revision06/guarded_power_02`. The source is the retained
`hfss/Velocity_Connect_Vehcom_R05_PowerClosure_B1_Radiation.aedt`, SHA-256
`d671f9c8fd9209e1ca735b49bd1836e880828bb73cfc8db58774ca1df9b97415`.
The source project's bytes were unchanged by the audit. This fixture is a
numerical failure case, not an accepted radiator or railway measurement.

Both ports use the same explicit incident-voltage excitation convention for
native powers, losses and fields: active terminal 1 V, other terminal 0 V,
port postprocessing disabled, 3.55 GHz last adaptive solution. Complex field
exports retain the native millivolt wrappers and explicit angular coordinates.
Primary and adjacent conductor-surface results are retained separately and
are not added twice. Native radiated power is also cross-checked against the
signed radiation-boundary Poynting flux.

```powershell
python hfss/replay_power_budget_revision06.py
```

Successful replay means the recorded discrepancy is independently recomputed
from these exports. It is **not** a fresh HFSS solve or physical validation.
The raw native radiation efficiencies are approximately 101.5607% and
101.5568%; input closure errors are +1.8162% and +1.8124% of accepted power.
Coordinate-integrated far-field powers disagree with native radiation by
approximately 3.3157% and 3.3180% of accepted power. No ratio is clipped.

`resource_guard.json` records the actual completed audit's memory limits and
source hashes. `power_budget_report.json` and per-port records preserve the
original export context. Global source-manifest verification checks the exact
bytes of every compact export. Full adaptive result databases and interrupted
attempts remain outside this small fixture, at their original local paths.
