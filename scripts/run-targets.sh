#!/usr/bin/env bash
# Build and validate every target container declared in containers/targets.yaml.
#
# RUNTIME: rootless Podman.
#
# We deliberately do NOT use Docker. Membership of the `docker` group grants
# root-equivalent access to the host, and this project's own security
# requirements say it runs alongside offensive tooling on a field laptop. CI
# that demands root-equivalent access to run would be a fair thing to roast a
# security-adjacent project for. Podman is rootless by default.
#
# If podman is missing or its rootless prerequisites are unmet, this exits
# non-zero with remediation rather than silently falling back to docker.
set -euo pipefail

cd "$(dirname "$0")/.."

RUNTIME="${HAMMUNITION_RUNTIME:-podman}"

if ! command -v "$RUNTIME" >/dev/null 2>&1; then
    cat >&2 <<MSG
ERROR: '$RUNTIME' is not installed.

Rootless Podman needs three things on Debian/Ubuntu, and installing the podman
package alone is NOT sufficient:

    sudo apt install podman uidmap podman-docker

    # podman     the runtime
    # uidmap     provides newuidmap/newgidmap — without these, rootless cannot
    #            map UIDs and every run fails
    # podman-docker  optional; provides a 'docker' shim for tools that expect it

Then ensure this account has subordinate ID ranges (it currently may not):

    grep "^\$(id -un):" /etc/subuid /etc/subgid \\
      || sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "\$(id -un)"
    podman system migrate

Do NOT work around this by joining the 'docker' group. That is root-equivalent
host access and is exactly the trade this project declined.
MSG
    exit 1
fi

if ! "$RUNTIME" info >/dev/null 2>&1; then
    echo "ERROR: '$RUNTIME' is installed but not usable. Check rootless setup:" >&2
    echo "  command -v newuidmap    # from the uidmap package" >&2
    echo "  grep \"^\$(id -un):\" /etc/subuid /etc/subgid" >&2
    echo "  $RUNTIME system migrate" >&2
    exit 1
fi

echo "runtime: $($RUNTIME --version)"

# ---------------------------------------------------------------------------
# Degraded mode, opt-in and loud.
#
# An account with no /etc/subuid and /etc/subgid ranges can still run rootless
# podman, but only with two workarounds:
#
#   --storage-opt ignore_chown_errors=true   image layers cannot be chowned
#   --build-arg APT_SANDBOX_USER=root        apt cannot drop to uid 42
#
# Both weaken the isolation the container is there to provide, so they are NOT
# the default and never silently applied. CI needs neither: its runners have
# subordinate ID ranges. The real fix on a dev machine is one root command,
# printed below.
#
# This exists because the alternative — joining the docker group — is the trade
# this project declined, and an unusable local harness is how people end up
# making it anyway.
# ---------------------------------------------------------------------------
BUILD_OPTS=()
RUN_OPTS=()
if [[ "${HAMMUNITION_DEGRADED_PODMAN:-0}" == "1" ]]; then
    BUILD_OPTS=(--build-arg "APT_SANDBOX_USER=root" --storage-opt ignore_chown_errors=true)
    RUN_OPTS=(--storage-opt ignore_chown_errors=true)
    cat >&2 <<'MSG'

┌─ DEGRADED MODE ──────────────────────────────────────────────────────────┐
│ HAMMUNITION_DEGRADED_PODMAN=1 is set. Container isolation is WEAKENED:   │
│   * apt runs as root inside the build instead of dropping to uid 42      │
│   * image layer ownership errors are ignored                            │
│                                                                          │
│ Results are still useful for type checking and package probes. Do NOT    │
│ treat a pass here as equivalent to CI.                                   │
│                                                                          │
│ Fix it properly — one root command, then re-run without this variable:   │
│   sudo usermod --add-subuids 100000-165535 \                             │
│                --add-subgids 100000-165535 "$(id -un)"                   │
│   podman system migrate                                                  │
└──────────────────────────────────────────────────────────────────────────┘

MSG
fi

targets=$(python3 - <<'PY'
import pathlib

import yaml

data = yaml.safe_load(pathlib.Path("containers/targets.yaml").read_text())
for t in data["targets"]:
    print(f"{t['name']}\t{t['image']}\t{t.get('platform', 'linux/amd64')}\t{t.get('claims', 'full')}")
PY
)

failed=()
while IFS=$'\t' read -r name image platform claims; do
    echo "═══ $name ($image, $platform, claims=$claims) ═══"
    if ! "$RUNTIME" build --platform="$platform" \
            -f containers/Dockerfile.target \
            --build-arg "BASE=$image" \
            ${BUILD_OPTS[@]+"${BUILD_OPTS[@]}"} \
            -t "hammunition-$name:local" . ; then
        failed+=("$name (build)"); continue
    fi
    if ! "$RUNTIME" run --rm --platform="$platform" \
            ${RUN_OPTS[@]+"${RUN_OPTS[@]}"} "hammunition-$name:local" \
            python scripts/capability_matrix.py --check ; then
        failed+=("$name (validate)"); continue
    fi
    if ! "$RUNTIME" run --rm --platform="$platform" \
            ${RUN_OPTS[@]+"${RUN_OPTS[@]}"} "hammunition-$name:local" \
            python -m pytest ; then
        failed+=("$name (tests)")
    fi
done <<< "$targets"

if (( ${#failed[@]} )); then
    printf '\nFAILED: %s\n' "${failed[*]}" >&2
    exit 1
fi
echo -e "\nall targets passed"
