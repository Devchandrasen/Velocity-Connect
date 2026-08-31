#!/usr/bin/env bash
set -euo pipefail

destination="${1:-$PWD/ns-3.48-velocity-connect}"
project_root="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ns3_revision="d2add90b452d600cfb4859baed8e9ea633519447"
nr_revision="47a3adc263f773556eaadac5a5341458dbc61c47"

if [[ -e "$destination" ]]; then
  echo "Refusing to overwrite existing destination: $destination" >&2
  exit 2
fi

git clone https://gitlab.com/nsnam/ns-3-dev.git "$destination"
git -C "$destination" checkout --detach "$ns3_revision"
git clone https://gitlab.com/cttc-lena/nr.git "$destination/contrib/nr"
git -C "$destination/contrib/nr" checkout --detach "$nr_revision"

bash "$project_root/scripts/sync_wsl_ns3_v5.sh" \
  "$destination" \
  "$project_root"

echo "Pinned simulator ready at: $destination"
