#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# Run scripts/brltty-probe.sh in each target's container and keep the answer
# under reference/probes/brltty-<target>.txt, which gen_brltty_inventory.py
# renders into docs/reference/brltty-inventory.md.
#
#   scripts/run-brltty-probe.sh                # all seven targets
#   scripts/run-brltty-probe.sh ubuntu-24.04   # one
#
# Rootless podman, never docker (CLAUDE.md). An account with no subuid ranges
# sets HAMMUNITION_DEGRADED_PODMAN=1, same as the harness. PODMAN_AUTHFILE
# names an auth file to use for pulls: podman falls back to ~/.docker/config.json,
# and a stale Docker Hub login there fails every anonymous pull with
# "unauthorized"; an empty file ({}) is the fix without touching that login.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$REPO_ROOT/reference/probes"
mkdir -p "$OUT_DIR"

# Fully qualified: a short name resolves only through registries.conf aliases,
# and the vendor images have none.
declare -A IMAGES=(
    [debian-13]="docker.io/library/debian:13"
    [debian-13-arm64]="docker.io/library/debian:13"
    [ubuntu-26.04]="docker.io/library/ubuntu:26.04"
    [ubuntu-24.04]="docker.io/library/ubuntu:24.04"
    [kali-rolling]="docker.io/kalilinux/kali-rolling:latest"
    [parrot]="docker.io/parrotsec/core:latest"
    [linuxmint-22.3]="docker.io/linuxmintd/mint22.3-amd64:latest"
)
# The arm64 row asks Debian's archive for the arm64 package from an amd64
# container -- the rules file is architecture-independent content, and the
# archive index is what is being measured, not emulation.
declare -A FOREIGN_ARCH=([debian-13-arm64]="arm64")
ALL=(debian-13 debian-13-arm64 ubuntu-26.04 ubuntu-24.04 kali-rolling parrot linuxmint-22.3)

command -v podman >/dev/null || { echo "podman is required (never docker -- see CLAUDE.md)" >&2; exit 1; }
RUN_OPTS=(--rm --platform linux/amd64)
if [ "${HAMMUNITION_DEGRADED_PODMAN:-}" = "1" ]; then
    echo "WARNING: HAMMUNITION_DEGRADED_PODMAN=1 -- container isolation is weakened." >&2
    echo "         The real fix is one root command:" >&2
    echo "           sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 \$USER" >&2
    echo "           podman system migrate" >&2
    RUN_OPTS+=(--storage-opt ignore_chown_errors=true)
fi
if [ -n "${PODMAN_AUTHFILE:-}" ]; then
    RUN_OPTS+=(--authfile "$PODMAN_AUTHFILE")
fi

for target in "${@:-${ALL[@]}}"; do
    image="${IMAGES[$target]:-}"
    [ -n "$image" ] || { echo "unknown target: $target" >&2; exit 1; }
    echo "==> $target ($image)"
    out="$OUT_DIR/brltty-$target.txt"
    podman run "${RUN_OPTS[@]}" \
        -v "$REPO_ROOT/scripts/brltty-probe.sh":/probe.sh:ro \
        "$image" bash /probe.sh "${FOREIGN_ARCH[$target]:-}" > "$out"
    # Verify the effect, not the exit status (D-031): the file must carry the
    # sections the generator reads.
    grep -q '^### candidate' "$out" && grep -q '^### udev-rules-shipped\|^NO DEB' "$out" \
        || { echo "    probe produced no usable answer for $target -- see $out" >&2; exit 1; }
    echo "    $(grep -c '^### FILE' "$out") rules file(s) -> reference/probes/brltty-$target.txt"
done
