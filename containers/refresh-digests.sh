#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Re-resolve the base-image digests pinned in containers/targets.yaml and the
# CI matrix in .github/workflows/ci.yml (OpenSSF Scorecard: PinnedDependencies).
#
#   containers/refresh-digests.sh           rewrite both files in place
#   containers/refresh-digests.sh --check   report drift, change nothing (exit 1)
#
# Every `image:` value is `repo:tag@sha256:<index digest>`; the tag is kept
# beside the digest so the human reading it still sees what it follows, and
# podman ignores it in favour of the digest. The digest is that of the
# multi-arch INDEX, so the arm64 target resolves the same pin natively. All six
# images are on Docker Hub; the registry is asked directly with curl, the same
# way `git ls-remote --tags` re-resolves an action pin.
set -euo pipefail
cd "$(dirname "$0")/.."

check=0
[ "${1:-}" = "--check" ] && check=1

accept='application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'

resolve() { # repo:tag -> sha256:...
    local ref=$1 repo tag token digest
    repo=${ref%%:*}; tag=${ref##*:}
    case "$repo" in */*) ;; *) repo="library/$repo" ;; esac
    token=$(curl -fsS "https://auth.docker.io/token?service=registry.docker.io&scope=repository:$repo:pull" \
        | python3 -c 'import sys, json; print(json.load(sys.stdin)["token"])')
    digest=$(curl -fsSI -H "Authorization: Bearer $token" -H "Accept: $accept" \
        "https://registry-1.docker.io/v2/$repo/manifests/$tag" \
        | tr -d '\r' | awk -F': ' 'tolower($1) == "docker-content-digest" {print $2}')
    case "$digest" in sha256:????????????????????????????????????????????????????????????????) echo "$digest" ;;
        *) echo "could not resolve $ref" >&2; return 1 ;; esac
}

drift=0
for file in containers/targets.yaml .github/workflows/ci.yml containers/Dockerfile.target; do
    # `image: "repo:tag@sha256:..."` (optionally quoted) or the Dockerfile's `ARG BASE=`.
    mapfile -t refs < <(grep -oE '(image: "?|ARG BASE=)[a-z0-9./_-]+:[A-Za-z0-9._-]+(@sha256:[0-9a-f]{64})?' "$file" \
        | sed -E 's/^(image: "?|ARG BASE=)//; s/@sha256:.*//' | sort -u)
    for ref in "${refs[@]}"; do
        digest=$(resolve "$ref")
        # Every occurrence must carry the current digest, none an older one (a comment
        # line holding the right digest must not hide a stale default).
        if [ "$(grep -oF "$ref@sha256:" "$file" | wc -l)" -ne "$(grep -oF "$ref@$digest" "$file" | wc -l)" ] \
            || ! grep -qF "$ref@$digest" "$file"; then
            drift=1
            echo "$file: $ref -> $digest"
            [ "$check" -eq 1 ] || sed -i -E "s#(image: \"?|ARG BASE=)${ref}(@sha256:[0-9a-f]{64})?#\1${ref}@${digest}#" "$file"
        fi
    done
done

if [ "$check" -eq 1 ] && [ "$drift" -eq 1 ]; then
    echo "pinned digests are stale; run containers/refresh-digests.sh" >&2
    exit 1
fi
[ "$drift" -eq 1 ] || echo "digests current"
