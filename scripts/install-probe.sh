#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 The Hammunition contributors
# SPDX-License-Identifier: GPL-3.0-or-later

# Attempt a REAL install of one package and classify the outcome honestly.
#
# `apt-cache policy` proves the archive *offers* a package. It does not prove
# dependency resolution succeeds on that release, which is what a
# capability-matrix row actually claims. This closes that gap — and no more
# than that gap.
#
#   OK          resolved, unpacked and configured
#   UNRESOLVED  not in the archive, or dependencies could not be satisfied.
#               Trustworthy: this is a fact about the archive.
#   UNPACKED    dependencies resolved and the package unpacked, but
#               configuration failed. In a rootless container WITHOUT
#               subordinate UID ranges this is expected and near-universal for
#               anything pulling dbus or systemd: postinst scripts chown to
#               system users and the kernel returns EINVAL. It says nothing
#               about the package.
#
# The UNPACKED test is deliberately structural, not a string match on error
# text: if dpkg has a version recorded, resolution and unpack succeeded. An
# earlier version of this script tried to pattern-match the failure messages
# and mis-classified two packages, which is precisely the kind of guess D-018
# exists to prevent.
#
# Run ONE package per invocation. Sharing a container lets one broken postinst
# wedge dpkg and mark every later package failed — that produced 21 false
# failures on the first attempt.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
APT="apt-get -o APT::Sandbox::User=${APT_SANDBOX_USER:-_apt} -o DPkg::Lock::Timeout=-1"

pkg="$1"
out=$($APT install -y --no-install-recommends "$pkg" 2>&1)
status=$?
ver=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || true)

if [[ $status -eq 0 ]]; then
    printf '%s\tOK\t%s\t\n' "$pkg" "${ver:--}"
    exit 0
fi

if [[ -n "$ver" ]]; then
    detail=$(printf '%s' "$out" | grep -oiE '(ch(own|grp)|fchownat|statoverride|access ACL)[^\n]{0,40}Invalid argument' | head -1)
    printf '%s\tUNPACKED\t%s\t%s\n' "$pkg" "$ver" \
        "${detail:-configuration failed; dependency resolution and unpack succeeded}"
    exit 0
fi

reason=$(printf '%s' "$out" | grep -iE '^E:' | grep -viE 'Sub-process /usr/bin/dpkg' | head -1 | cut -c1-140)
[[ -z "$reason" ]] && reason=$(printf '%s' "$out" | grep -iE '^E:' | head -1 | cut -c1-140)
printf '%s\tUNRESOLVED\t-\t%s\n' "$pkg" "${reason:-unknown}"
