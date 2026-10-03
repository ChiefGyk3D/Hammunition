#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The CI test command (the `ci` job's `test-command`, run once per Python).
#
# The tether contract test reads hammunition-gps-tether's source and used to
# skip without it, so the drift check never ran (#215). The tag is read from
# the manifest, never written in the workflow: a re-pin moves CI too. The
# clone sits beside the workspace, where tests/test_tether_contract.py looks.
set -euo pipefail

cd "$(dirname "$0")/.."

tag=$(grep -oP 'hammunition-gps-tether/archive/refs/tags/\Kv[0-9][^/ ]*?(?=\.tar\.gz)' \
  catalog/packages/gps-tether.yaml | head -n 1)
test -n "$tag"

dest=../hammunition-gps-tether
if [ ! -d "$dest" ]; then
  git clone --quiet --depth 1 --branch "$tag" \
    https://github.com/ChiefGyk3D/hammunition-gps-tether "$dest"
fi

HAMMUNITION_REQUIRE_TETHER=1 exec python -m pytest
