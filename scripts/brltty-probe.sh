#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# Runs INSIDE a target container (see run-brltty-probe.sh). Answers, for one
# target, the question D-042 sub-project 2 asked: does this distribution's
# brltty ship a udev rule that claims a USB identifier our hardware catalog
# also names?  brltty is the package AHRL purges unconditionally and EmComm
# Tools shadows with an empty 85-brltty.rules, because its rules once claimed
# every FTDI, CP210x and CH340 bridge as a braille display.
#
# The package is DOWNLOADED and read, never installed. Nothing here configures
# anything. Output is plain text on stdout, one "### section" per fact, read
# by scripts/gen_brltty_inventory.py.
#
# The udev sweep (udev-sweep.sh) does not answer this on its own: it covers
# Debian 13, where brltty ships no rules at all, and until 2026-09-12 its parser
# read only the ATTRS{idVendor} syntax -- brltty writes ENV{PRODUCT}=="403/de58/*"
# and had zero rows in a sweep that claimed to filter nothing.

set -u
export DEBIAN_FRONTEND=noninteractive
ARCH="${1:-}"

# Rootless podman without subuid ranges cannot drop apt to _apt. Same
# workaround the sweep and the harness use; it weakens isolation inside a
# throwaway container that installs nothing.
echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/99sandbox
cd /tmp
if [ -n "$ARCH" ]; then dpkg --add-architecture "$ARCH"; fi
apt-get update -qq >/dev/null 2>&1 || apt-get update -qq >/dev/null

pkg="brltty${ARCH:+:$ARCH}"
echo "### target"
grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
echo "### candidate"
apt-cache policy "$pkg" | sed -n 's/^  Candidate: //p'

# Who brings brltty onto a machine: every package whose Depends, Recommends or
# Suggests names it, with the relation. Recommends is installed by default;
# Suggests is not. This is how "brltty is on every Ubuntu desktop" becomes a
# measured claim instead of a remembered one.
echo "### pulled-in-by"
for r in $(apt-cache rdepends "$pkg" 2>/dev/null | sed '1,2d; s/^ *//; s/^|//' | sort -u); do
    rel=$(apt-cache show "$r" 2>/dev/null \
        | grep -E '^(Depends|Recommends|Suggests):' \
        | grep -E '(^|[ ,|])brltty([ ,|(]|$)' | head -1 | cut -d: -f1)
    [ -n "$rel" ] && echo "$r $rel"
done

echo "### download"
apt-get download "$pkg" >/dev/null 2>&1 || true
deb=$(ls brltty_*.deb 2>/dev/null | head -1)
if [ -z "$deb" ]; then
    echo "NO DEB"
    exit 0
fi
echo "### version"
echo "$(dpkg-deb -f "$deb" Version) $(dpkg-deb -f "$deb" Architecture)"

# What the package SHIPS under udev/rules.d, from the archive's own file list
# -- so a target that ships none is a measured "none", not an extraction that
# silently found nothing (D-031).
echo "### udev-rules-shipped"
dpkg-deb -c "$deb" | awk '{print $6}' | grep -E 'udev/rules\.d/.*\.rules$' || echo none

# Extract ONLY the rules files, by whether a file appeared -- never by
# dpkg-deb's exit status, which is non-zero under rootless podman after the
# files are already written.
rm -rf x && mkdir x
dpkg-deb --fsys-tarfile "$deb" \
    | tar -x --no-same-owner --no-same-permissions -C x --wildcards './*udev/rules.d/*' 2>/dev/null || true
for f in $(find x -path '*udev/rules.d/*' -name '*.rules' | sort); do
    echo "### FILE ${f#x} sha256=$(sha256sum "$f" | cut -c1-64)"
    cat "$f"
    echo "### END FILE"
done
