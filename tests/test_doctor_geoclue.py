# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`doctor` on GeoClue's tether socket and its agent.  D-069."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition import geoclue
from hammunition.doctor import Check, run_checks
from hammunition.geoclue import GeoClueState
from test_doctor import HEALTHY


def _geoclue(state: GeoClueState | None) -> list[Check]:
    checks = run_checks(**{**HEALTHY, "geoclue_state": state})  # type: ignore[arg-type]
    return [c for c in checks if c.name.startswith("geoclue")]


def _state(**fields: object) -> GeoClueState:
    base: dict[str, object] = {
        "dropin_ours": True,
        "tmpfiles_ours": True,
        "directory": "current",
        "agent": True,
    }
    return GeoClueState(**{**base, **fields})  # type: ignore[arg-type]


def test_no_geoclue_says_nothing() -> None:
    assert _geoclue(None) == []


def test_everything_in_place_is_ok_twice() -> None:
    checks = _geoclue(_state())
    assert [(c.name, c.status) for c in checks] == [("geoclue", "ok"), ("geoclue agent", "ok")]
    assert "nmea.sock" in checks[0].detail


def test_not_set_up_is_information_naming_apply() -> None:
    checks = _geoclue(_state(dropin_ours=False, tmpfiles_ours=False, directory="absent"))
    assert checks[0].status == "info"
    assert "hammunition hardware apply" in checks[0].detail


def test_a_missing_directory_warns_with_the_tmpfiles_command() -> None:
    check = _geoclue(_state(directory="absent"))[0]
    assert check.status == "warn"
    assert check.fix == f"sudo systemd-tmpfiles --create {geoclue.TMPFILES}"


def test_a_wrong_directory_names_what_is_wrong() -> None:
    check = _geoclue(_state(directory="mode 0755, not 2750"))[0]
    assert check.status == "warn" and "mode 0755" in check.detail
    assert check.fix is not None and "systemd-tmpfiles" in check.fix


def test_one_file_without_the_other_warns_naming_apply() -> None:
    check = _geoclue(_state(tmpfiles_ours=False))[0]
    assert check.status == "warn"
    assert check.fix is not None and "hardware apply" in check.fix


def test_no_agent_warns_and_says_what_comaps_will_see() -> None:
    agent = _geoclue(_state(agent=False))[1]
    assert agent.status == "warn"
    assert "busctl --user list" in agent.detail and "25 s" in agent.detail
    assert agent.fix is not None and "geoclue-demo-agent.desktop" in agent.fix


def test_an_agent_not_asked_is_information() -> None:
    agent = _geoclue(_state(agent=None))[1]
    assert agent.status == "info" and "not checked" in agent.detail


def test_the_cli_reads_busctl_as_the_user_and_never_as_root(
    geoclue_files: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real reading through a fake `busctl` on PATH: `--user list`, nothing else,
    and not asked at all under root, whose bus is not the session's."""
    import argparse
    import importlib
    import os

    from fake_tools import calls, install_fakes

    cli = importlib.import_module("hammunition.cli.main")
    log = install_fakes(
        monkeypatch, tmp_path / "bin", {"busctl": f"echo '{geoclue.DEMO_AGENT} 42 agent op'"}
    )
    args = argparse.Namespace(user="nobody")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    state = cli._geoclue_state_for_doctor(args)
    assert state is not None and state.agent is True
    assert [command for _, command in calls(log)] == ["busctl --user list --no-pager"]
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    state = cli._geoclue_state_for_doctor(args)
    assert state is not None and state.agent is None
    assert len(calls(log)) == 1
