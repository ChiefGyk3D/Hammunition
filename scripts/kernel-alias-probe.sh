#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# Extract the kernel's USB id -> driver table.  D-028.
#
# `modules.alias` is the kernel's own statement about which driver claims which
# VID:PID. It is the strongest available evidence that an identifier names a
# CHIP rather than a device: if the pair sits in cp210x's or ftdi_sio's table,
# the kernel maintainers put it in a general-purpose bridge driver, and a udev
# symlink matching it will claim whatever else uses that chip.
#
# The kernel package is downloaded and unpacked, never installed -- this reads a
# text file out of a .deb. Separate from udev-sweep.sh so that adding this does
# not mean re-running a fifteen-minute archive sweep.
#
# Output is TSV on stdout:  vendor  product  driver

set -euo pipefail

echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/99sandbox
log() { echo "[kernel-alias] $*" >&2; }

log "resolving the kernel image package"
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends dpkg-dev kmod usb.ids python3 >/dev/null

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT; cd "$WORK"

# linux-image-amd64 is a metapackage; follow it to the real image.
image="$(apt-cache depends linux-image-amd64 2>/dev/null \
        | awk '/Depends: linux-image-/{print $2; exit}')"
[ -n "$image" ] || { log "no linux-image-amd64 dependency found"; exit 1; }
version="${image#linux-image-}"
log "downloading $image"
apt-get download "$image" >/dev/null 2>&1 || { log "download failed"; exit 1; }

log "extracting modules"
# The kernel .deb does NOT ship modules.alias -- depmod generates it at install
# time -- so it is generated here from the extracted module tree. Modules live
# under usr/lib/modules on a usrmerge system and depmod wants <base>/lib/modules,
# hence the symlink.
#
# Only the file is extracted and success is judged by whether it appeared, never
# by tar's exit status: under rootless podman tar cannot chmod and exits non-zero
# after writing perfectly good files. See the same note in udev-sweep.sh.
mkdir -p root
dpkg-deb --fsys-tarfile ./*.deb 2>/dev/null \
    | tar -x --no-same-permissions --no-same-owner -C root 2>/dev/null || true
modules="$(find root -name '*.ko*' | wc -l)"
[ "$modules" -gt 0 ] || { log "no kernel modules recovered"; exit 1; }
log "$modules modules; running depmod"
ln -sfn usr/lib root/lib 2>/dev/null || true
depmod -b "$WORK/root" "$version" 2>/dev/null || true
alias_file="$(find root -name modules.alias -print -quit)"
[ -n "$alias_file" ] || { log "depmod produced no modules.alias"; exit 1; }

# alias usb:v10C4pEA60d*dc*dsc*dp*ic*isc*ip*in* cp210x
#
# Only aliases fixing BOTH vendor and product are useful; a class-only alias
# says nothing about a specific pair. sed rather than awk's match() with a third
# argument, which is a GNU extension the container's mawk does not have.
# Joined against usb.ids so the fourth column says what the pair actually is.
# Without it the dataset is 2,000 opaque hex pairs and nobody can review whether
# a flag is right -- and the whole point of D-028 is that both error directions
# are silent, so the evidence has to be legible.
sed -nE 's/^alias usb:v([0-9A-Fa-f]{4})p([0-9A-Fa-f]{4})[^ ]* +(.+)$/\1\t\2\t\3/p' \
    "$alias_file" \
    | awk -F'\t' '{ print tolower($1) "\t" tolower($2) "\t" $3 }' \
    | sort -u > pairs.tsv

python3 - <<'PYEOF'
import re
db, vendor = {}, None
try:
    handle = open("/usr/share/misc/usb.ids", encoding="utf-8", errors="replace")
except OSError:
    handle = None
if handle:
    with handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            m = re.match(r"^([0-9a-fA-F]{4})\s+(.*)$", line)
            if m:
                vendor = m.group(1).lower()
                db[vendor] = (m.group(2).strip(), {})
                continue
            m = re.match(r"^\t([0-9a-fA-F]{4})\s+(.*)$", line)
            if m and vendor:
                db[vendor][1][m.group(1).lower()] = m.group(2).strip()
with open("pairs.tsv") as fh:
    for line in fh:
        v, p, driver = line.rstrip("\n").split("\t")
        name = db.get(v, ("", {}))[1].get(p, "")
        print("\t".join((v, p, driver, name)))
PYEOF

log "done"
