#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Regenerate the hash-pinned lock files (OpenSSF Scorecard: PinnedDependencies).
# Needs `uv` (pipx run uv, or pip install uv in a scratch venv) and the network.
# One universal lock per set covers Python 3.11 to 3.14 and every platform.
set -euo pipefail
cd "$(dirname "$0")/.."
compile() { uv pip compile pyproject.toml "$@" --generate-hashes --python-version 3.11 --universal -q; }
compile -o requirements/runtime.txt
compile --extra dev -o requirements/dev.txt
compile --extra docs -o requirements/docs.txt
.venv/bin/python scripts/check_locks.py --check 2>/dev/null || python3 scripts/check_locks.py --check
