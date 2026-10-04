# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The whole console, in a real pseudo-terminal, against the fake hammunition:
Home -> Install -> plan -> R -> the pane -> a person types yes -> result."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .helpers import SRC_DIR, TESTS_DIR, load, make_shim
from .pty_driver import PtyProcess

pytestmark = [
    pytest.mark.pty,
    # The console refuses root by design; the distro containers run the suite as root.
    pytest.mark.skipif(os.geteuid() == 0, reason="the console refuses to run as root"),
]


def env_for(tmp: Path) -> dict[str, str]:
    home = tmp / "home"
    home.mkdir()
    return {
        "PATH": f"{make_shim(tmp)}:{os.environ['PATH']}",
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "PYTHONPATH": f"{SRC_DIR}{os.pathsep}{TESTS_DIR}",
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_HAMMUNITION_LOG": str(tmp / "fake.log"),
        "HAMMUNITION_ACCEPT_RF_RESEARCH": "1",  # a canary: no child of the console may ever see it
    }


def shim_of(env: dict[str, str]) -> Path:
    return Path(env["PATH"].split(os.pathsep)[0]) / "hammunition"


def test_install_end_to_end_with_a_typed_yes(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    first = load("list-all")["profiles"][0]["name"]
    proc = PtyProcess([sys.executable, "-m", "console.console_harness", str(shim_of(env))], env)
    try:
        proc.expect("Install")
        proc.send("1")
        proc.expect(first)
        proc.send("\x1b[B")  # down: off the name box onto the first profile
        proc.send("\r")
        proc.expect("changes nothing")
        proc.send("R")
        proc.expect("continue:")
        proc.send("yes\r")
        proc.expect("Finished with exit code 0")
        proc.send("\r")
        proc.expect("Exit code: 0")
        proc.send("b")
        proc.expect(first)
        proc.send("q")
        assert proc.wait() == 0
    finally:
        proc.close()
    entries = [json.loads(line) for line in (tmp_path / "fake.log").read_text().splitlines()]
    assert entries, "the fake was never called"
    for entry in entries:
        assert "HAMMUNITION_ACCEPT_RF_RESEARCH" not in entry["env"], entry
        assert "--yes" not in entry["argv"] and "-y" not in entry["argv"], entry
    real = [e for e in entries if e["argv"][:1] == ["install"] and "--dry-run" not in e["argv"]]
    assert len(real) == 1 and real[0]["argv"] == ["install", first] and real[0]["tty"] is True
    dry = [e for e in entries if "--dry-run" in e["argv"]]
    assert dry and dry[0]["tty"] is False, "reads must never have a terminal"


def test_the_console_refuses_a_pipe(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "hammunition", "console"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
    )
    assert done.returncode == 2 and "terminal" in done.stderr
