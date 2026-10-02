# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition maps splat``: pointing SPLAT! at Hammunition's terrain
through ``~/.splat_path``.  D-061, amended 2026-10-02.

SPLAT reads the one line of ``~/.splat_path`` as its "directory path of last
resort" (its manual; measured: with or without the trailing slash). The
file is the operator's: written only when absent, never over another path.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from hammunition.splat_path import SplatPathError, ensure_splat_path

cli = importlib.import_module("hammunition.cli.main")

DIR = Path("/usr/local/share/hammunition/data/splat-sdf")


def test_an_absent_file_is_written_with_the_directory(tmp_path: Path) -> None:
    state = ensure_splat_path(tmp_path / ".splat_path", DIR)
    assert state == "written"
    path = tmp_path / ".splat_path"
    assert path.read_text() == f"{DIR}/\n"
    assert path.stat().st_mode & 0o777 == 0o644
    assert list(tmp_path.iterdir()) == [path], "no temporary left behind"


@pytest.mark.parametrize("line", [f"{DIR}/\n", f"{DIR}\n", f"{DIR}"])
def test_a_file_naming_the_directory_already_is_left_as_it_is(tmp_path: Path, line: str) -> None:
    path = tmp_path / ".splat_path"
    path.write_text(line)
    assert ensure_splat_path(path, DIR) == "already"
    assert path.read_text() == line


def test_another_directory_is_the_operator_s_and_is_left_alone(tmp_path: Path) -> None:
    path = tmp_path / ".splat_path"
    path.write_text("/opt/splat/sdf/\n")
    assert ensure_splat_path(path, DIR) == "other"
    assert path.read_text() == "/opt/splat/sdf/\n"


def test_a_symlink_or_a_directory_is_refused_and_nothing_changes(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.write_text("keep\n")
    path = tmp_path / ".splat_path"
    path.symlink_to(victim)
    with pytest.raises(SplatPathError, match="symbolic link"):
        ensure_splat_path(path, DIR)
    assert victim.read_text() == "keep\n"
    path.unlink()
    path.mkdir()
    with pytest.raises(SplatPathError, match="not a regular file"):
        ensure_splat_path(path, DIR)


def test_the_command_refuses_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert cli.main(["maps", "splat"]) == cli.EXIT_FAILED
    assert "per user" in capsys.readouterr().err


def test_the_command_writes_the_file_and_prints_the_signal_server_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("HOME", str(tmp_path))
    # Never the machine's own prefix: whether it holds terrain is not the test's.
    monkeypatch.setattr(cli, "DEFAULT_PREFIX", tmp_path / "prefix")
    assert cli.main(["maps", "splat"]) == cli.EXIT_OK
    out = capsys.readouterr()
    assert (tmp_path / ".splat_path").read_text().endswith("/data/splat-sdf/\n")
    assert "-sdf " in out.out and "/data/splat-sdf/" in out.out
    assert "no SPLAT terrain is installed yet" in out.err
    terrain = tmp_path / "prefix" / "share" / "hammunition" / "data" / "splat-sdf"
    terrain.mkdir(parents=True)
    (terrain / "0:1:359:0.sdf.bz2").write_bytes(b"sdf")
    assert cli.main(["maps", "splat"]) == cli.EXIT_OK
    again = capsys.readouterr()
    assert "already" in again.out and "no SPLAT terrain" not in again.err


def test_the_command_leaves_another_path_and_says_to_pass_d(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".splat_path").write_text("/opt/splat/sdf/\n")
    assert cli.main(["maps", "splat"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "/opt/splat/sdf/" in out and "-d " in out
    assert (tmp_path / ".splat_path").read_text() == "/opt/splat/sdf/\n"


def test_a_refusal_fails_the_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".splat_path").mkdir()
    assert cli.main(["maps", "splat"]) == cli.EXIT_FAILED
    assert "nothing was changed" in capsys.readouterr().err.lower()
