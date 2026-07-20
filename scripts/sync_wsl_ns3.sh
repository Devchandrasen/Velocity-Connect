#!/usr/bin/env bash
set -euo pipefail

readonly EXPECTED_NR_REVISION="f29ebd33450c49af934ea5dde8606f855c22c2a6"
readonly EXPECTED_PATCHED_SOURCE_SHA256="83052d7876cceb8fee876f7abf8820e67164faa432c23aa822a488b251c1a6f9"
readonly UPSTREAM_BEAM_FIX_REVISION="81892efac84f2aef0a962b9da176ea7d7b6912b0"
readonly UPSTREAM_BUDGET_FIX_REVISION="a1aa32c757e0f834a4e40654853ce56dee13eca3"

usage() {
    cat <<'EOF'
Usage: sync_wsl_ns3.sh [--check-only] [--no-build] [NS3_ROOT [PROJECT_ROOT]]

Patch the validated ns-3.46 / 5G-LENA v4.1.1 dependency, synchronize the
Velocity Connect C++ sources into scratch/velocity_connect, and build the
hsr_velocity_connect target.

Defaults:
  NS3_ROOT     /home/codex/velocity-connect-ns3
  PROJECT_ROOT parent directory of this script
EOF
}

check_only=0
build=1
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
    echo "The ns-3 wrapper refuses to configure or build as root." >&2
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ns3_root="${1:-/home/codex/velocity-connect-ns3}"
project_root="${2:-$(cd "$script_dir/.." && pwd)}"
nr_root="$ns3_root/contrib/nr"
patch_file="$project_root/patches/5g-lena-v4.1.1-harq-symbol-budget.patch"
beam_patch_file="$project_root/patches/5g-lena-v4.1.1-harq-beam-order.patch"
scratch_dir="$ns3_root/scratch/velocity_connect"
patch_files=("$beam_patch_file" "$patch_file")
patched_source="$nr_root/model/nr-mac-scheduler-harq-rr.cc"

for required in \
    "$ns3_root/ns3" \
    "$nr_root/.git" \
    "${patch_files[@]}" \
    "$project_root/hsr_velocity_connect.cc"; do
    if [[ ! -e "$required" ]]; then
        echo "Missing required path: $required" >&2
        exit 1
    fi
done

git_nr=(git -c "safe.directory=$nr_root" -C "$nr_root")
actual_revision="$("${git_nr[@]}" rev-parse HEAD)"

if [[ "$actual_revision" != "$EXPECTED_NR_REVISION" ]]; then
    echo "Unsupported 5G-LENA revision: $actual_revision" >&2
    echo "Expected clean v4.1.1 revision: $EXPECTED_NR_REVISION" >&2
    echo "Upstream beam fix: $UPSTREAM_BEAM_FIX_REVISION" >&2
    echo "Upstream symbol-budget fix: $UPSTREAM_BUDGET_FIX_REVISION" >&2
    exit 1
fi

changed_files="$("${git_nr[@]}" status --porcelain --untracked-files=no | awk '{print $2}')"
if [[ -n "$changed_files" && "$changed_files" != "model/nr-mac-scheduler-harq-rr.cc" ]]; then
    echo "5G-LENA has unrelated tracked changes; refusing to mix dependency patches." >&2
    "${git_nr[@]}" status --short >&2
    exit 1
fi

patch_statuses=()
for current_patch in "${patch_files[@]}"; do
    if "${git_nr[@]}" apply --reverse --check "$current_patch" >/dev/null 2>&1; then
        patch_statuses+=("already-applied")
    elif "${git_nr[@]}" apply --check "$current_patch"; then
        patch_statuses+=("ready")
    else
        echo "Patch does not apply cleanly: $current_patch" >&2
        exit 1
    fi
done

if [[ "$check_only" -eq 1 ]]; then
    echo "5G-LENA revision: $actual_revision"
    for index in "${!patch_files[@]}"; do
        echo "$(basename "${patch_files[$index]}"): ${patch_statuses[$index]}"
    done
    if [[ ! " ${patch_statuses[*]} " =~ " ready " ]]; then
        actual_source_sha256="$(sha256sum "$patched_source" | awk '{print $1}')"
        if [[ "$actual_source_sha256" != "$EXPECTED_PATCHED_SOURCE_SHA256" ]]; then
            echo "Patched scheduler hash mismatch: $actual_source_sha256" >&2
            exit 1
        fi
    fi
    exit 0
fi

for index in "${!patch_files[@]}"; do
    if [[ "${patch_statuses[$index]}" == "ready" ]]; then
        "${git_nr[@]}" apply "${patch_files[$index]}"
        patch_statuses[$index]="applied"
    fi
done

actual_source_sha256="$(sha256sum "$patched_source" | awk '{print $1}')"
if [[ "$actual_source_sha256" != "$EXPECTED_PATCHED_SOURCE_SHA256" ]]; then
    echo "Patched scheduler hash mismatch: $actual_source_sha256" >&2
    exit 1
fi

mkdir -p "$scratch_dir"
install -m 0644 \
    "$project_root/hsr_apps.h" \
    "$project_root/hsr_io.h" \
    "$project_root/hsr_nr.h" \
    "$project_root/hsr_runner.h" \
    "$project_root/hsr_stats.h" \
    "$project_root/hsr_types.h" \
    "$project_root/hsr_velocity_connect.cc" \
    "$scratch_dir/"

echo "5G-LENA revision: $actual_revision"
for index in "${!patch_files[@]}"; do
    echo "$(basename "${patch_files[$index]}"): ${patch_statuses[$index]}"
done
echo "Synchronized sources: $scratch_dir"

if [[ "$build" -eq 1 ]]; then
    "$ns3_root/ns3" build hsr_velocity_connect -j "${JOBS:-2}"
fi
