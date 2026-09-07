# Revision06 operational execution contract

2026-09-07. **One authorized resource-only pilot completed; scientific campaigns
remain planned, not run.** Hold all further ns-3 execution until the parent releases
the host after its coordinated HFSS work.
This file does not supersede old plans, results, failure ledgers or the scientific
protocol in `vehcom_campaign_protocol.md`. No HFSS calls, C++/driver/manuscript
edits, app shutdowns, automations, background services or dependency installs.

## Parent handoff and immediate admission

The practical future sequence is principal (160), channel-sensitivity (160), then
separately resource-admitted load (360). Principal/sensitivity are complete focused
experiments, not result-selected fragments of an expanded analysis. The launcher
predeclares all 680 identities, preserves independent family analysis gates, and
reports 680 succeeded only when 680 ledger rows have actually succeeded. Even
then, a separate full raw-evidence analysis is required; launch counts and runner
success are not scientifically validated results.

Initial host admission was **NO-GO**, including for principal alone. The user
reported 1.10 GiB available of 15.42 GiB RAM, C: free 6.4 GiB and W: free 167.7 GiB.
A read-only OS snapshot here found 901120 KiB available host memory (~0.86 GiB).
WSL reported ~6.19 GiB MemAvailable and ~935 GiB virtual free disk. Registry inspection
confirmed Ubuntu and Docker WSL disks are backed on C:. WSL free space alone does
not establish either host RAM or VHD-growth headroom. No user workload was stopped.

Use a **new** `W:\Velocity-Connect-Revision06\campaign-20260907-v1` directory for
future outputs (`/mnt/w/Velocity-Connect-Revision06/campaign-20260907-v1` in WSL).
Nothing is moved/deleted. Preparation creates a new directory, distinct from the
authorized resource pilot. Ensure W: is mounted in WSL; an absent mount must not be
mistaken for a directory on the Linux root disk. The runtime lives beside the
future outputs; simulator and immutable C++ source remain at their original pin.
Keep checking C: separately for WSL swap/VHD and unrelated application growth.

## Verified pin and historical resource evidence

Read-only `--PrintHelp` inspection verified 62 options, all nine source hashes,
and the final versioned executable:

```text
/home/codex/buildprovenance/velocity-em-bridge-r05-portable-20260907
binary SHA256: a57f40ab95bf1a3b4edb69dc564e7b39f4a821710b751898529adb8885755d8d
pin SHA256: 2fa3af7a09ff56baeef5ae9bba61f82ca8b03f452cfce894431b522ea7ce8467
source bundle: 4ee0328e2897055f1d5be22c857847c25a16cf69f48b0648c6abcd18a6ec4c79
```

The existing `source/` already supplies the necessary immutable C++ snapshot.
Preparation additionally copies/hashes the launcher, original validation driver,
analyzer and both protocols under `runtime/`. Run that frozen copy thereafter;
workspace/HFSS edits cannot silently change the running campaign. The pin's shared
library hashes are checked too: this executable still depends on the ns3-v5 build
libraries. Do not rebuild or replace them during a campaign. Dynamic-loader
environment overrides are rejected. This is hash consistency, not a reproducible
rebuild or complete system-library/environment attestation.

The new launcher's real WSL read-only `inspect` additionally verified all **38
shared-library hashes**. Its snapshot at 2026-09-07T07:31:45Z saw 2853847040 bytes
available host RAM (~2.66 GiB), 6502567936 WSL-available bytes (~6.06 GiB),
180018208768 W: free bytes (~167.66 GiB), and 6779150336 C: free bytes (~6.31 GiB).
Only host memory failed the original 3-GiB principal/sensitivity admission. This is a point-in-time
snapshot, not a promise of available memory at launch; every row probes again.

Read-only inspection of accepted v3 outputs found the following on-disk totals
per run (all files in each result directory; **not peak RAM**):

| Prior profile | Inspected rows | Largest observed run directory |
| --- | ---: | ---: |
| Principal DL, 1 UE | 60 | 126473 bytes |
| Principal UL, 1 UE | 60 | 119648 bytes |
| Load DL composite, 16 UEs, old 1 Mbps/UE | 3 | 503779 bytes |
| Load DL scalar reference, 16 UEs, old 1 Mbps/UE | 3 | 504491 bytes |

These are old configurations, not revision06 trace-size bounds. Protocol timing
evidence is consecutive completion-mtime spacing, not per-process benchmarking:
principal DL/UL means 39.66/31.32 s; old 1 Mbps/UE 16-UE load mean 736.76 s. Constant
cost extrapolation gives principal + sensitivity ~3.16 h (RMa unmeasured), and all
families ~33.7 h. Crude packet-proportional load scaling instead gives ~31.6 days.
Neither is a reliable ETA or a measured upper/lower bound. No peak RSS/virtual
memory evidence was found in those logs. The subsequent capped resource pilot
below supplies new, deliberately limited evidence for a pre-freeze policy change.

## Completed authorized resource qualification

`W:\Velocity-Connect-Revision06\resource-pilot-01` completed exactly one principal
UMi LOS DL/direct-composite, six-gNB, one-UE, 4-Mbps row, with the unchanged
14.4-s simulation and [6.3,13.5) active window. Seed **960001**, run **96000001**
were checked against the scoped history and all proposed scientific identities.
Limits were 120 s wall timeout, RLIMIT_AS 512 MiB, host prestart >=1 GiB, and
own-process-group termination if sampled host availability fell below 512 MiB.

**GNU time -v: exit 0; peak RSS 77280 KiB (75.47 MiB); wall 71.65 s; user CPU
47.21 s; system 0.47 s; zero swaps.** Launcher elapsed was 71.96 s. Final prestart
host availability was 1350373376 bytes (~1.26 GiB), WSL 6715035648 bytes (~6.25
GiB). Six raw files total 126619 bytes. No performance comparisons/statistics
were produced; scientific campaign rows completed remains **zero**. Sampled
`/proc` values concern the time wrapper, not the simulator; use GNU time's child
RSS. No certified continuous host-free-memory minimum was recorded.

Result SHA256: `1969eea91ec44e7ce30294f53607996681ded700cba85aea8ef034c78aaff288`.
Pilot manifest SHA256: `ecb18738171f5c6575658b90f38ad0318e3509b423b4f42ffc11e736a5c83fa8`.
This is the file-byte hash. The separate embedded canonical content digest,
excluding the digest field itself, is
`2e9fe2d23dfe8dd3f0c6dce4fd8babe0dc0a61b8bca1f4bb7fa80af740bad2d7`;
the result's `manifest_sha256` references that value. Both were independently
verified unchanged; they are different hash constructions, not a mismatch.
Preparation binds that resource evidence and uses the pilot's recorded help,
rechecking binary, immutable C++ source and libraries by file reads only. It
does not launch even PrintHelp during coordinated HFSS work.

Before scientific preparation, principal/sensitivity admission changed to
**1.5 GiB available host and WSL memory with a 512 MiB child address-space cap**.
This reserves the entire cap plus a 1-GiB host margin. Full-family live memory
floor stays 1 GiB, stricter than the pilot's 512 MiB floor. The capped success
supports the tested row, not a worst-case guarantee for UL, scalar or RMa rows;
the OS cap/live guards bound future execution and failures remain terminal.
Load limits are unchanged. No scientific outcome drove this policy decision.

## Exact frozen science and operational budgets

There are exactly two baseline treatments: `direct_composite` and
`scalar_passive_legacy_reference` (`declared_scalar`, 6.5 dB). No candidate or
extra-argument override is exposed. Current EM complex coupling cannot enter this
moving campaign. All fixed controls, [6.3,13.5) s active window, 14.4 s simulation,
six-site geometry, 500 km/h motion, one active route-km/run, replication counts,
bootstrap and threshold contracts are inherited unchanged from the old driver.

| Family | Fixed experiment | Rows | Seed / run range (inclusive) |
| --- | --- | ---: | --- |
| Principal | UMi LOS, DL/UL, 1 UE, 4 Mbps/UE, 40 pairs/cell | 160 | 860001..860080 / 86000001..86000080 |
| Channel-sensitivity | UMi/RMa LOS, DL/UL, 1 UE, 4 Mbps/UE, 20 pairs/cell | 160 | 862001..862080 / 86002001..86002080 |
| Load | UMi LOS DL, 1/4/16 UEs x 4/20/50 Mbps/UE, 20 pairs/cell | 360 | 861001..861180 / 86001001..86001180 |

All treatments within a pair share identifiers; different pairs do not. Equal
identifiers do not prove common channel realizations. These proposed bases are
above the inspected v3 ranges (principal seeds 1..20, load 301..303, runs at most
200111 in inspected directories). `prepare` must collision-check **every**
`plan.json` and legacy `single_run.csv` under the supplied history roots, including
excluded/failed attempts. It rejects reuse of either a seed or a run. Provide
every other relevant history root/prior plan; no global uniqueness claim is made.
Legacy `campaign_config.json` Cartesian designs reserve all declared identities,
including unstarted/aborted rows. A malformed/empty legacy result is hash-retained
with its error and can use only its discovered ancestor configuration's **entire**
identity design as fallback; it is not skipped. Unknown malformed history without
that declared fallback fails closed. An independent replacement campaign requires
fresh explicit bases and a new directory, never a retry or deletion of old rows.

**Initial blocker, addressed by a narrower documented inspection scope:** scanning all historical `out/` correctly
refused `diagnostic-gdb-uplink-composite-n4-seed301/single_run.csv`, a header-only
result with no ancestor campaign configuration. The initial aborted recovery
campaign CSV was safely handled using its complete declared configuration, with
the malformed result/hash preserved; the standalone diagnostic lacks that fallback.
Do not silently ignore/delete it or claim that a broad historical audit passed.
Bounded read-only searches did not recover the exact diagnostic RNG command.
The task's implementation review selected explicit accepted/excluded legacy and all five R05 campaign
roots, plus readable standalone results: **155 roots, 3343 files, 7342 identity
entries** for the pilot. Nineteen malformed results retain declared-configuration
fallback. Five header-only diagnostics (gdb, gdb2, gdb3, patched, replay) remain
unverified; their paths, hashes and errors are preserved in the scope note.
Scientific preparation additionally includes the resource-pilot-01 root, whose
960001/96000001 identifiers are outside the 860001 scientific design. The manifest
records exact coverage and `global_uniqueness_verified: false`; no all-history
collision-check claim is made. None of the excluded diagnostics is deleted.

| Frozen operational policy | Principal / sensitivity (each) | Load |
| --- | ---: | ---: |
| Required available host RAM before each row | 1.5 GiB | 6 GiB |
| Required WSL MemAvailable before each row | 1.5 GiB | 6 GiB |
| Child address-space hard limit, not RSS prediction | 512 MiB | 4 GiB |
| Row timeout | 1800 s | 43200 s |
| Row aggregate storage reservation/guard | 16 MiB | 256 MiB |
| Complete family trace reservation | 2.5 GiB | 90 GiB |
| Sum of all row timeouts, not ETA | 80 h | 180 days |

Output admission requires **all pending rows of the selected focused family**
times its row reservation, plus a 5 GiB disk floor; backing-store free space must
independently remain >=5 GiB. Principal+channel reserves total 5 GiB traces and
the full suite 95 GiB, excluding the 5 GiB floor and small runtime/ledger overhead.
W: has reported capacity for these reservations; fresh resource admission remains mandatory.
Limits are intentionally conservative policy choices, not experimentally observed
requirements. Changing them after a start would require a separately reviewed
new campaign, not retuning around observed outcomes.

Each invocation defaults to **20 row starts and 7200 s wall budget**, one process
at a time. It starts no row unless its full frozen timeout plus 60 s overhead fits
the remaining invocation window. Finite maximum row starts and per-row timeouts
bound simulation work. Resource-probe latency, process teardown, hashing and OS
scheduling mean the total command wall time is not a real-time deadline guarantee.
Load needs an explicitly longer invocation window even to start one row.

During a child run, address-space/per-file-size/core-dump limits are OS-enforced.
Aggregate output size is sampled about every second; host/WSL memory and both disk
floors are sampled about every five seconds (a Windows probe can take up to 15 s).
Live memory floor is 1 GiB each. Sampled aggregate storage may overshoot between
checks and is not a filesystem quota; a single file cannot exceed its row cap.
The launcher is a foreground single-threaded process; it does not start monitors
or detached workers. Only its explicitly created simulator process group is killed
on timeout/interrupt/resource breach. No existing process is stopped.

Future row ledgers retain the exact admission snapshot, operational limits and
sampled `/proc` VmHWM/VmPeak memory observations. These sampled high-water marks
may miss final allocations and are not certified whole-run peaks. There is no
memory estimate manufactured from small trace sizes or the `--PrintHelp` process.

## Prepare, admit, run, stop, resume (future commands; not executed here)

From WSL, first confirm `/mnt/w` is an actual mounted W: volume. These commands
are manual, not an instruction to start now:

```bash
P=/mnt/c/Users/devel/OneDrive/Documents/Velocity-Connect
O=/mnt/w/Velocity-Connect-Revision06/campaign-20260907-v1
H=/home/codex/velocity-connect-ns3-v5/out
python3 -B "$P/scripts/run_vehcom_revision06.py" inspect --out "$O"
# prepare: repeat --history-root for each reviewed explicit root recorded in the
# resource-pilot manifest, also include resource-pilot-01, and use
# --history-scope-note to retain the five unverified diagnostics.
# Do not pass broad H alone: unresolved diagnostic CSVs intentionally fail closed.
R="$O/runtime/scripts/run_vehcom_revision06.py"
python3 -B "$R" admit --out "$O" --profiles principal channel-sensitivity
# ONLY after resources recover, admission passes, and operator approves execution:
python3 -B "$R" run --out "$O" --execute --profiles principal channel-sensitivity --max-rows 20 --wall-seconds 7200
python3 -B "$R" status --out "$O"
# Same run command resumes only unstarted rows, without retrying any terminal row.
```

After the HFSS post-audit is finished, history review is resolved, and a fresh
admission check passes, the complete principal family can instead be queued in
one foreground invocation (not a pilot or a smaller scientific design):

```bash
python3 -B "$R" run --out "$O" --execute --profiles principal --max-rows 160 --wall-seconds 289000
# Separately, after principal execution and a fresh operational admission:
python3 -B "$R" run --out "$O" --execute --profiles channel-sensitivity --max-rows 160 --wall-seconds 289000
```

The generous wall allowance accommodates 160 predeclared 1800-s row timeouts;
it is not an ETA. A failure does not condition whether the remaining fixed rows
are attempted; a resource/STOP gate can pause before completion, and the same
invocation parameters resume only pending rows. Never start these while another
coordinated HFSS post-audit/solve is using the host. An application merely being
closed or a single passing memory sample is not permission to bypass admission.

Create a file named `STOP` in the campaign root for a between-row safe stop.
The current row finishes (subject to its fixed timeout/live guard); no new row
starts. Keep the file until ready to resume, then rename it to retain the operator
record. Ctrl+C is an emergency in-flight interruption: current row is terminal
`interrupted`; it cannot be retried and that family's statistics stay unavailable.
A crash-left `running` row fails closed. After independently confirming **no orphan
from this campaign remains**, resume with both `--recover-interrupted` and
`--orphan-confirmed`; the row becomes `interrupted`, never relaunched. OS-held
root/family locks prevent cooperating concurrent launchers, including the original
driver using the same family directory. Uncooperative/manual launches are outside
that guarantee. Truncated ledgers or incomplete preparation are not auto-repaired.

Ordinary simulator nonzero exits, malformed outputs and timeouts remain in the
ledger and do **not** select an early stopping point: the fixed queue continues
until an operational gate/pause. No tuning, extra replication, survivor filtering
or result-dependent retry occurs. Resource/operator interruptions pause execution
and preserve the failed/unfinished evidence. No performance metrics are inspected
to decide whether to continue to the next family.

Use the frozen `runtime/scripts/analyze_vehcom_validation.py` separately, writing
a new analysis file for a complete focused family only. Unfinished or failed
families produce `statistics: null`; raw hashes and full metric/trace reconciliation
are required before scientific summaries exist. WSL analysis still needs NumPy
and SciPy, not installed or changed here. Never pool 320 successes into a claim of
680 completed. Neither this campaign nor passing tests proves railway calibration,
installed EM coupling, device feasibility or common-random-number channels.

## Verification boundary

`tests/test_vehcom_revision06.py` uses a non-executable fixture pin and tiny fake
CSVs. Tests cover frozen counts/identities, old-identity collisions, no-launch
preparation, fresh resource admission, bounded starts, STOP/time gates, serial
resume, retained failures/timeouts, explicit crash recovery, drift, locks, and
no partial statistics. Synthetic fixture successes are launcher tests only.
Run the new and existing validation suites with:

```powershell
python -B -m pytest -p no:cacheprovider tests/test_vehcom_revision06.py tests/test_vehcom_validation.py -q
```

Final local verification: **99 passed in 28.68 s** (new revision06 plus existing
validation tests). This includes mocked child cleanup/OS-limit dispatch tests;
The one authorized resource pilot exercised real Linux limits and the pinned ns-3
binary; it did not execute a scientific campaign. Read-only WSL inspection verified
binary/source/library consistency and resource probes. No heavy load, full campaign,
HFSS call, or performance analysis was performed. Existing non-owned files remain
untouched, including parallel parent changes.
