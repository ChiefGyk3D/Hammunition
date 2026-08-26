#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# Mine the LoRa mesh firmware projects for USB identifiers.
#
# The same method as scripts/udev-sweep.sh, pointed somewhere Debian cannot
# reach. Meshtastic and MeshCore both build with PlatformIO, so every supported
# board carries a `boards/*.json` with a `build.hwids` array: the identifiers
# the flashing tools look for. That is curated, machine-readable, maintained by
# the people who ship the firmware -- exactly the shape that made the Debian
# udev rules worth mining.
#
# It matters more here than convenience. This catalog's `meshtastic` entry could
# not be closed by a capture even in principle: the maintainer's boards were
# lost in a flood, and "Meshtastic" was never one device anyway. Upstream
# publishes what a hundred boards present, and none of them has to be on a desk.
#
# Expect the result to be lopsided. A first look shows dozens of distinct
# products sharing a handful of identifiers -- Espressif's 303a:1001, Adafruit's
# nRF52840 bootloader ids -- which is the D-028 thesis arriving from a third
# independent direction.
#
# Output is TSV on stdout:  project  board_file  board_name  vendor  product  source

set -euo pipefail

log() { echo "[lora-sweep] $*" >&2; }

# Rootless podman without subuid ranges cannot drop apt to _apt; same
# workaround the rest of the container tooling documents.
echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/99sandbox
log "installing tooling"
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends git ca-certificates python3 >/dev/null

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT; cd "$WORK"

# project:repo. Shallow clones -- this reads board metadata, not history.
PROJECTS=(
    "meshtastic:meshtastic/firmware"
    "meshcore:meshcore-dev/MeshCore"
    "rnode:markqvist/RNode_Firmware"
)

for entry in "${PROJECTS[@]}"; do
    name="${entry%%:*}"; repo="${entry#*:}"
    log "cloning $repo"
    git clone -q --depth 1 "https://github.com/$repo" "$name" 2>/dev/null \
        || { log "  unavailable: $repo"; continue; }
done

python3 - <<'PY'
import json
import re
import sys
from pathlib import Path

PAIR = re.compile(r'idVendor\}\s*==\s*"([0-9a-fA-F]{4})".*?idProduct\}\s*==\s*"([0-9a-fA-F]{4})"')

rows = 0
for project in sorted(p for p in Path().iterdir() if p.is_dir()):
    # PlatformIO board definitions: build.hwids is a list of [vid, pid] pairs.
    for board in sorted(project.rglob("boards/*.json")):
        try:
            data = json.loads(board.read_text(errors="replace"))
        except (OSError, ValueError):
            continue
        hwids = (data.get("build") or {}).get("hwids") or []
        name = (data.get("name") or "").replace("\t", " ").strip()
        for pair in hwids:
            if not isinstance(pair, list) or len(pair) != 2:
                continue
            vendor, product = (str(x).lower().removeprefix("0x") for x in pair)
            print("\t".join((project.name, board.name, name, vendor, product, "platformio")))
            rows += 1
    # udev rules shipped alongside the firmware.
    for rules in sorted(project.rglob("*.rules")):
        for line in rules.read_text(errors="replace").splitlines():
            m = PAIR.search(line)
            if m:
                print("\t".join((project.name, rules.name, "", m.group(1).lower(),
                                 m.group(2).lower(), "udev")))
                rows += 1
print(f"[lora-sweep] {rows} identifier rows", file=sys.stderr)
PY
