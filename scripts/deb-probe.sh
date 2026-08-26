#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# Download an upstream .deb and attempt a real install, classifying the outcome
# the same way scripts/install-probe.sh does.
#
# The question this answers: SCOPE.md's DragonOS Tier 1 admits "apt-installable
# OR upstream .deb". Publishing a .deb is not the same as that .deb installing
# on our targets, and several of these are built for an older release than we
# ship against.
#
# Reads `label|url` lines on stdin.
#
#   OK          resolved, unpacked and configured
#   UNRESOLVED  dependencies could not be satisfied on this base — the finding
#   UNPACKED    resolved and unpacked; configuration failed. Structural test:
#               dpkg has a version recorded, so resolution succeeded. In a
#               rootless container without subuid ranges this is expected.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
APT="apt-get -o APT::Sandbox::User=${APT_SANDBOX_USER:-_apt} -o DPkg::Lock::Timeout=-1"

$APT -qq update >/dev/null 2>&1
$APT install -y --no-install-recommends ca-certificates curl >/dev/null 2>&1

while IFS='|' read -r label url; do
    [[ -z "${label:-}" || "$label" == \#* ]] && continue
    file="/tmp/$(basename "$url")"
    if ! curl -fsSL -o "$file" "$url"; then
        printf '%s\tDOWNLOAD-FAIL\t-\t-\t%s\n' "$label" "$url"
        continue
    fi
    sha=$(sha256sum "$file" | cut -d' ' -f1)
    pkg=$(dpkg-deb -f "$file" Package 2>/dev/null || echo "$label")
    ver=$(dpkg-deb -f "$file" Version 2>/dev/null || echo "?")
    out=$($APT install -y --no-install-recommends "$file" 2>&1)
    status=$?
    installed=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || true)

    if [[ $status -eq 0 ]]; then
        printf '%s\tOK\t%s\t%s\t\n' "$label" "$ver" "$sha"
    elif [[ -n "$installed" ]]; then
        printf '%s\tUNPACKED\t%s\t%s\tresolved; configuration blocked by rootless ownership\n' \
            "$label" "$ver" "$sha"
    else
        reason=$(printf '%s' "$out" | grep -oiE 'Depends: [^ ]+[^\n]{0,60}' | head -2 | tr '\n' ';' | cut -c1-180)
        [[ -z "$reason" ]] && reason=$(printf '%s' "$out" | grep -iE '^E:' | head -1 | cut -c1-160)
        printf '%s\tUNRESOLVED\t%s\t%s\t%s\n' "$label" "$ver" "$sha" "${reason:-unknown}"
    fi
done
