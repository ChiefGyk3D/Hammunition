# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""capture_fixtures.py runs the engine; it must never do so where it could reach a real
operator's files (the 2026-10-03 incident, console issue #5)."""

import os
import subprocess
from pathlib import Path

import pytest

from . import capture_fixtures as cap
from .helpers import SRC_DIR


@pytest.fixture
def not_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)


def test_a_home_it_made_itself_is_accepted(not_root: None) -> None:
    with cap.capture_home() as home:
        cap.assert_safe_home(cap.capture_env(home))


def test_the_operators_real_home_is_refused(not_root: None) -> None:
    for real in cap._real_homes():
        with pytest.raises(cap.UnsafeHome):
            cap.assert_safe_home({"HOME": str(real)})


def test_an_unmarked_temporary_directory_is_refused(tmp_path: Path, not_root: None) -> None:
    with pytest.raises(cap.UnsafeHome, match="not created by capture_home"):
        cap.assert_safe_home({"HOME": str(tmp_path)})


def test_a_missing_home_is_refused(not_root: None) -> None:
    with pytest.raises(cap.UnsafeHome, match="not set"):
        cap.assert_safe_home({})


@pytest.mark.parametrize("variable", cap.OWNER_VARIABLES)
def test_a_variable_that_names_an_owner_is_refused(variable: str, not_root: None) -> None:
    with cap.capture_home() as home:
        env = {**cap.capture_env(home), variable: "someone"}
        with pytest.raises(cap.UnsafeHome, match=variable):
            cap.assert_safe_home(env)


def test_capture_env_drops_those_variables_and_the_consent_canary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in cap.OWNER_VARIABLES:
        monkeypatch.setenv(key, "someone")
    monkeypatch.setenv("HAMMUNITION_ACCEPT_RF_RESEARCH", "1")
    with cap.capture_home() as home:
        env = cap.capture_env(home)
    assert not set(cap.OWNER_VARIABLES) & set(env) and "HAMMUNITION_ACCEPT_RF_RESEARCH" not in env


def test_root_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with cap.capture_home() as home, pytest.raises(cap.UnsafeHome, match="root"):
        cap.assert_safe_home(cap.capture_env(home))


def test_run_refuses_before_it_spawns_anything(monkeypatch: pytest.MonkeyPatch) -> None:
    spawned: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: spawned.append(a))
    real = sorted(cap._real_homes())[0]
    with pytest.raises(cap.UnsafeHome):
        cap.run(["hammunition"], ["station", "show"], {"HOME": str(real)})
    assert spawned == []


def test_the_script_never_names_a_real_home_or_runs_outside_the_guard() -> None:
    """Every spawn goes through run(), and run() checks first."""
    text = (Path(cap.__file__)).read_text()
    assert text.count("subprocess.run(") == 1
    run_body = text.split("def run(", 1)[1].split("\ndef ", 1)[0]
    assert run_body.index("assert_safe_home(env)") < run_body.index("subprocess.run(")
    assert str(SRC_DIR.parents[0]) not in text
