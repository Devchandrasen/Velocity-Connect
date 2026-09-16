#!/usr/bin/env bash
set -euo pipefail

readonly EXPECTED_NS3_REVISION="d2add90b452d600cfb4859baed8e9ea633519447"
readonly EXPECTED_NR_REVISION="47a3adc263f773556eaadac5a5341458dbc61c47"
readonly NS3_PATCH_REL="patches/ns-3.48-fqcodel-short-transport-header.patch"
readonly EXPECTED_NS3_PATCH_SHA256="027739864dcd1f60ab323197895b233cb211287ca5b416c71975679f8b4f8217"
readonly HANDOVER_SUITES=(
    "ipv4-queue-disc-short-transport-header"
    "nr-x2-handover-measures"
    "nr-x2-handover"
    "nr-handover-delay"
    "nr-handover-scenarios"
    "nr-ue-handover-interference"
)

usage() {
    cat <<'EOF'
Usage: sync_wsl_ns3_v5.sh [--check-only] [--no-build] [--run-tests] [NS3_ROOT [PROJECT_ROOT]]

Verify the official ns-3.48 / 5G-LENA v5.0 revisions, synchronize the
Velocity Connect sources, build hsr_velocity_connect, and optionally run the
official handover suites used by the publication evidence gate.

Defaults:
  NS3_ROOT     /home/codex/velocity-connect-ns3-v5
  PROJECT_ROOT parent directory of this script

The active CMake must be version 3.22 or newer. On the validated WSL setup:
  export PATH=/home/codex/.venvs/ns3-v5/bin:$PATH
EOF
}

check_only=0
build=1
run_tests=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --check-only)
            check_only=1
            shift
            ;;
        --no-build)
            build=0
            shift
            ;;
        --run-tests)
            run_tests=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            break
            ;;
    esac
done

if [[ "$EUID" -eq 0 ]]; then
    echo "Run this script as the non-root user that owns the ns-3 tree." >&2
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ns3_root="${1:-/home/codex/velocity-connect-ns3-v5}"
project_root="${2:-$(cd "$script_dir/.." && pwd)}"
nr_root="$ns3_root/contrib/nr"
scratch_dir="$ns3_root/scratch/velocity_connect"
tools_dir="$ns3_root/velocity_connect_tools"
ns3_patch="$project_root/$NS3_PATCH_REL"

for required in \
    "$ns3_root/ns3" \
    "$ns3_root/.git" \
    "$nr_root/.git" \
    "$ns3_patch" \
    "$project_root/hsr_velocity_connect.cc"; do
    if [[ ! -e "$required" ]]; then
        echo "Missing required path: $required" >&2
        exit 1
    fi
done

actual_ns3_revision="$(git -C "$ns3_root" rev-parse HEAD)"
actual_nr_revision="$(git -C "$nr_root" rev-parse HEAD)"
if [[ "$actual_ns3_revision" != "$EXPECTED_NS3_REVISION" ]]; then
    echo "Unsupported ns-3 revision: $actual_ns3_revision" >&2
    echo "Expected ns-3.48 revision: $EXPECTED_NS3_REVISION" >&2
    exit 1
fi
if [[ "$actual_nr_revision" != "$EXPECTED_NR_REVISION" ]]; then
    echo "Unsupported 5G-LENA revision: $actual_nr_revision" >&2
    echo "Expected v5.0 revision: $EXPECTED_NR_REVISION" >&2
    exit 1
fi
if [[ -n "$(git -C "$nr_root" status --porcelain --untracked-files=no)" ]]; then
    echo "The 5G-LENA tree has tracked changes; refusing to mix dependency edits." >&2
    git -C "$nr_root" status --short >&2
    exit 1
fi

actual_patch_sha256="$(sha256sum "$ns3_patch" | awk '{print $1}')"
if [[ "$actual_patch_sha256" != "$EXPECTED_NS3_PATCH_SHA256" ]]; then
    echo "Unexpected ns-3 robustness patch hash: $actual_patch_sha256" >&2
    echo "Expected: $EXPECTED_NS3_PATCH_SHA256" >&2
    exit 1
fi

patch_state="not_applied"
if [[ -n "$(git -C "$ns3_root" status --porcelain --untracked-files=no)" ]]; then
    if ! git -C "$ns3_root" apply --check --reverse "$ns3_patch"; then
        echo "The ns-3 tree has tracked changes beyond the declared robustness patch." >&2
        git -C "$ns3_root" status --short >&2
        exit 1
    fi
    normalize_diff() {
        sed -E -e '/^index /d' -e 's/^@@ .* @@.*$/@@/'
    }
    actual_declared_diff() {
        git -C "$ns3_root" diff --no-ext-diff
        (
            cd "$ns3_root"
            git diff --no-index -- /dev/null \
                src/internet/test/ipv4-queue-disc-item-test-suite.cc ||
                [[ "$?" -eq 1 ]]
        )
    }
    if ! diff -u \
        <(normalize_diff < "$ns3_patch") \
        <(actual_declared_diff | normalize_diff) >/dev/null; then
        echo "The applied ns-3 diff does not byte-semantically match the declared patch." >&2
        exit 1
    fi
    patch_state="applied"
elif ! git -C "$ns3_root" apply --check "$ns3_patch"; then
    echo "The declared ns-3 robustness patch does not apply cleanly." >&2
    exit 1
fi

echo "ns-3 revision: $actual_ns3_revision"
echo "5G-LENA revision: $actual_nr_revision"
echo "ns-3 robustness patch: $actual_patch_sha256 ($patch_state)"
if [[ "$check_only" -eq 1 ]]; then
    exit 0
fi

if [[ "$patch_state" == "not_applied" ]]; then
    git -C "$ns3_root" apply "$ns3_patch"
    echo "Applied declared ns-3 robustness patch."
fi

mkdir -p "$scratch_dir" "$tools_dir"
install -m 0644 \
    "$project_root/hsr_apps.h" \
    "$project_root/hsr_em_channel.h" \
    "$project_root/hsr_handover.h" \
    "$project_root/hsr_io.h" \
    "$project_root/hsr_nr.h" \
    "$project_root/hsr_runner.h" \
    "$project_root/hsr_stats.h" \
    "$project_root/hsr_types.h" \
    "$project_root/hsr_velocity_connect.cc" \
    "$scratch_dir/"
install -m 0644 \
    "$project_root/research_campaign.py" \
    "$project_root/run_corridor_campaign.py" \
    "$project_root/statistical_evidence.py" \
    "$tools_dir/"
install -m 0755 \
    "$project_root/scripts/run_transaction_campaigns_v7.sh" \
    "$project_root/scripts/run_publication_loss_sweep_v7.sh" \
    "$project_root/scripts/run_official_test_gate_v5.sh" \
    "$project_root/scripts/run_bad_length_regression_v1.sh" \
    "$tools_dir/"
echo "Synchronized simulator sources: $scratch_dir"
echo "Synchronized campaign tools: $tools_dir"

if [[ "$build" -eq 1 ]]; then
    "$ns3_root/ns3" -j "${JOBS:-4}" build hsr_velocity_connect
fi

if [[ "$run_tests" -eq 1 ]]; then
    "$ns3_root/ns3" -j "${JOBS:-4}" build nr-test test-runner
    for suite in "${HANDOVER_SUITES[@]}"; do
        "$ns3_root/test.py" -n -s "$suite" --jobs "${JOBS:-4}" --nocolor
    done
fi
