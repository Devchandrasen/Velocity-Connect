# Reproducing the Velocity Connect implementation

This repository contains implementation source and compact validation fixtures.
It intentionally excludes manuscript sources, generated figures, solver result
trees, bulk campaign outputs, patent material, and hardware handoff documents.

## 1. CPU-only validation

The fast validation path checks the campaign matrix, passive link-budget model,
polarization-twisted four-port mapping, frozen Touchstone fixtures, statistics,
prototype evidence store, and corridor checkpoint logic. It does not require
ns-3, 5G-LENA, or Ansys HFSS.

```powershell
git clone https://github.com/Devchandrasen/Velocity-Connect.git
Set-Location Velocity-Connect
py -3.12 -m venv .venv-reproduction
.\.venv-reproduction\Scripts\python.exe -m pip install --upgrade pip
.\.venv-reproduction\Scripts\python.exe -m pip install -r environment\requirements-lock.txt
.\.venv-reproduction\Scripts\python.exe scripts\verify_source_manifest.py
.\.venv-reproduction\Scripts\python.exe -m pytest -q
```

The source-manifest check is byte-sensitive. A changed implementation file must
be reviewed and the manifest deliberately regenerated with:

```powershell
.\.venv-reproduction\Scripts\python.exe scripts\verify_source_manifest.py --write
```

## 2. Pinned ns-3.48 and 5G-LENA v5.0 build

Run this part on Ubuntu 22.04, either directly or under WSL2. The bootstrap
script clones exact revisions, applies the declared ns-3 robustness patch,
synchronizes the Velocity Connect source, and builds the simulator.

```bash
git clone https://github.com/Devchandrasen/Velocity-Connect.git
cd Velocity-Connect
bash scripts/bootstrap_ns3_v5.sh "$HOME/ns-3.48-velocity-connect" "$PWD"
bash scripts/sync_wsl_ns3_v5.sh --check-only \
  "$HOME/ns-3.48-velocity-connect" "$PWD"
```

Run the official upstream handover and regression gates before a full campaign:

```bash
bash scripts/sync_wsl_ns3_v5.sh --run-tests \
  "$HOME/ns-3.48-velocity-connect" "$PWD"
```

Run the guarded network campaign from the pinned simulator checkout:

```bash
cd "$HOME/ns-3.48-velocity-connect"
bash velocity_connect_tools/run_transaction_campaigns_v7.sh
bash velocity_connect_tools/run_publication_loss_sweep_v7.sh
bash velocity_connect_tools/run_official_test_gate_v5.sh
```

Every run writes an explicit configuration and attempt ledger. Failed or
interrupted runs remain visible and are not promoted into summaries.

## 3. HFSS implementation

The `hfss` directory contains parameterized PyAEDT builders and native AEDT
scripts. Five small native projects are retained as inspectable implementation
artifacts:

- the selected dual-port n78 screening antenna;
- the installed-radome screening model;
- the dual-slant PTF radiator screening model;
- the balanced PTF-V4 four-port control; and
- the PTF-V5 physical-delay four-port.

Create the optional HFSS environment on Windows:

```powershell
py -3.12 -m venv .venv-hfss
.\.venv-hfss\Scripts\python.exe -m pip install -r hfss\requirements-hfss.txt
```

The native scripts resolve their output paths from their own location. They no
longer depend on the original developer's home directory. Ansys licensing and
solver execution remain external requirements.

The compact solved exports in `fixtures/hfss` are used by the CPU-only tests.
They provide exact four-port matrices for code validation without claiming a
fabricated or measured product.

## Evidence boundary

A passing unit test, source-manifest check, or simulator build demonstrates
software reproducibility only. The repository does not claim VNA, OTA,
installed-coach, route, or moving-train validation. HFSS gain and efficiency
claims remain excluded wherever strict radiated-power closure is not satisfied.
