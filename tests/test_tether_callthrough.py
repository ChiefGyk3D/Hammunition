# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition maps gps-tether`` calls the installed program when there is one.

The tether is its own project now (hammunition-gps-tether); the engine's verb
runs the installed program and says where from, and keeps working from the
engine's own module, with a deprecation note, where it is not installed.  D-071
note, 2026-10-02.
"""

from __future__ import annotations

import importlib
import os
from typing import NoReturn

import pytest

cli = importlib.import_module("hammunition.cli.main")

PROGRAM = "/usr/local/bin/hammunition-gps-tether"


class Exec(Exception):
    """Raised in place of replacing the test process."""


def _record(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    seen: list[tuple[str, list[str]]] = []

    def execv(path: str, argv: list[str]) -> NoReturn:
        seen.append((path, argv))
        raise Exec

    monkeypatch.setattr(os, "execv", execv)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    return seen


def test_the_installed_program_is_run_with_the_options_given(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _record(monkeypatch)
    monkeypatch.setattr(cli, "installed_tether", lambda: PROGRAM)
    argv = [
        "maps",
        "gps-tether",
        "--gpsd",
        "192.0.2.10:3000",
        "--port",
        "10112",
        "--no-nmea-socket",
    ]
    with pytest.raises(Exec):
        cli.main(argv)
    assert seen == [
        (
            PROGRAM,
            [PROGRAM, "--gpsd", "192.0.2.10:3000", "--port", "10112", "--no-nmea-socket"],
        )
    ]
    err = capsys.readouterr().err
    assert PROGRAM in err and "hammunition-gps-tether" in err


def test_no_options_means_no_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _record(monkeypatch)
    monkeypatch.setattr(cli, "installed_tether", lambda: PROGRAM)
    with pytest.raises(Exec):
        cli.main(["maps", "gps-tether"])
    assert seen == [(PROGRAM, [PROGRAM])]


def test_the_position_port_and_socket_options_pass_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record(monkeypatch)
    monkeypatch.setattr(cli, "installed_tether", lambda: PROGRAM)
    with pytest.raises(Exec):
        cli.main(["maps", "gps-tether", "--position-port", "10120", "--nmea-socket", "/x/n.sock"])
    assert seen[0][1] == [PROGRAM, "--position-port", "10120", "--nmea-socket", "/x/n.sock"]


def test_root_is_refused_before_anything_is_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _record(monkeypatch)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli, "installed_tether", lambda: PROGRAM)
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_FAILED
    assert seen == []
    assert "not as root" in capsys.readouterr().err


def test_without_the_program_the_engines_own_copy_runs_with_a_deprecation_note(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hammunition.gps_tether as tether

    seen = _record(monkeypatch)
    monkeypatch.setattr(cli, "installed_tether", lambda: None)
    monkeypatch.setattr(tether, "listen", lambda port=tether.PORT: _Closer())
    monkeypatch.setattr(tether, "serve", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_OK
    assert seen == []
    err = capsys.readouterr().err
    assert "hammunition install gps-tether" in err
    assert "will go away" in err


class _Closer:
    def close(self) -> None:
        pass


def test_installed_tether_finds_it_on_the_path_and_nowhere_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    import stat
    from pathlib import Path

    directory = Path(str(tmp_path))
    program = directory / "hammunition-gps-tether"
    program.write_text("#!/bin/sh\n")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(directory))
    assert cli.installed_tether() == str(program)
    monkeypatch.setenv("PATH", "/nonexistent-dir")
    assert cli.installed_tether() is None


def test_installed_tether_also_looks_in_the_operators_local_bin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """A menu entry started by Plasma has no ~/.local/bin on its PATH, which is
    where the venv's wrapper lands (issue #145's lesson)."""
    import stat
    from pathlib import Path

    home = Path(str(tmp_path))
    program = home / ".local" / "bin" / "hammunition-gps-tether"
    program.parent.mkdir(parents=True)
    program.write_text("#!/bin/sh\n")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/nonexistent-dir")
    assert cli.installed_tether() == str(program)
