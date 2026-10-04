# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""How the console runs the engine: one function, one answer.

The console drives the engine through its `--json` documents as a subprocess
(D-059). It runs the interpreter that is running it, `-m hammunition`, so the
engine it drives is always the one it shipped with: the same in a checkout's
venv, under the bootstrap-linked `~/.local/bin/hammunition` (whose script
points at that venv's interpreter) and in a packaged install, with no
dependence on what `hammunition` happens to resolve to on PATH.
"""

from __future__ import annotations

import sys


def engine_argv() -> list[str]:
    """The argv prefix that runs this installation's engine."""
    return [sys.executable, "-m", "hammunition"]
