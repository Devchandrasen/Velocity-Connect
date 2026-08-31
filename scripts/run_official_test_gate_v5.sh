#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly NS3_ROOT="${NS3_ROOT:-$(cd "$script_dir/.." && pwd)}"
readonly SUITES=(
    "ipv4-queue-disc-short-transport-header"
    "nr-lte-pattern-generation"
    "nr-phy-patterns"
    "nr-x2-handover-measures"
    "nr-x2-handover"
    "nr-handover-delay"
    "nr-handover-scenarios"
    "nr-ue-handover-interference"
)

cd "$NS3_ROOT"
echo "ns3_revision=$(git rev-parse HEAD)"
echo "nr_revision=$(git -C contrib/nr rev-parse HEAD)"
for suite in "${SUITES[@]}"; do
    echo "=== $suite ==="
    ./test.py -n -s "$suite" --jobs 4 --nocolor
done
