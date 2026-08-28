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
#   package  section  rules_file  vendor  product  symlink  comment  vendor_name
#   product_name  enabled  disabled_reason  subsystem
#
# DISABLED RULES ARE EXTRACTED TOO, and they turned out to be the best evidence
# in the whole sweep. Debian's own gpsd rules file comments five identifiers out
# with the line "!!! rule disabled in Debian as it matches too many other
# devices" -- 0403:6001, 10c4:ea60, 10c4:ea71 and 067b:2303 twice. That is a
# distribution maintainer stating in a shipped file that an identifier does not
# name a device, which is stronger evidence than anything this project infers
# from modules.alias, and it independently reaches D-028's conclusion about two
# of the same identifiers. Discarding it as "a comment" was throwing away the
# one source that says *why*.

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
# Which subsystem the rule matches, which is the only thing in a rules file that
# says what KIND of device it is. `tty` means a serial port; `usb` means the bus
# device, which is what a libusb program opens. Recorded because inferring it
# 180 times for the programmer class would be guessing 180 times, and because
# it is how the DMR class established that an Anytone is a serial device.
SUBSYSTEM = re.compile(r'SUBSYSTEMS?\s*==\s*"([^"]+)"')

# Boilerplate a comment must not be mistaken for a device description. The
# previous filter was `len(text) < 60`, which rejected
# "u-blox AG, u-blox 5 (tested with Navilock NL-402U) [linux module: cdc_acm]"
# at 73 characters and then -- the actual defect -- KEPT THE PREVIOUS COMMENT,
# so the published inventory described a u-blox as a Silicon Labs CP210x. A
# rejected comment now clears the field instead of leaving the last one
# standing: no description is honest, someone else's is not.
BOILERPLATE = re.compile(
    r"^(SPDX|Copyright|This file|udev rules|Do not|# )|generated by|^!!!", re.IGNORECASE)
# A comment about what the RULE does, carrying no device name. qdmr's and
# dmrconfig's rules both read
#
#     # Anytone AT-D868UV, AT-D878UV
#     # Ignore this device in Modem Manager
#     ATTRS{idVendor}=="28e9" ...
#
# and taking the nearest comment records the radio as "Ignore this device in
# Modem Manager". Same family as the stale-comment bug above, from the other
# side: there the nearest comment was missing, here it is present and is not a
# description.
#
# DELIBERATELY NARROW. Six rows in the whole sweep match a broader
# "directive-shaped comment" pattern and only these two benefit: "Set ACLs for
# console users on Samsung Galaxy S devices" and "Add permission ... to eeprom
# programmer CH341" both name their device, and a filter that dropped them
# would trade a small gain for a larger loss.
NOT_A_DESCRIPTION = re.compile(r"^ignore\s+th\w+\s+device\s+in\s+modem\s*manager", re.IGNORECASE)
# A commented-out rule, and why it was commented out. Two forms: the reason
# line ("!!! rule disabled in Debian as ...") and the rule itself on the
# following line.
DISABLED_REASON = re.compile(r"^!+\s*(rule\s+disabled.*|disabled.*)$", re.IGNORECASE)

rows = 0
disabled_rows = 0
for pkg_dir in sorted(Path("extracted").iterdir()):
    pkg = pkg_dir.name
    for rules in sorted(pkg_dir.rglob("udev/rules.d/*.rules")):
        comment = ""
        reason = ""
        for line in rules.read_text(errors="replace").splitlines():
            stripped = line.strip()
            enabled = "1"
            if stripped.startswith("#"):
                text = stripped.lstrip("#").strip()
                if not PAIR.search(text):
                    match = DISABLED_REASON.match(text)
                    if match:
                        reason = match.group(1)
                    elif NOT_A_DESCRIPTION.match(text):
                        # Says what the rule does, not what the device is. Keep
                        # whatever named the device on the line above.
                        pass
                    elif not text or BOILERPLATE.search(text):
                        # Clear rather than carry: the next rule gets no
                        # description sooner than it gets the wrong one.
                        comment = ""
                    else:
                        comment = text
                    continue
                # A commented-out rule. Emitted, because a distribution
                # switching one off and saying why is the strongest statement
                # available that an identifier does not name a device.
                enabled = "0"
                stripped = text
            m = PAIR.search(stripped)
            if not m:
                continue
            vendor, product = m.group(1).lower(), m.group(2).lower()
            link = SYMLINK.search(stripped)
            vname, pname = DB.get(vendor, ("", {}))[0], DB.get(vendor, ("", {}))[1].get(product, "")
            subsystem = SUBSYSTEM.search(stripped)
            print("\t".join((
                pkg, SECTION.get(pkg, ""), rules.name, vendor, product,
                link.group(1) if link else "", comment, vname, pname,
                enabled, reason if enabled == "0" else "",
                subsystem.group(1) if subsystem else "")))
            if enabled == "0":
                disabled_rows += 1
                reason = ""
            else:
                rows += 1
print(f"[udev-sweep] {rows} identifiers extracted, "
      f"{disabled_rows} from rules a distribution disabled", file=sys.stderr)
PY
