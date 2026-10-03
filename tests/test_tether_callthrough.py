# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition maps gps-tether`` calls the installed program when there is one.

The tether is its own project now (hammunition-gps-tether); the engine's verb
runs the installed program and says where from, and where it is not installed
refuses with the install command; the engine carries no copy.  D-071 note,
2026-10-02.
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
    monkeypatch.setattr(cli, "installed_tether", lambda: ([PROGRAM], PROGRAM))
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
    # the tree form: env, PYTHONPATH, python, -m, then the options

    err = capsys.readouterr().err
    assert PROGRAM in err and "hammunition-gps-tether" in err


def test_no_options_means_no_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _record(monkeypatch)
    monkeypatch.setattr(cli, "installed_tether", lambda: ([PROGRAM], PROGRAM))
    with pytest.raises(Exec):
        cli.main(["maps", "gps-tether"])
    assert seen == [(PROGRAM, [PROGRAM])]


def test_the_position_port_and_socket_options_pass_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record(monkeypatch)
    monkeypatch.setattr(cli, "installed_tether", lambda: ([PROGRAM], PROGRAM))
    with pytest.raises(Exec):
        cli.main(["maps", "gps-tether", "--position-port", "10120", "--nmea-socket", "/x/n.sock"])
    assert seen[0][1] == [PROGRAM, "--position-port", "10120", "--nmea-socket", "/x/n.sock"]


def test_root_is_refused_before_anything_is_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _record(monkeypatch)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli, "installed_tether", lambda: ([PROGRAM], PROGRAM))
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_FAILED
    assert seen == []
    assert "not as root" in capsys.readouterr().err


def test_without_the_program_the_verb_refuses_and_names_the_install_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _record(monkeypatch)
    monkeypatch.setattr(cli, "installed_tether", lambda: None)
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_FAILED
    assert seen == []
    err = capsys.readouterr().err
    assert "hammunition install gps-tether" in err and "not installed" in err


def test_the_installed_program_is_really_run_and_its_exit_follows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """A script stands in for the installed program: the real execv, no fake."""
    import subprocess
    import sys
    from pathlib import Path

    directory = Path(str(tmp_path)) / "bin"
    program = directory / "hammunition-gps-tether"
    _executable(program)
    program.write_text('#!/bin/sh\necho "ran: $*"\nexit 7\n')
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; os.geteuid = lambda: 1000  # also true under unshare -r\n"
            # A tether installed on the host (its tree under /usr/local/share)
            # is found before the PATH; point the lookup at an empty place so
            # the host cannot change the result.
            "import importlib; from pathlib import Path\n"
            "m = importlib.import_module('hammunition.cli.main')\n"
            "m.TETHER_TREE = Path(sys.argv[1]); m.main(sys.argv[2:])",
            str(directory / "no-such-tree"),
            "maps",
            "gps-tether",
            "--port",
            "10112",
        ],
        env={
            "PATH": str(directory),
            "HOME": str(tmp_path),
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 7
    assert "ran: --port 10112" in result.stdout


def _executable(path: object) -> None:
    import stat
    from pathlib import Path

    program = Path(str(path))
    program.parent.mkdir(parents=True, exist_ok=True)
    program.write_text("#!/bin/sh\n")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)


def test_the_catalog_units_tree_is_run_in_place_with_the_archives_python(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    from pathlib import Path

    tree = Path(str(tmp_path)) / "gps-tether"
    (tree / "src" / "hammunition_gps_tether").mkdir(parents=True)
    (tree / "src" / "hammunition_gps_tether" / "__main__.py").write_text("")
    monkeypatch.setattr(cli, "TETHER_TREE", tree)
    monkeypatch.setenv("PATH", "/nonexistent-dir")
    found = cli.installed_tether()
    assert found == (
        [
            "/usr/bin/env",
            f"PYTHONPATH={tree / 'src'}",
            "/usr/bin/python3",
            "-P",
            "-m",
            "hammunition_gps_tether",
        ],
        str(tree),
    )


def test_a_tree_without_the_entry_point_is_not_the_tether(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    from pathlib import Path

    tree = Path(str(tmp_path)) / "gps-tether"
    (tree / "src").mkdir(parents=True)  # a half-extracted tree
    monkeypatch.setattr(cli, "TETHER_TREE", tree)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/nonexistent-dir")
    assert cli.installed_tether() is None


def test_a_program_on_the_path_is_found_when_there_is_no_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    from pathlib import Path

    directory = Path(str(tmp_path)) / "bin"
    _executable(directory / "hammunition-gps-tether")
    monkeypatch.setattr(cli, "TETHER_TREE", Path(str(tmp_path)) / "no-tree")
    monkeypatch.setenv("PATH", str(directory))
    program = str(directory / "hammunition-gps-tether")
    assert cli.installed_tether() == ([program], program)
    monkeypatch.setenv("PATH", "/nonexistent-dir")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.installed_tether() is None


def test_the_operators_local_bin_is_searched_when_the_path_lacks_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """A menu entry started by Plasma has no ~/.local/bin on its PATH (issue #145)."""
    from pathlib import Path

    home = Path(str(tmp_path))
    _executable(home / ".local" / "bin" / "hammunition-gps-tether")
    monkeypatch.setattr(cli, "TETHER_TREE", home / "no-tree")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/nonexistent-dir")
    program = str(home / ".local" / "bin" / "hammunition-gps-tether")
    assert cli.installed_tether() == ([program], program)


def test_a_program_that_cannot_be_run_is_one_error_line_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def execv(path: str, argv: list[str]) -> NoReturn:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "execv", execv)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(cli, "installed_tether", lambda: ([PROGRAM], PROGRAM))
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_FAILED
    err = capsys.readouterr().err
    assert "cannot run" in err and PROGRAM in err and "Permission denied" in err


def test_the_tree_form_passes_the_options_after_the_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record(monkeypatch)
    prefix = [
        "/usr/bin/env",
        "PYTHONPATH=/t/src",
        "/usr/bin/python3",
        "-m",
        "hammunition_gps_tether",
    ]
    monkeypatch.setattr(cli, "installed_tether", lambda: (prefix, "/t"))
    with pytest.raises(Exec):
        cli.main(["maps", "gps-tether", "--port", "10112"])
    assert seen == [("/usr/bin/env", [*prefix, "--port", "10112"])]
