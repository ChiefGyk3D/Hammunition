# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from .helpers import SRC_DIR, TESTS_DIR, make_shim
from .pty_driver import PtyProcess

pytestmark = pytest.mark.pty


def env_for(tmp: Path) -> dict[str, str]:
    return {
        "PATH": f"{make_shim(tmp)}:{os.environ['PATH']}",
        "HOME": str(tmp),
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "PYTHONPATH": f"{SRC_DIR}{os.pathsep}{TESTS_DIR}",
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_HAMMUNITION_LOG": str(tmp / "fake.log"),
        "HARNESS_RESULT": str(tmp / "result"),
        "HAMMUNITION_ACCEPT_RF_RESEARCH": "1",  # a canary: it must not reach the child
    }


def harness(env: dict[str, str]) -> PtyProcess:
    return PtyProcess(
        [sys.executable, "-m", "console.pane_harness", "--", "hammunition", "install", "station"],
        env,
    )


def test_a_person_typing_yes_into_a_real_tty_is_what_confirms(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    proc = harness(env)
    try:
        proc.expect("continue:")
        proc.send("yes\r")
        proc.expect("Finished with exit code 0")
        proc.send("\r")
        assert proc.wait() == 0
    finally:
        proc.close()
    assert (tmp_path / "result").read_text().strip() == "0"
    entry = json.loads((tmp_path / "fake.log").read_text().splitlines()[0])
    assert entry["argv"] == ["install", "station"] and entry["tty"] is True
    assert "HAMMUNITION_ACCEPT_RF_RESEARCH" not in entry["env"], (
        "the consent variable leaked into the pane's child"
    )


def test_anything_but_yes_is_declined_and_the_exit_code_is_the_engines(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    proc = harness(env)
    try:
        proc.expect("continue:")
        proc.send("no\r")
        proc.expect("Finished with exit code 3")
        proc.send("\r")
        proc.wait()
    finally:
        proc.close()
    assert (tmp_path / "result").read_text().strip() == "3"


def test_the_same_fake_refuses_without_a_tty_so_the_tty_above_was_real(tmp_path: Path) -> None:
    shim = make_shim(tmp_path)
    done = subprocess.run(
        ["hammunition", "install", "station"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"},
    )
    assert done.returncode == 3 and "no interactive terminal" in done.stderr


def test_every_key_reaches_the_running_program_and_the_pane_cannot_be_left(tmp_path: Path) -> None:
    """Esc, b, q, Ctrl-A (twice, to hit urwid's escape handling) and an arrow, typed before
    anything printable, all reach the child. The harness quits on a q/b/esc handed up, as
    the Shell does, so a key leaking past the pane would end the process."""
    env = env_for(tmp_path)
    keys = tmp_path / "keys"
    env["FAKE_HAMMUNITION_KEYS"] = str(keys)
    proc = harness(env)
    try:
        proc.expect("recording")
        for key in ("\x1b", "b", "q", "\x01", "\x01", "\x1b[A", " "):
            proc.send(key)
            time.sleep(0.15)
        proc.send("X")
        proc.expect("Finished with exit code 0")
        got = bytes.fromhex("".join(keys.read_text().split())).decode("latin-1")
        assert got == "\x1bbq\x01\x01\x1b[A X"
        assert proc.proc.poll() is None, "the console left the pane while the program ran"
        proc.send("\r")
        assert proc.wait() == 0
    finally:
        proc.close()
