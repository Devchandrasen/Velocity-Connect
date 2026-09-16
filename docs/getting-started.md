# Getting started with Velocity Connect

This tutorial takes a clean checkout to two visible results: a verified CPU
test run and a local paired-measurement dashboard. Neither step requires Ansys
HFSS or ns-3.

## What you need

- Git
- 64-bit CPython 3.12
- PowerShell on Windows, or an equivalent shell on Linux
- approximately 2 GB of free disk space for the virtual environment

Use the pinned simulator workflow only after this local gate passes. Ansys
Electronics Desktop is optional and required only to rebuild HFSS projects.

## Step 1: Create the analysis environment

```powershell
git clone https://github.com/Devchandrasen/Velocity-Connect.git
Set-Location Velocity-Connect
py -3.12 -m venv .venv-reproduction
.\.venv-reproduction\Scripts\python.exe -m pip install -r environment\requirements-lock.txt
```

The lock file records the exact analysis packages used by the repository. The
separate hash-locked Windows file is used by the clean-machine release gate.

## Step 2: Run the local evidence gate

```powershell
.\.venv-reproduction\Scripts\python.exe scripts\verify_source_manifest.py
.\.venv-reproduction\Scripts\python.exe -m pytest -q
```

The first command checks the reviewed implementation files byte for byte. The
second checks campaign identities, link budgets, four-port algebra, statistics,
HFSS fixtures, calibration contracts, and prototype behavior.

A passing run proves that the software and retained fixtures are internally
consistent. It does not reproduce an HFSS solve or an ns-3 campaign.

## Step 3: Start the local measurement prototype

Run the collector in one terminal:

```powershell
.\.venv-reproduction\Scripts\python.exe -m prototype.velocity_connect.server
```

The process prints a local URL and the append-only evidence path. Keep this
terminal open.

In a second terminal, send a deterministic synthetic stream:

```powershell
.\.venv-reproduction\Scripts\python.exe prototype\demo_stream.py \
  --samples-per-condition 20
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The dashboard reports
paired baseline/passive summaries by segment and seat.

The demo identifies every sample as synthetic. Do not cite its values as
hardware, modem, or field evidence.

## Step 4: Inspect the data contract

The prototype stores newline-delimited JSON at
`out/prototype/samples.jsonl`. Its accepted schema and field limits are defined
in `prototype/velocity_connect/model.py`. The read-only endpoints are:

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | process health |
| `GET /api/v1/status` | sample counts, sources, runs, and latest timestamp |
| `GET /api/v1/report` | condition summaries and paired KPI differences |
| `POST /api/v1/samples` | validate and append one sample |

The server binds to localhost by default and has no production authentication.
Do not expose it to an untrusted network.

## What you built

You now have a verified analysis environment, a checked source snapshot, and a
working local evidence collector. Continue with:

- [How to run a guarded campaign](how-to-run-a-campaign.md) for ns-3/5G-LENA;
- [Experiment reference](experiment-reference.md) for model choices and outputs;
- [Evidence model](evidence-model.md) before interpreting results; and
- [HFSS README](../hfss/README.md) for electromagnetic regeneration.

## Troubleshooting

### `py -3.12` is not found

Install 64-bit CPython 3.12 and enable the Python launcher, or replace
`py -3.12` with the absolute path to a Python 3.12 executable.

### The source manifest fails

Run `git status --short` first. A deliberate change to a required source file
must be reviewed before regenerating the manifest:

```powershell
.\.venv-reproduction\Scripts\python.exe scripts\verify_source_manifest.py --write
```

Never regenerate the manifest to hide an unexplained difference.

### Port 8765 is in use

Choose another local port:

```powershell
.\.venv-reproduction\Scripts\python.exe -m prototype.velocity_connect.server --port 8877
```

Then pass `--url http://127.0.0.1:8877/api/v1/samples` to `demo_stream.py`.

[Back to the project overview](../README.md)
