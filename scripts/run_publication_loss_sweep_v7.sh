#!/usr/bin/env bash
set -euo pipefail

# Guarded non-ideal-RRC sensitivity sweep over predeclared total passive loss.
# No HFSS gain or component-loss decomposition enters this experiment.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly NS3_ROOT="${NS3_ROOT:-$(cd "$script_dir/.." && pwd)}"
readonly TOOLS_DIR="$NS3_ROOT/velocity_connect_tools"
readonly PYTHON_BIN="${PYTHON_BIN:-python3}"
readonly OUTPUT_PREFIX="${1:-transaction-v3-loss-sweep}"
readonly SEEDS="31,32,33,34,35"
readonly LOSSES=(1.5 6.5 12 20 22.5 26)

cd "$NS3_ROOT"

campaign_complete() {
    local output="$1"
    "$PYTHON_BIN" - "$output" <<'PY'
import csv
import sys
from pathlib import Path

ledger = Path(sys.argv[1]) / "campaign_runs.csv"
if not ledger.is_file():
    raise SystemExit(1)
with ledger.open(newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream))
ok = len(rows) == 5 and all(row.get("status") == "ok" for row in rows)
raise SystemExit(0 if ok else 1)
PY
}

run_direction() {
    local direction="$1"
    local run_base="$2"
    local index=0
    for loss in "${LOSSES[@]}"; do
        local token="${loss//./p}"
        local output="out/${OUTPUT_PREFIX}-${direction}-loss${token}"
        if campaign_complete "$output"; then
            echo "[skip-complete] $output"
            index=$((index + 1))
            continue
        fi
        if [[ -d "$output" ]] && [[ -n "$(find "$output" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
            echo "Refusing partial campaign: $output" >&2
            return 2
        fi
        "$PYTHON_BIN" "$TOOLS_DIR/research_campaign.py" \
            --ns3 ./ns3 \
            --program hsr_velocity_connect \
            --workdir . \
            --out "$output" \
            --profile corridor \
            --numerology 1 \
            --nr-scenario UMi \
            --nr-condition LOS \
            --shadowing 1 \
            --passive-model declared_scalar \
            --declared-passive-loss-db "$loss" \
            --num-gnbs 6 \
            --gnb-lateral-offset-m 10 \
            --gnb-spacing-m 500 \
            --guarded-corridor 1 \
            --channel-update-period-ms 5 \
            --enable-srs 0 \
            --enable-handover 1 \
            --use-ideal-rrc 0 \
            --handover-hysteresis-db 1.5 \
            --handover-ttt-ms 128 \
            --gnb-height-m 10 \
            --ue-height-m 1.5 \
            --scenarios repeater \
            --speeds 500 \
            --distances 0 \
            --seeds "$SEEDS" \
            --num-ues 1 \
            --app-pkt-size 1024 \
            --saturating-load 0 \
            --per-ue-offered-mbps 4 \
            --traffic-direction "$direction" \
            --gnb-tx-power-dbm 40 \
            --ue-tx-power-dbm 23 \
            --run-base "$((run_base + index * 100))" \
            --timeout 1800 \
            --max-runs 5
        campaign_complete "$output"
        index=$((index + 1))
    done
}

run_direction downlink 220000 \
    >"out/${OUTPUT_PREFIX}-dl.stdout.log" \
    2>"out/${OUTPUT_PREFIX}-dl.stderr.log" &
dl_pid=$!
run_direction uplink 230000 \
    >"out/${OUTPUT_PREFIX}-ul.stdout.log" \
    2>"out/${OUTPUT_PREFIX}-ul.stderr.log" &
ul_pid=$!

status=0
if ! wait "$dl_pid"; then
    status=1
fi
if ! wait "$ul_pid"; then
    status=1
fi
if [[ "$status" -ne 0 ]]; then
    echo "One or more declared-loss campaigns failed." >&2
    exit "$status"
fi

campaign_count=0
run_count=0
for direction in downlink uplink; do
    for loss in "${LOSSES[@]}"; do
        token="${loss//./p}"
        campaign_complete "out/${OUTPUT_PREFIX}-${direction}-loss${token}"
        campaign_count=$((campaign_count + 1))
        run_count=$((run_count + 5))
    done
done
if [[ "$campaign_count" -ne 12 || "$run_count" -ne 60 ]]; then
    echo "Final loss-sweep contract validation failed." >&2
    exit 3
fi

echo "All 12 declared-loss campaigns and 60 runs completed successfully."
