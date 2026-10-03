# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the fake long command through the real executor, as `install` does:
the run log on, the status writer active, the `$` line echoed through it.

argv: <slow_lines.py> [--verbose] [--long]. XDG_STATE_HOME says where the run
log goes; the test reads it back."""

import os
import sys
from pathlib import Path

from hammunition import runlog
from hammunition.backends import Command, SubprocessRunner
from hammunition.distro import Target
from hammunition.execute import execute
from hammunition.plan import InstallPlan
from hammunition.progress import LiveStatus, activate_live
from hammunition.state import TransactionLog

script, flags = sys.argv[1], set(sys.argv[2:])
command = Command(
    argv=(sys.executable, script),
    description="a fake long step",
    long_running="--long" in flags,
)
plan = InstallPlan(target=Target(distro="debian", version="13", arch="x86_64"), packages=())
log = TransactionLog(path=Path(os.environ["XDG_STATE_HOME"]) / "transaction.jsonl")
live = LiveStatus(verbose="--verbose" in flags, after=0.5, interval=0.3)
with runlog.session(command="install", argv=["install"], owner=None, version="t"):
    with activate_live(live):
        report = execute([command], SubprocessRunner(), log=log, plan=plan, echo=live.print)
    print("done" if report.ok else "failed")
