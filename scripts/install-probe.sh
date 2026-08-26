#!/usr/bin/env bash
# Attempt a REAL install of each named package and classify the outcome.
#
# `apt-cache policy` proves the archive *offers* a package. It does not prove
# dependency resolution succeeds on that release, which is the claim a
# capability-matrix row actually makes. This closes that gap.
#
# Three outcomes, because a rootless container without subordinate UID ranges
# cannot run a postinst that chowns to a system user, and that is an artifact of
# the harness rather than a fact about the package:
#
#   OK        unpacked and configured
#   DEGRADED  dependencies resolved and the package unpacked; its postinst
#             failed only on `chown ... Invalid argument`. Dependency
#             resolution — the thing being measured — succeeded. Real on a
#             machine with subuid ranges; see HAMMUNITION_DEGRADED_PODMAN.
#   FAIL      not in the archive, or dependencies could not be satisfied
#
# Run ONE package per invocation. Sharing a container across packages lets one
# broken postinst wedge dpkg and mark every later package failed, which is how
# the first version of this script produced 21 false failures.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
APT="apt-get -o APT::Sandbox::User=${APT_SANDBOX_USER:-_apt} -o DPkg::Lock::Timeout=-1"

pkg="$1"
out=$($APT install -y --no-install-recommends "$pkg" 2>&1)
status=$?
ver=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || echo "-")

if [[ $status -eq 0 ]]; then
    printf '%s\tOK\t%s\t\n' "$pkg" "$ver"
    exit 0
fi

# Unpacked but the postinst tripped only over an unmappable chown/chgrp.
if printf '%s' "$out" | grep -qiE "ch(own|grp).*Invalid argument" \
   && ! printf '%s' "$out" | grep -qiE "Unable to locate|have unmet dependencies|not going to be installed|no installation candidate"; then
    printf '%s\tDEGRADED\t%s\tpostinst chown unmappable in a rootless container without subuid\n' "$pkg" "$ver"
    exit 0
fi

reason=$(printf '%s' "$out" | grep -iE '^E:' | grep -viE 'Sub-process /usr/bin/dpkg' | head -1 | cut -c1-140)
[[ -z "$reason" ]] && reason=$(printf '%s' "$out" | grep -iE '^E:' | head -1 | cut -c1-140)
printf '%s\tFAIL\t%s\t%s\n' "$pkg" "${ver:--}" "${reason:-unknown}"
