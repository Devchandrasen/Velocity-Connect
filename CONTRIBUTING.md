# Contributing to Velocity Connect

Velocity Connect accepts changes that improve the implementation while keeping
its evidence history and claim boundaries intact.

## Before you start

1. Read [Architecture](docs/architecture.md) and
   [Evidence model](docs/evidence-model.md).
2. Open an issue for changes to experiment design, dependency pins, campaign
   identities, HFSS acceptance criteria, or measurement schemas.
3. Keep generated simulator outputs, solver trees, manuscript files, and local
   virtual environments out of the repository.

## Development setup

```powershell
py -3.12 -m venv .venv-reproduction
.\.venv-reproduction\Scripts\python.exe -m pip install -r environment\requirements-lock.txt
.\.venv-reproduction\Scripts\python.exe scripts\verify_source_manifest.py
.\.venv-reproduction\Scripts\python.exe -m pytest -q
```

Use a focused branch. Keep unrelated local files and experiment outputs out of
the commit.

## Change rules

### Implementation

- Add or update tests for changed behavior.
- Reject invalid scientific inputs explicitly. Do not clamp, fill, or silently
  repair them.
- Preserve append-only ledgers and terminal failures.
- Do not change frozen seeds, run identifiers, thresholds, or dependency pins
  without documenting the reason and impact.

### HFSS and RF data

- Keep raw solver values and units.
- Do not report efficiency above 100 percent as an accepted result.
- Record solver version, boundary type, mesh controls, excitation context, and
  output hashes.
- Keep compact fixtures only. Bulk result trees belong outside Git.

### Documentation

- Separate software, simulation, measurement, and field evidence.
- Use commands that can be copied from a clean checkout.
- Link every new guide from `README.md` within two clicks.
- Do not add manuscript claims that are absent from `RESULTS.md`.

## Source manifest

The manifest is deliberately byte-sensitive. After reviewing a required-file
change, regenerate it with:

```powershell
.\.venv-reproduction\Scripts\python.exe scripts\verify_source_manifest.py --write
```

Then run the check again. A manifest update without a reviewed source diff is
not acceptable.

## Pull-request checklist

- [ ] The change has a narrow purpose.
- [ ] New behavior has tests.
- [ ] `scripts/verify_source_manifest.py` passes.
- [ ] `pytest -q` passes.
- [ ] New local Markdown links resolve.
- [ ] No generated bulk data, credentials, or machine-specific paths are added.
- [ ] Claims match the evidence layer that was actually tested.
- [ ] Failures and limitations remain visible.

## Reporting a reproducibility problem

Use the reproducibility issue template. Include the Git commit, operating
system, Python version, ns-3 and 5G-LENA commits when applicable, exact command,
terminal output, and whether the failure occurred before or during simulation.

Do not attach licences, private datasets, access tokens, or proprietary solver
files that you are not authorized to share.
