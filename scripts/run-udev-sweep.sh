#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# Run scripts/udev-sweep.sh inside each target container and save the TSV.
#
#   scripts/run-udev-sweep.sh [target ...]     default: debian-13
#
# Output goes to reference/probes/udev-<target>.tsv, which is gitignored --
# probe output is measurement, not source. scripts/gen_udev_inventory.py turns
# it into the committed document.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$REPO_ROOT/reference/probes"
mkdir -p "$OUT_DIR"

declare -A IMAGES=(
    [debian-13]="debian:13"
    [kali-rolling]="kalilinux/kali-rolling:latest"
    [parrot]="parrotsec/core:latest"
    [ubuntu-26.04]="ubuntu:26.04"
)

command -v podman >/dev/null || { echo "podman is required (never docker -- see CLAUDE.md)" >&2; exit 1; }

STORAGE_OPTS=()
if [ "${HAMMUNITION_DEGRADED_PODMAN:-}" = "1" ]; then
    echo "WARNING: HAMMUNITION_DEGRADED_PODMAN=1 -- container isolation is weakened." >&2
    echo "         The real fix is one root command:" >&2
    echo "           sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 \$USER" >&2
    echo "           podman system migrate" >&2
    STORAGE_OPTS=(--storage-opt ignore_chown_errors=true)
fi

for target in "${@:-debian-13}"; do
    image="${IMAGES[$target]:-}"
    [ -n "$image" ] || { echo "unknown target: $target" >&2; exit 1; }
    echo "==> $target ($image)"
    podman run --rm "${STORAGE_OPTS[@]}" \
        -v "$REPO_ROOT/scripts/udev-sweep.sh":/sweep.sh:ro \
        "$image" bash /sweep.sh > "$OUT_DIR/udev-$target.tsv"
    echo "    $(wc -l < "$OUT_DIR/udev-$target.tsv") identifiers -> reference/probes/udev-$target.tsv"
done
