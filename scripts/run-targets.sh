#!/usr/bin/env bash
# Build and validate every target container declared in containers/targets.yaml.
#
# This is the local equivalent of the CI `targets` job. It needs a usable
# docker; if the daemon is unreachable it says so and exits non-zero rather
# than skipping silently (D-016: fail loudly).
set -euo pipefail

cd "$(dirname "$0")/.."

if ! docker info >/dev/null 2>&1; then
    cat >&2 <<'MSG'
ERROR: docker is not usable by this user.

The daemon may be running while your account lacks access to the socket.
Check with:

    systemctl is-active docker
    ls -l /var/run/docker.sock
    id -nG | tr ' ' '\n' | grep -x docker

Adding yourself to the `docker` group grants root-equivalent access to the
host. On a machine that also holds security tooling that is a real decision,
not a formality — make it deliberately, or run these checks in CI instead.
MSG
    exit 1
fi

targets=$(python3 - <<'PY'
import yaml, pathlib
data = yaml.safe_load(pathlib.Path("containers/targets.yaml").read_text())
for t in data["targets"]:
    print(f"{t['name']}\t{t['image']}\t{t.get('platform', 'linux/amd64')}")
PY
)

failed=()
while IFS=$'\t' read -r name image platform; do
    echo "═══ $name ($image, $platform) ═══"
    if ! docker build --platform="$platform" \
            -f containers/Dockerfile.target \
            --build-arg "BASE=$image" \
            -t "hammunition-$name:local" . ; then
        failed+=("$name (build)"); continue
    fi
    if ! docker run --rm --platform="$platform" "hammunition-$name:local" \
            python scripts/capability_matrix.py --check ; then
        failed+=("$name (validate)"); continue
    fi
    if ! docker run --rm --platform="$platform" "hammunition-$name:local" \
            python -m pytest ; then
        failed+=("$name (tests)")
    fi
done <<< "$targets"

if (( ${#failed[@]} )); then
    printf '\nFAILED: %s\n' "${failed[*]}" >&2
    exit 1
fi
echo -e "\nall targets passed"
