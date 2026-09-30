# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition maps comaps``: the per-user state CoMaps needs, then CoMaps.  D-069.

The licence acceptance CoMaps asks for on first start, written only when the
operator's settings have no answer; and a link in CoMaps' own map directory
for each map ``comaps-maps`` installed. Nothing is launched: ``execve`` is
replaced, and the settings and maps are the test's own directories.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

import pytest

from hammunition.comaps_launch import (
    EULA_LINE,
    data_dir,
    ensure_eula,
    link_maps,
    settings_path,
)

cli = importlib.import_module("hammunition.cli.main")


def test_the_settings_and_data_follow_xdg(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path / "c"), "XDG_DATA_HOME": str(tmp_path / "d")}
    assert settings_path(env) == tmp_path / "c" / "CoMaps" / "settings.ini"
    assert data_dir(env) == tmp_path / "d" / "CoMaps"
    assert settings_path({}, home=tmp_path) == tmp_path / ".config" / "CoMaps" / "settings.ini"
    assert data_dir({}, home=tmp_path) == tmp_path / ".local" / "share" / "CoMaps"


def test_the_eula_line_is_added_only_when_the_key_is_absent() -> None:
    assert ensure_eula("") == f"{EULA_LINE}\n"
    assert ensure_eula("Units=Metric") == f"Units=Metric\n{EULA_LINE}\n"
    kept = "DeveloperMode=false\nUnits=Metric\n"
    assert ensure_eula(kept) == kept + f"{EULA_LINE}\n"
    # CoMaps VERIFYs every key is unique, so a second line would crash it;
    # an operator's own answer, whichever it is, is theirs.
    for answered in ("EulaAccepted=true\n", "EulaAccepted=false\nUnits=Metric\n"):
        assert ensure_eula(answered) == answered


# -- the map links -------------------------------------------------------------


def _installed(tmp_path: Path) -> Path:
    root = tmp_path / "prefix" / "share" / "hammunition" / "data" / "comaps-maps"
    (root / "260830").mkdir(parents=True)
    (root / "260830" / "US_Vermont.mwm").write_bytes(b"vt")
    (root / "260830" / "US_Delaware.mwm").write_bytes(b"de")
    return root


def test_each_installed_map_is_linked_into_its_version_directory(tmp_path: Path) -> None:
    installed = _installed(tmp_path)
    writable = tmp_path / "home" / "CoMaps"
    notes = link_maps(installed, writable)
    link = writable / "260830" / "US_Vermont.mwm"
    assert link.is_symlink() and link.resolve() == (installed / "260830" / "US_Vermont.mwm")
    assert (writable / "260830" / "US_Delaware.mwm").read_bytes() == b"de"
    assert any("2 map(s)" in n for n in notes)
    # Idempotent: a second run changes nothing and says so.
    again = link_maps(installed, writable)
    assert any("0 new" in n or "already" in n for n in again)


def test_a_map_the_operator_downloaded_in_the_app_is_left(tmp_path: Path) -> None:
    installed = _installed(tmp_path)
    writable = tmp_path / "home" / "CoMaps"
    (writable / "260830").mkdir(parents=True)
    own = writable / "260830" / "US_Vermont.mwm"
    own.write_bytes(b"downloaded in CoMaps")
    notes = link_maps(installed, writable)
    assert own.read_bytes() == b"downloaded in CoMaps" and not own.is_symlink()
    assert any("US_Vermont.mwm" in n and "left" in n for n in notes)


def test_a_link_to_a_map_no_longer_installed_is_removed_and_no_other(tmp_path: Path) -> None:
    installed = _installed(tmp_path)
    writable = tmp_path / "home" / "CoMaps"
    link_maps(installed, writable)
    (installed / "260830" / "US_Delaware.mwm").unlink()
    elsewhere = writable / "260830" / "Other.mwm"
    elsewhere.symlink_to(tmp_path / "nowhere.mwm")  # not ours: pointing outside our data
    link_maps(installed, writable)
    assert not os.path.lexists(writable / "260830" / "US_Delaware.mwm")
    assert elsewhere.is_symlink()


def test_no_installed_maps_links_nothing_and_says_so(tmp_path: Path) -> None:
    notes = link_maps(tmp_path / "absent", tmp_path / "home" / "CoMaps")
    assert any("no CoMaps maps are installed" in n for n in notes)


# -- the command ------------------------------------------------------------------


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    binary = prefix / "bin" / "CoMaps"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setattr(cli, "DEFAULT_PREFIX", prefix)
    _installed(tmp_path)
    started: dict[str, Any] = {}

    def execve(path: str, argv: list[str], env: dict[str, str]) -> None:
        started.update(path=path, argv=argv, env=env)
        raise SystemExit(0)

    monkeypatch.setattr(cli.os, "execve", execve)
    return started


def test_the_command_prepares_then_starts_comaps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    started = _env(monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["maps", "comaps"])
    settings = tmp_path / "config" / "CoMaps" / "settings.ini"
    assert settings.read_text() == f"{EULA_LINE}\n"
    assert (settings.stat().st_mode & 0o777) == 0o600
    assert started["path"] == str(tmp_path / "prefix" / "bin" / "CoMaps")
    env = started["env"]
    assert env["MWM_WRITABLE_DIR"] == str(tmp_path / "data" / "CoMaps")
    assert env["MWM_RESOURCES_DIR"] == str(tmp_path / "prefix" / "share" / "comaps" / "data")
    assert (tmp_path / "data" / "CoMaps" / "260830" / "US_Vermont.mwm").is_symlink()
    assert "licence" in capsys.readouterr().err


def test_configure_only_does_not_start_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    started = _env(monkeypatch, tmp_path)
    assert cli.main(["maps", "comaps", "--configure-only"]) == 0
    assert not started


def test_a_symlinked_settings_file_is_refused_and_comaps_not_started(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    started = _env(monkeypatch, tmp_path)
    settings = tmp_path / "config" / "CoMaps" / "settings.ini"
    settings.parent.mkdir(parents=True)
    settings.symlink_to(tmp_path / "elsewhere.ini")
    assert cli.main(["maps", "comaps"]) == cli.EXIT_FAILED
    assert not started
    assert "symbolic link" in capsys.readouterr().err


def test_root_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    assert cli.main(["maps", "comaps"]) == cli.EXIT_FAILED
    assert "not as root" in capsys.readouterr().err


def test_a_missing_comaps_names_the_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    started = _env(monkeypatch, tmp_path)
    (tmp_path / "prefix" / "bin" / "CoMaps").unlink()
    assert cli.main(["maps", "comaps"]) == cli.EXIT_FAILED
    assert not started
    assert "hammunition install comaps" in capsys.readouterr().err
