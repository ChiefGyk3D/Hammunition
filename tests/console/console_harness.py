# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The real `hammunition console` entry point with the engine replaced by the fake.

Usage: python -m console.console_harness SHIM

For tests/console/test_pty_install.py only. It goes through the same
refusals and the same `run` as the subcommand; the one difference is that the
console drives SHIM (a `hammunition` that runs fake_hammunition.py) instead of
`python -m hammunition`, so no test ever runs the real engine.
"""

from __future__ import annotations

import sys

from hammunition.console.__main__ import main
from hammunition.console.engine import Engine


def run(shim: str) -> int:
    return main([], engine=Engine(argv0=[shim]))


if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
