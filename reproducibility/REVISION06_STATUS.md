# Revision 06: scientific validation and execution status

Recorded 7 September 2026. **Not submission-ready.** This revision strengthens
the checks and starts additional simulation work; it does not close the physical
antenna or moving-train calibration gates. No acceptance prediction is made.

## What has actually been established

The same-excitation HFSS audit is complete. Both terminals were evaluated with
one 1 V incident source, the other at 0 V, and port postprocessing disabled.
Explicit angular coordinates and voltage units are used throughout. Original
project bytes and all failed attempts are retained.

| 3.55 GHz radiation-boundary diagnostic | Port 1 | Port 2 |
| --- | ---: | ---: |
| Native raw radiation efficiency | 101.5607% | 101.5568% |
| Coordinate-integrated field efficiency | 104.8764% | 104.8748% |
| Native radiation plus primary-side losses minus accepted power, relative to accepted power | +1.8162% | +1.8124% |
| Field radiation minus native radiation, relative to accepted power | +3.3157% | +3.3180% |

This is a reproducible numerical imbalance, not an efficiency correction.
The approximately 99.749% loss-based ratio uses a different denominator and is
explicitly excluded as a substitute. Conductor sheet-side accounting still needs
expert review. Native radiation closely agrees with signed boundary flux, but
that does not establish the cause of the remaining accepted-power/field error.

The field parser's actual HFSS millivolt/complex-wrapper mismatch was corrected.
That software correction alone did **not** remove the numerical imbalance.
The full exports are replayable without Ansys:

```powershell
python hfss/replay_power_budget_revision06.py
```

### Controlled refinement attempts

1. The 15 mm boundary mesh was initially refused for insufficient host RAM.
   Once admitted, it reached 64,394 volume elements and Ansys Student rejected
   the solve for exceeding its simulation size limit. No power result exists.
2. The 20 mm boundary mesh was admitted but stopped by the process guard after
   105.19 seconds: sampled owned working set 2.808 GiB exceeded the 2.75 GiB cap.
   Minimum available host RAM was 0.918 GiB. The partial model is excluded.

Projects, logs and terminal guard records remain under
`W:/Velocity-Connect-Revision06/hfss_boundary15_01` and `hfss_boundary20_01`.
The latter builder record says `started` because the guard interrupted it;
its terminal `resource_guard.json` takes precedence. Neither attempt is resumed
or called converged. A fresh controlled solve needs sufficient RAM and a mesh
within the licensed limit; the license is not bypassed. No more HFSS work is
started while the network queue owns the resource window.

## Expanded simulation work

All **680** new baseline identities are frozen: principal 160,
channel-sensitivity 160, load 360. The separate resource-only pilot completed
with GNU time peak RSS 75.47 MiB and wall time 71.65 seconds. That pilot is
excluded from the scientific campaign and from performance comparisons.

At 08:00:22 UTC, invocation `run02` launched the **320-row principal plus
channel-sensitivity queue**, one simulator process at a time. The first row's
`running` ledger event was verified. That row subsequently exited zero and passed
the runner's output checks at 08:01:39 UTC; the next scalar-reference row started.
This is execution, not completed analysis or a treatment comparison.
The 360 load rows have not been launched. The queue has a 12-hour invocation
budget, 30-minute per-row timeout, 512 MiB child address-space cap, live resource
guards and no retries of failed/interrupted scientific rows. Its local process
continues only while the computer and required WSL runtime remain available;
there is no scheduler, automatic restart or notification service.

The first wrapper invocation, `run01`, failed in native WSL argument parsing
before any scientific row started. Its logs are retained. The wrapper was fixed
and `run02` uses a fresh log directory; no scientific failure was discarded.

These experiments use the existing direct and declared-scalar reference models.
They are **not calibrated moving-train EM-to-network experiments**. Both UMi and
RMa LOS remain channel-model sensitivity cases. Identical seed/run IDs alone do
not establish common channel realizations. Complete terminal results still need
the frozen analyzer's raw-hash, trace and metric reconciliation before any
performance statistics can be used in the paper.

### Read progress and request a safe stop

```powershell
wsl -d Ubuntu-22.04 -u codex -- python3 -B `
  /mnt/w/Velocity-Connect-Revision06/campaign-20260907-v1/runtime/scripts/run_vehcom_revision06.py `
  status --out /mnt/w/Velocity-Connect-Revision06/campaign-20260907-v1

# Between-row safe stop: the active row finishes under its own guards.
New-Item -ItemType File -Path W:/Velocity-Connect-Revision06/campaign-20260907-v1/STOP
```

Do not start a second queue while one is active. Do not rebuild the pinned
simulator or shared libraries during execution. After a safe stop, resumption
requires checking the terminal state and keeping the stop request as a renamed
record; only still-planned rows are eligible. See
`vehcom_revision06_execution.md` for recovery restrictions.

The frozen protocol copy contains an inaccurate attribution that the narrower
historical scan was directly "user-approved". It was selected by the task's
implementation review within the requested work, not by a separate user answer.
The workspace document is corrected. The frozen copy is retained unchanged for
integrity; this erratum does not alter plans, identifiers or acceptance criteria.
Five header-only diagnostic histories still lack full RNG provenance. Exact
inspection scope and those failures are retained; global uniqueness is not
claimed.

## Moving-train coupling and declarations

`calibration/measurement_contract.py` now rejects incomplete provenance,
unsupported units, out-of-support queries, route/observation leakage and synthetic
data mislabeled as calibration input. It validates package integrity and
completeness, **not measurement authenticity or scientific calibration**. There
is no fitted moving-link model or bridge export from this module.

The bounded primary-source search did not verify a ready-to-admit installed-link
railway dataset. Actual progress needs permitted raw measurements, synchronized
trajectory, antenna/reference-plane calibration, uncertainty evidence and
independent route holdouts. Neither published plots nor synthetic operators can
fill that evidence gap. Details and acquisition leads are in `calibration/README.md`.

Author order, contributions, funding, conflicts/patent interests, all-author
approval and data rights remain unconfirmed. A separate confirmation form is
provided in the local Revision 06 manuscript folder. No declarations, data reuse
permission or calibrated field results have been invented.

## Verification and release boundary

The implementation-only suite passed **213 tests**, with one Windows symlink
test skipped for host privilege restrictions; 85 subtests also passed. The full
workspace suite passed 256 tests and one skip, including 43 additional local
manuscript tests. These are software checks, not RF or railway performance.

The earlier Revision 05 PDF/LaTeX archive is unchanged and must not be described
as an updated Revision 06 submission. No submission or GitHub push is performed
while the requested scientific work and declarations remain incomplete. Local
implementation packaging, source-manifest checks and archive tests likewise do
not turn this revision into a clean-machine HFSS/ns-3 installation guarantee.
