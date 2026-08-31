#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ROOT="${ROOT:-$(cd "$script_dir/.." && pwd)}"
readonly OUT_DIR="${1:-$ROOT/out/regression-bad-ipv4-length-20260731-v3}"

if [[ -e "$OUT_DIR" ]]; then
    echo "Refusing to overwrite existing regression output: $OUT_DIR" >&2
    exit 3
fi
mkdir -p "$OUT_DIR"

run_args=(
    "hsr_velocity_connect"
    "--singleRun=1"
    "--scenario=composite"
    "--speed=500"
    "--distance=0"
    "--gnbHeightM=10"
    "--gnbLateralOffsetM=10"
    "--ueHeightM=1.5"
    "--numUes=4"
    "--seed=301"
    "--run=201003"
    "--simTime=25"
    "--appStart=1"
    "--appStop=0"
    "--channelUpdatePeriodMs=5"
    "--enableSrs=0"
    "--appPktSize=1024"
    "--saturatingLoad=0"
    "--perUeOfferedMbps=1"
    "--saturatingIntervalUs=100"
    "--trafficDirection=uplink"
    "--nrScenario=UMi"
    "--nrCondition=LOS"
    "--shadowing=1"
    "--numerology=1"
    "--paperProfile=0"
    "--passiveModel=declared_scalar"
    "--numGnbs=6"
    "--gnbSpacingM=500"
    "--guardedCorridor=1"
    "--enableHandover=1"
    "--handoverHysteresisDb=1.5"
    "--handoverTimeToTriggerMs=128"
    "--useIdealRrc=0"
    "--legacyRepeaterLossDb=5"
    "--declaredPassiveLossDb=6.5"
    "--donorGainDbi=8"
    "--serviceGainDbi=2"
    "--feederCableLossDb=3"
    "--indoorDistribLossDb=4"
    "--couplingLossDb=8"
    "--gnbTxPowerDbm=40"
    "--ueTxPowerDbm=23"
    "--outDir=$OUT_DIR"
)

printf '%q ' "$ROOT/ns3" run "${run_args[*]}" > "$OUT_DIR/command.txt"
printf '\n' >> "$OUT_DIR/command.txt"

set +e
(
    cd "$ROOT"
    "$ROOT/ns3" run "${run_args[*]}"
) > "$OUT_DIR/stdout.log" 2> "$OUT_DIR/stderr.log"
return_code=$?
set -e
printf '%s\n' "$return_code" > "$OUT_DIR/exit_code.txt"
if [[ "$return_code" -ne 0 ]]; then
    echo "Exact bad-length regression replay failed with exit code $return_code." >&2
    exit "$return_code"
fi

python3 - "$OUT_DIR" <<'PY'
import csv
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
required = {
    "single_run.csv",
    "ue_metrics.csv",
    "packet_receptions.csv",
    "handover_events.csv",
    "rsrp_measurements.csv",
    "ue_serving_cells.csv",
    "command.txt",
    "stdout.log",
    "stderr.log",
    "exit_code.txt",
}
missing = sorted(name for name in required if not (out_dir / name).is_file())
if missing:
    raise SystemExit(f"Regression output is incomplete: {missing}")

with (out_dir / "single_run.csv").open(newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream))
if len(rows) != 1:
    raise SystemExit(f"Expected one terminal row, found {len(rows)}")
row = rows[0]
expected = {
    "scenario": "composite",
    "traffic_direction": "uplink",
    "num_ues": "4",
    "seed": "301",
    "run": "201003",
}
for key, value in expected.items():
    if row.get(key) != value:
        raise SystemExit(f"Unexpected {key}: {row.get(key)!r}; expected {value!r}")

bad_length_drops = int(row["bad_ipv4_length_drops"])
short_hash_events = int(row["short_transport_header_hash_events"])
if bad_length_drops < 0:
    raise SystemExit(
        f"Invalid incoming IPv4 bad-length drop count: {bad_length_drops}"
    )
if short_hash_events < 0:
    raise SystemExit(
        f"Invalid short-header hash-event count: {short_hash_events}"
    )

result = {
    "status": "PASS",
    "seed": 301,
    "run": 201003,
    "bad_ipv4_length_drops": bad_length_drops,
    "short_transport_header_hash_events": short_hash_events,
    "single_run_csv": str(out_dir / "single_run.csv"),
}
(out_dir / "regression_result.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(result, sort_keys=True))
PY
