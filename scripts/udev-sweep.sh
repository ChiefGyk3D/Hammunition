#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# Sweep an apt archive for every USB identifier its udev rules already name.
#
# WHY THIS EXISTS. The rtl-sdr entry carried three identifiers. Debian's own
# librtlsdr0 rule carries 42, and the missing 39 were not exotic -- Hauppauge,
# Terratec, Dexatek, Gigabyte, all RTL2832U underneath. Someone with a Hauppauge
# stick had a working device, no /dev symlink, and nothing anywhere telling them
# why. That is the exact failure this catalog refuses to guess its way into,
# arrived at by omission instead.
#
# So it is a method, not a fix, and the same shape as the Debian Blend task
# lists: curated, maintained, machine-readable data that nobody in this space
# has mined. A distribution's udev rules are a primary source about hardware we
# will never own, maintained by the people who ship the drivers.
#
# NO SILENT CAP. Every package in the archive that ships a udev rule is swept --
# all of them, not a curated list, because a curated list is exactly how the
# rtl-sdr gap happened in the first place. On Debian 13 that is ~280 packages
# and ~264 MB of downloads. Packages are DOWNLOADED and UNPACKED, never
# installed: this reads files, it does not configure anything.
#
# Output is TSV on stdout:
#   package  section  rules_file  vendor  product  symlink  comment  vendor_name  product_name

set -euo pipefail

# Rootless podman without subuid ranges cannot drop apt to _apt. Same workaround
# the container harness documents; it weakens isolation inside a throwaway
# container that installs nothing.
echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/99sandbox

log() { echo "[udev-sweep] $*" >&2; }

log "installing sweep tooling"
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends apt-file usb.ids dpkg-dev python3 >/dev/null

log "building the file index (this is the slow part)"
apt-file update >/dev/null 2>&1

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

apt-file search "udev/rules.d" 2>/dev/null | cut -d: -f1 | sort -u > packages
log "$(wc -l < packages) packages ship udev rules"

mkdir -p debs extracted
log "downloading"
# One at a time: a single unavailable package must not abort the sweep.
while read -r pkg; do
    (cd debs && apt-get download "$pkg" >/dev/null 2>&1) || log "  skipped (no download): $pkg"
done < packages

log "$(find debs -name '*.deb' | wc -l) archives downloaded; extracting rules"

# Extract ONLY the rules files, and judge success by whether a file appeared --
# never by tar's exit status.
#
# The first version of this used `dpkg-deb -x ... || continue`. Under rootless
# podman without subuid ranges, tar cannot chown or chmod, so it writes the
# files and THEN exits non-zero. Every one of 280 packages logged "bad archive"
# while the sweep still produced thousands of rows, so the run looked
# successful, the log said total failure, and the truth was a partial extraction
# nobody had characterised. Same shape as the install probe reporting 21 false
# failures, and the same fix: test the artifact, not the exit code.
extracted_ok=0
extract_failed=0
for deb in debs/*.deb; do
    [ -e "$deb" ] || continue
    pkg="$(basename "$deb" | cut -d_ -f1)"
    dest="extracted/$pkg"
    mkdir -p "$dest"
    dpkg-deb --fsys-tarfile "$deb" 2>/dev/null \
        | tar -x --no-same-permissions --no-same-owner --wildcards \
              -C "$dest" './*udev/rules.d/*' 2>/dev/null || true
    if find "$dest" -name '*.rules' -print -quit | grep -q .; then
        extracted_ok=$((extracted_ok + 1))
    else
        extract_failed=$((extract_failed + 1))
        log "  no rules file recovered: $pkg"
        rmdir "$dest" 2>/dev/null || true
    fi
done
log "rules recovered from $extracted_ok packages; $extract_failed yielded none"

log "parsing"
python3 - <<'PY'
import re, subprocess, sys
from pathlib import Path

def usb_ids(path="/usr/share/misc/usb.ids"):
    db, vendor = {}, None
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return db
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
    return db

DB = usb_ids()
SECTION = {}
for pkg_dir in sorted(Path("extracted").iterdir()):
    SECTION[pkg_dir.name] = ""
out = subprocess.run(["apt-cache", "show", *SECTION], capture_output=True, text=True, check=False)
current = None
for line in out.stdout.splitlines():
    if line.startswith("Package: "):
        current = line.split(" ", 1)[1].strip()
    elif line.startswith("Section: ") and current in SECTION and not SECTION[current]:
        SECTION[current] = line.split(" ", 1)[1].strip()

PAIR = re.compile(
    r"idVendor\}\s*==\s*\"([0-9a-fA-F]{4})\".*?idProduct\}\s*==\s*\"([0-9a-fA-F]{4})\"")
SYMLINK = re.compile(r'SYMLINK\+?=\s*"([^"]+)"')

rows = 0
for pkg_dir in sorted(Path("extracted").iterdir()):
    pkg = pkg_dir.name
    for rules in sorted(pkg_dir.rglob("udev/rules.d/*.rules")):
        comment = ""
        for line in rules.read_text(errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                text = stripped.lstrip("#").strip()
                # Keep only comments that look like a device name, not licence
                # boilerplate or commented-out rules.
                if text and len(text) < 60 and "==" not in text and not text.startswith("SPDX"):
                    comment = text
                continue
            m = PAIR.search(line)
            if not m:
                continue
            vendor, product = m.group(1).lower(), m.group(2).lower()
            link = SYMLINK.search(line)
            vname, pname = DB.get(vendor, ("", {}))[0], DB.get(vendor, ("", {}))[1].get(product, "")
            print("\t".join((
                pkg, SECTION.get(pkg, ""), rules.name, vendor, product,
                link.group(1) if link else "", comment, vname, pname)))
            rows += 1
print(f"[udev-sweep] {rows} identifiers extracted", file=sys.stderr)
PY
