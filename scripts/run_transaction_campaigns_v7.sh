#!/usr/bin/env bash
set -euo pipefail

# Boundary-controlled transaction campaign using only predeclared total
# passive-path losses. No antenna gain, service gain, or component loss is
# inferred from the preliminary HFSS donor coupon.
#
# Spatial contract:
#   six gNBs at x = 0..5*ISD, 10 m lateral offset;
#   UE starts at x = 0;
#   application measurement window x = 1.75*ISD..3.75*ISD;
#   simulator stops at x = 4*ISD;
#   3GPP channel spatial consistency updates every 5 ms.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-$(cd "$script_dir/.." && pwd)}"
OUT_PREFIX="${OUT_PREFIX:-out/transaction-v3}"
MAX_PARALLEL="${MAX_PARALLEL:-6}"
PYTHON="${PYTHON:-python3}"
CAMPAIGN_DRIVER="${CAMPAIGN_DRIVER:-$ROOT/velocity_connect_tools/research_campaign.py}"
PRIMARY_PASSIVE_LOSS_DB="${PRIMARY_PASSIVE_LOSS_DB:-6.5}"

cd "$ROOT"

campaign_complete() {
  local out_dir="$1"
  local expected="$2"
  "$PYTHON" - "$out_dir" "$expected" <<'PY'
import csv
import sys
from pathlib import Path

ledger = Path(sys.argv[1]) / "campaign_runs.csv"
expected = int(sys.argv[2])
if not ledger.exists():
    raise SystemExit(1)
with ledger.open(newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream))
ok = len(rows) == expected and all(row.get("status") == "ok" for row in rows)
raise SystemExit(0 if ok else 1)
PY
}

run_campaign() {
  local out_dir="$1"
  local expected="$2"
  shift 2

  if campaign_complete "$out_dir" "$expected"; then
    echo "[skip-complete] $out_dir ($expected successful runs)"
    return 0
  fi
  if [[ -d "$out_dir" ]] && [[ -n "$(find "$out_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "[refuse-partial] $out_dir already contains incomplete evidence" >&2
    return 3
  fi

  "$PYTHON" "$CAMPAIGN_DRIVER" \
    --ns3 ./ns3 \
    --program hsr_velocity_connect \
    --workdir . \
    --out "$out_dir" \
    --profile corridor \
    --numerology 1 \
    --nr-scenario UMi \
    --nr-condition LOS \
    --shadowing 1 \
    --passive-model declared_scalar \
    --declared-passive-loss-db "$PRIMARY_PASSIVE_LOSS_DB" \
    --num-gnbs 6 \
    --gnb-lateral-offset-m 10 \
    --guarded-corridor 1 \
    --channel-update-period-ms 5 \
    --enable-srs 0 \
    --enable-handover 1 \
    --use-ideal-rrc 0 \
    --handover-hysteresis-db 1.5 \
    --handover-ttt-ms 128 \
    --gnb-height-m 10 \
    --ue-height-m 1.5 \
    --app-pkt-size 1024 \
    --saturating-load 0 \
    --per-ue-offered-mbps 4 \
    --timeout 1800 \
    "$@"

  campaign_complete "$out_dir" "$expected"
}

active_pids=()
phase_failed=0

reap_one() {
  local completed_pid=""
  if ! wait -n -p completed_pid; then
    phase_failed=1
  fi
  local remaining=()
  local pid
  for pid in "${active_pids[@]}"; do
    if [[ "$pid" != "$completed_pid" ]]; then
      remaining+=("$pid")
    fi
  done
  active_pids=("${remaining[@]}")
}

run_limited() {
  while (( ${#active_pids[@]} >= MAX_PARALLEL )); do
    reap_one
  done
  run_campaign "$@" &
  active_pids+=("$!")
}

wait_all() {
  while (( ${#active_pids[@]} > 0 )); do
    reap_one
  done
  if (( phase_failed != 0 )); then
    echo "At least one transaction-v3 campaign failed." >&2
    return 1
  fi
  phase_failed=0
}

seeds_20="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20"
seeds_param="101,102,103,104,105,106,107,108"
seeds_tune="201,202,203,204,205,206,207,208,209,210"
seeds_load="301,302,303"

for direction in downlink uplink; do
  direction_offset=0
  [[ "$direction" == uplink ]] && direction_offset=1000
  run_limited \
    "${OUT_PREFIX}-principal-${direction}" 60 \
    --scenarios metal,composite,repeater \
    --speeds 500 \
    --distances 0 \
    --seeds "$seeds_20" \
    --num-ues 1 \
    --gnb-spacing-m 500 \
    --traffic-direction "$direction" \
    --run-base "$((171000 + direction_offset))"
done
wait_all

for direction in downlink uplink; do
  direction_offset=0
  [[ "$direction" == uplink ]] && direction_offset=1000
  for spacing in 300 500 800; do
    phase="param"
    [[ "$direction" == downlink ]] && phase="recovery-param"
    run_limited \
      "${OUT_PREFIX}-${phase}-${direction}-isd${spacing}" 48 \
      --scenarios composite,repeater \
      --speeds 300,400,500 \
      --distances 0 \
      --seeds "$seeds_param" \
      --num-ues 1 \
      --gnb-spacing-m "$spacing" \
      --traffic-direction "$direction" \
      --run-base "$((180000 + spacing + direction_offset))"
  done
done
wait_all

for target_loss in 6p5 12; do
  declared_loss=6.5
  loss_offset=0
  if [[ "$target_loss" == 12 ]]; then
    declared_loss=12
    loss_offset=1000
  fi
  for hysteresis in 0p5 1p5 3; do
    case "$hysteresis" in
      0p5) hysteresis_db=0.5; h_offset=100 ;;
      1p5) hysteresis_db=1.5; h_offset=200 ;;
      3) hysteresis_db=3.0; h_offset=300 ;;
    esac
    for ttt in 40 128 256; do
      run_limited \
        "${OUT_PREFIX}-tune-ul-l${target_loss}-h${hysteresis}-t${ttt}" 20 \
        --scenarios repeater \
        --speeds 300,500 \
        --distances 0 \
        --seeds "$seeds_tune" \
        --num-ues 1 \
        --gnb-spacing-m 500 \
        --traffic-direction uplink \
        --declared-passive-loss-db "$declared_loss" \
        --handover-hysteresis-db "$hysteresis_db" \
        --handover-ttt-ms "$ttt" \
        --run-base "$((190000 + loss_offset + h_offset + ttt))"
    done
  done
done
wait_all

for direction in downlink uplink; do
  direction_offset=0
  [[ "$direction" == uplink ]] && direction_offset=1000
  for scenario in composite repeater; do
    scenario_offset=0
    [[ "$scenario" == repeater ]] && scenario_offset=100
    run_limited \
      "${OUT_PREFIX}-load-${direction}-${scenario}" 12 \
      --scenarios "$scenario" \
      --speeds 500 \
      --distances 0 \
      --seeds "$seeds_load" \
      --num-ues-list 1,4,8,16 \
      --gnb-spacing-m 500 \
      --traffic-direction "$direction" \
      --per-ue-offered-mbps 1 \
      --run-base "$((200000 + direction_offset + scenario_offset))"
  done
done
wait_all

expected_campaigns=(
  "principal-downlink:60"
  "principal-uplink:60"
  "recovery-param-downlink-isd300:48"
  "recovery-param-downlink-isd500:48"
  "recovery-param-downlink-isd800:48"
  "param-uplink-isd300:48"
  "param-uplink-isd500:48"
  "param-uplink-isd800:48"
)
for loss in 6p5 12; do
  for hysteresis in 0p5 1p5 3; do
    for ttt in 40 128 256; do
      expected_campaigns+=("tune-ul-l${loss}-h${hysteresis}-t${ttt}:20")
    done
  done
done
for direction in downlink uplink; do
  for scenario in composite repeater; do
    expected_campaigns+=("load-${direction}-${scenario}:12")
  done
done

accepted_total=0
for contract in "${expected_campaigns[@]}"; do
  suffix="${contract%%:*}"
  expected="${contract##*:}"
  campaign_complete "${OUT_PREFIX}-${suffix}" "$expected"
  accepted_total=$((accepted_total + expected))
done
if (( ${#expected_campaigns[@]} != 30 || accepted_total != 816 )); then
  echo "Final transaction-v3 contract validation failed." >&2
  exit 4
fi

echo "All 30 transaction-v3 campaigns and 816 runs completed successfully."
