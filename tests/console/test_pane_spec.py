# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import sys
from pathlib import Path

import pytest

from hammunition.console.guard import Refused
from hammunition.console.pane import RUNNER, build_pane_spec, read_exit_status


def test_the_command_is_the_runner_around_the_checked_argv() -> None:
    spec = build_pane_spec(
        ["hammunition", "install", "station"], "/tmp/s/status", {"PATH": "/bin", "TERM": "xterm"}
    )
    assert spec.command == [
        sys.executable,
        str(RUNNER),
        "/tmp/s/status",
        "--",
        "hammunition",
        "install",
        "station",
    ]
    assert RUNNER.exists()


def test_the_consent_environment_never_reaches_the_child() -> None:
    env = {"PATH": "/bin", "HAMMUNITION_ACCEPT_RF_RESEARCH": "1", "X_CONSENT": "1"}
    spec = build_pane_spec(["hammunition", "install", "station"], "/s", env)
    assert "HAMMUNITION_ACCEPT_RF_RESEARCH" not in spec.env and "X_CONSENT" not in spec.env
    assert spec.env["PATH"] == "/bin"


@pytest.mark.parametrize(
    "bad",
    [
        ["hammunition", "install", "x", "--yes"],
        ["hammunition", "install", "-y"],
        ["hammunition", "services", "start", "gpsd"],
        ["rm", "-rf", "/"],
    ],
)
def test_a_command_the_guard_refuses_never_becomes_a_pane(bad: list[str]) -> None:
    with pytest.raises(Refused):
        build_pane_spec(bad, "/s", {})


def test_read_exit_status(tmp_path: Path) -> None:
    ok = tmp_path / "a"
    ok.write_text("3\n")
    assert read_exit_status(str(ok)) == 3
    assert read_exit_status(str(tmp_path / "missing")) is None
    bad = tmp_path / "b"
    bad.write_text("three")
    assert read_exit_status(str(bad)) is None
