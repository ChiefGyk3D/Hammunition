#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Regenerate the hash-pinned lock files (OpenSSF Scorecard: PinnedDependencies).
# Needs `uv` (pipx run uv, or pip install uv in a scratch venv) and the network.
# One universal lock per set covers Python 3.11 to 3.14 and every platform.
set -euo pipefail
cd "$(dirname "$0")/.."
# The output goes last so the header the lock records names the extra first, which is
# what scripts/check_locks.py looks for.
compile() { local out=$1; shift; uv pip compile pyproject.toml "$@" --generate-hashes --python-version 3.11 --universal -q -o "$out"; }
compile requirements/runtime.txt
compile requirements/console.txt --extra console
compile requirements/dev.txt --extra dev
compile requirements/docs.txt --extra docs
.venv/bin/python scripts/check_locks.py --check 2>/dev/null || python3 scripts/check_locks.py --check
