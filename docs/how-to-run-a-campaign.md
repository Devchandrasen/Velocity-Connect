# How to run a guarded network campaign

This guide builds the pinned ns-3/5G-LENA environment, runs the required
regression gate, executes the transaction-v3 campaign, and verifies its
terminal ledger.

## Prerequisites

- Ubuntu 22.04, directly or through WSL2
- Git, CMake 3.22 or newer, Ninja, and g++ 11.4 or newer
- enough storage for an ns-3 build and isolated campaign outputs
- a clean Velocity Connect checkout

The pinned revisions are:

- ns-3.48: `d2add90b452d600cfb4859baed8e9ea633519447`
- 5G-LENA v5.0: `47a3adc263f773556eaadac5a5341458dbc61c47`

## Step 1: Pass the CPU gate

From the Velocity Connect checkout:

```bash
python3 scripts/verify_source_manifest.py
python3 -m pytest -q
```

Resolve any source drift or test failure before spending simulator time.

## Step 2: Bootstrap the pinned simulator

Choose a new destination. Do not point the command at an unrelated ns-3 tree.

```bash
bash scripts/bootstrap_ns3_v5.sh \
  "$HOME/ns-3.48-velocity-connect" "$PWD"
```

The bootstrap clones exact revisions, applies the declared ns-3 patch,
synchronizes project source, and builds the target.

## Step 3: Verify synchronization and upstream behavior

```bash
bash scripts/sync_wsl_ns3_v5.sh --check-only \
  "$HOME/ns-3.48-velocity-connect" "$PWD"

bash scripts/sync_wsl_ns3_v5.sh --run-tests \
  "$HOME/ns-3.48-velocity-connect" "$PWD"
```

The test gate covers the local short-transport-header regression and pinned
5G-LENA handover, X2, measurement, delay, and interference suites. A failed
upstream test blocks the campaign.

## Step 4: Inspect a bounded dry run

Use the generic controller to see exact commands without invoking ns-3:

```bash
python3 research_campaign.py \
  --ns3 "$HOME/ns-3.48-velocity-connect/ns3" \
  --workdir "$HOME/ns-3.48-velocity-connect" \
  --profile corridor \
  --scenarios repeater \
  --speeds 500 \
  --distances 500 \
  --seeds 1,2,3 \
  --num-ues 1 \
  --max-runs 3 \
  --dry-run
```

Check the scenario, speed, distance, UE count, traffic direction, passive model,
and output location before execution.

## Step 5: Run the frozen transaction contract

```bash
cd "$HOME/ns-3.48-velocity-connect"
bash velocity_connect_tools/run_transaction_campaigns_v7.sh
```

The controller requires a clean output destination. The accepted terminal
contract contains 30 campaign ledgers and 816 successful rows. Interrupted or
failed earlier attempts stay separate and are not merged into the accepted
set.

## Step 6: Verify the terminal campaign

The script verifies factor multisets, unique seed/run pairs, status values, and
row counts before printing success. Preserve:

- every `campaign_config.json`;
- every `campaign_runs.csv`;
- raw per-run output directories;
- terminal logs; and
- dependency/source provenance records.

Do not infer success from plots or a subset of completed rows.

## Step 7: Run loss sensitivity and official regression

Only after the main campaign is terminal:

```bash
bash velocity_connect_tools/run_publication_loss_sweep_v7.sh
bash velocity_connect_tools/run_official_test_gate_v5.sh
```

The loss sweep evaluates 1.5, 6.5, 12, 20, 22.5, and 26 dB independently in
both directions. It does not convert any assumed loss into a measured device
property.

## Verification checklist

- The simulator and 5G-LENA commits match the pinned hashes.
- The synchronized source tree is clean.
- The official regression suites pass.
- Every expected run identity appears exactly once.
- Every accepted scientific row has terminal status `ok`.
- Failed and interrupted runs remain in separate provenance records.
- Analysis uses only the declared complete ledger.

## Troubleshooting

### The destination contains an old partial campaign

Use a new output directory. Do not delete failure history or merge old and new
rows by hand.

### The source manifest changed after a code edit

Review the diff, run the affected tests, and regenerate the manifest only after
the change is accepted:

```bash
python3 scripts/verify_source_manifest.py --write
```

### A run was interrupted

Keep its terminal record. The guarded driver does not retry the same scientific
identity. Follow the explicit recovery rules in
[vehcom campaign protocol](../reproducibility/vehcom_campaign_protocol.md).

### Resources are insufficient

Stop before launching more rows. Resource admission is operational protection,
not a statistical stopping rule. Never present a resource pilot as a scientific
result.

## Related

- [Experiment protocol](../EXPERIMENT_PROTOCOL.md)
- [Full reproducibility contract](../REPRODUCIBILITY.md)
- [Experiment reference](experiment-reference.md)
- [Evidence ledger](../RESULTS.md)

[Back to the project overview](../README.md)
