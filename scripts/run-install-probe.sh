#!/usr/bin/env bash
# Drive scripts/install-probe.sh once per package, in a fresh container each
# time, against one target image. Writes a TSV to reference/install-tests/.
#
# Usage: scripts/run-install-probe.sh <target-name> <image> <package-list-file>
set -euo pipefail
cd "$(dirname "$0")/.."

RUNTIME="${HAMMUNITION_RUNTIME:-podman}"
name="$1"; image="$2"; list="$3"
: "${sandbox_user:=_apt}"
out="reference/install-tests/${name}.tsv"
mkdir -p reference/install-tests

build_opts=()
run_opts=()
sandbox_user="_apt"
if [[ "${HAMMUNITION_DEGRADED_PODMAN:-0}" == "1" ]]; then
    sandbox_user="root"
    build_opts=(--storage-opt ignore_chown_errors=true --build-arg "APT_SANDBOX_USER=root")
    run_opts=(--storage-opt ignore_chown_errors=true -e APT_SANDBOX_USER=root)
    echo "NOTE: degraded podman — configuration failures are reported as UNPACKED, not as package defects." >&2
fi

# Populate apt lists once so each package run starts from a warm cache.
base="hammunition-probe-${name}:local"
"$RUNTIME" build ${build_opts[@]+"${build_opts[@]}"} -q -t "$base" - <<EOF >/dev/null
FROM ${image}
ARG APT_SANDBOX_USER=_apt
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get -o APT::Sandbox::User=\${APT_SANDBOX_USER} -qq update
EOF

: > "$out"
while read -r pkg; do
    [[ -z "$pkg" || "$pkg" == \#* ]] && continue
    "$RUNTIME" run --rm ${run_opts[@]+"${run_opts[@]}"} \
        -v "$PWD/scripts/install-probe.sh:/probe.sh:ro" "$base" \
        bash /probe.sh "$pkg" >> "$out" 2>/dev/null \
        || printf '%s\tFAIL\t-\tcontainer run failed\n' "$pkg" >> "$out"
done < "$list"

printf '\n%s:\n' "$name"
awk -F'\t' '{c[$2]++} END {for (k in c) printf "  %-9s %d\n", k, c[k]}' "$out"
