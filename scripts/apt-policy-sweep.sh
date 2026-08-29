#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# Ask one target's archive what it offers, for a list of package names.
#
# This answers the question every apt manifest rests on -- "is this package in
# this distribution, and at what version" -- for every target at once, so a
# manifest's `install` selector is written from measurement rather than from a
# memory of what Debian used to ship. `apt-cache policy` is the weaker of the
# two checks this repository runs: it proves the archive OFFERS a package, not
# that it installs. scripts/install-probe.sh is the stronger one, and costs a
# container per package. Use this to decide WHICH packages are worth the
# stronger check, and cite the stronger one for any claim that a thing works.
#
# **Architecture is asked, not emulated.** `HAMMUNITION_FOREIGN_ARCH=arm64`
# runs the native image and queries `pkg:arm64` after `dpkg --add-architecture`,
# because what an `arch` selector actually asks is "does this archive carry this
# package for that architecture" -- a fact about the archive's index, not about
# a running kernel. Emulation answers the same question and needs
# qemu-user-static; without it a `--platform linux/arm64` run dies with
# `Exec format error` and, before this script counted its own rows, produced an
# empty file and a cheerful "0 offered, 0 absent". That is a measurement, and a
# false one (D-031).
#
# An `Architecture: all` package answers nothing to `pkg:arm64` -- there is no
# such binary, because the one binary serves every architecture. Reporting that
# as absent would be the same false negative in a smaller costume, so the
# foreign-arch path falls back to the architecture-independent candidate and
# marks the row so the distinction survives into the output.
#
# Output: `name<TAB>version` per line, `-` where there is no candidate, and
# `<version> (all)` where the answer came from an architecture-independent
# package. One container per target, one apt-cache call per package.
#
# Usage: scripts/apt-policy-sweep.sh <target-name> <image> <package-list-file> [platform]
#        scripts/apt-policy-sweep.sh --all <package-list-file>
set -euo pipefail
cd "$(dirname "$0")/.."

RUNTIME="${HAMMUNITION_RUNTIME:-podman}"
OUT_DIR="reference/probes"
mkdir -p "$OUT_DIR"

sandbox_user="_apt"
run_opts=()
if [[ "${HAMMUNITION_DEGRADED_PODMAN:-0}" == "1" ]]; then
    sandbox_user="root"
    run_opts=(--storage-opt ignore_chown_errors=true)
    echo "NOTE: degraded podman -- isolation is weakened (CLAUDE.md)." >&2
fi

IN_CONTAINER=$(cat <<'EOF'
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
APT_OPT="-o APT::Sandbox::User=$1 -o Acquire::Retries=3"
arch="${2:-}"
suffix=""
if [[ -n "$arch" ]]; then
    dpkg --add-architecture "$arch"
    suffix=":$arch"
fi
apt-get $APT_OPT -qq update >/dev/null 2>&1
candidate() {
    apt-cache $APT_OPT policy "$1" 2>/dev/null | awk '/^  Candidate:/ {print $2; exit}'
}
while read -r pkg; do
    [[ -z "$pkg" || "$pkg" == \#* ]] && continue
    ver=$(candidate "${pkg}${suffix}")
    if [[ -z "$ver" || "$ver" == "(none)" ]] && [[ -n "$suffix" ]]; then
        # No such binary for that architecture -- but an `Architecture: all`
        # package has exactly one binary and it serves every architecture.
        if apt-cache $APT_OPT show "$pkg" 2>/dev/null | grep -qx 'Architecture: all'; then
            ver=$(candidate "$pkg")
            [[ -n "$ver" && "$ver" != "(none)" ]] && ver="$ver (all)"
        fi
    fi
    [[ -z "$ver" || "$ver" == "(none)" ]] && ver="-"
    printf '%s\t%s\n' "$pkg" "$ver"
done
EOF
)

sweep_one() {
    local name="$1" image="$2" list="$3" platform="${4:-}"
    local podman_opts=("${run_opts[@]}")
    [[ -n "$platform" ]] && podman_opts+=(--platform "$platform")
    local out="$OUT_DIR/policy-${name}.tsv"

    "$RUNTIME" run --rm ${podman_opts[@]+"${podman_opts[@]}"} -i "$image" \
        bash -s -- "$sandbox_user" "${HAMMUNITION_FOREIGN_ARCH:-}" \
        < <(printf '%s\n### PACKAGES\n' "$IN_CONTAINER"; cat "$list") \
        > "$out.raw" 2>/dev/null || true
    grep -v '^### PACKAGES$' "$out.raw" > "$out" || true
    rm -f "$out.raw"

    # D-031: the run exiting 0 is not the evidence, the rows are.
    local wanted got
    wanted=$(grep -cvE '^[[:space:]]*(#|$)' "$list")
    got=$(wc -l < "$out")
    if (( got < wanted )); then
        echo "FAIL: $name answered for $got of $wanted packages." >&2
        echo "      An empty or short sweep is not a result. Check that the image" >&2
        echo "      pulls for this platform and that apt-get update succeeded." >&2
        rm -f "$out"
        return 1
    fi
    printf '%-16s %3d offered, %3d absent -> %s\n' "$name" \
        "$(awk -F'\t' '$2!="-"' "$out" | wc -l)" \
        "$(awk -F'\t' '$2=="-"' "$out" | wc -l)" "$out"
}

if [[ "${1:-}" == "--all" ]]; then
    list="$2"
    while IFS='|' read -r name image platform; do
        [[ -z "$name" ]] && continue
        sweep_one "$name" "$image" "$list" "$platform"
    done < <(python3 - <<'PY'
import pathlib
import re

text = pathlib.Path("containers/targets.yaml").read_text()
for block in text.split("\n  - name: ")[1:]:
    name = block.split("\n", 1)[0].strip()
    image = re.search(r"^\s+image:\s*(\S+)", block, re.M)
    platform = re.search(r"^\s+platform:\s*(\S+)", block, re.M)
    if image:
        print(f"{name}|{image.group(1)}|{platform.group(1) if platform else ''}")
PY
)
else
    sweep_one "$1" "$2" "$3" "${4:-}"
fi
