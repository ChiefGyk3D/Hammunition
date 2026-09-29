# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition maps qmapshack`` and ``hammunition maps gps-tether``.  D-061."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import NoReturn

import pytest

cli = importlib.import_module("hammunition.cli.main")


class Exec(Exception):
    """Raised in place of replacing the test process."""


def _record_exec(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    seen: list[list[str]] = []

    def execvp(file: str, argv: list[str]) -> NoReturn:
        seen.append([file, *argv])
        raise Exec

    monkeypatch.setattr(os, "execvp", execvp)
    return seen


def _as(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, euid: int = 1000) -> Path:
    monkeypatch.setattr(os, "geteuid", lambda: euid)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "QLandkarte" / "QMapShack.conf"


def test_qmapshack_adds_our_directories_keeps_the_mode_and_starts_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = _as(monkeypatch, tmp_path)
    conf.parent.mkdir(parents=True)
    conf.write_text("[Units]\ntype=metric\n")
    conf.chmod(0o600)
    seen = _record_exec(monkeypatch)
    with pytest.raises(Exec):
        cli.main(["maps", "qmapshack"])
    assert seen == [["qmapshack", "qmapshack"]]
    text = conf.read_text()
    assert text.startswith("[Units]\ntype=metric\n")
    assert "mapPath=/usr/local/share/hammunition/data/osm-garmin, " in text
    assert "routino\\paths=/usr/local/share/hammunition/data/osm-routino" in text
    assert conf.stat().st_mode & 0o777 == 0o600


def test_configure_only_does_not_start_qmapshack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = _as(monkeypatch, tmp_path)
    seen = _record_exec(monkeypatch)
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_OK
    assert seen == []
    assert "demPaths=/usr/local/share/hammunition/data/dem-qmapshack/dem" in conf.read_text()


def test_a_config_it_cannot_read_is_left_alone_and_qmapshack_not_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conf = _as(monkeypatch, tmp_path)
    conf.parent.mkdir(parents=True)
    conf.write_text("[Canvas]\nmapPath=@Variant(\\0)\n")
    seen = _record_exec(monkeypatch)
    assert cli.main(["maps", "qmapshack"]) == cli.EXIT_FAILED
    assert seen == []
    assert conf.read_text() == "[Canvas]\nmapPath=@Variant(\\0)\n"
    assert "was not started" in capsys.readouterr().err


def test_qmapshack_refuses_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conf = _as(monkeypatch, tmp_path, euid=0)
    seen = _record_exec(monkeypatch)
    assert cli.main(["maps", "qmapshack"]) == cli.EXIT_FAILED
    assert seen == [] and not conf.exists()


def _tether_calls(
    monkeypatch: pytest.MonkeyPatch, *, fail: BaseException | None = None
) -> list[str]:
    """Stand-ins for the listener and the server; no socket is opened."""
    import socket

    import hammunition.gps_tether as tether

    calls: list[str] = []

    class Listener:
        def close(self) -> None:
            calls.append("closed")

    def listen(port: int = tether.PORT) -> socket.socket:
        calls.append(f"listen {port}")
        if isinstance(fail, OSError):
            raise fail
        return Listener()  # type: ignore[return-value]

    def serve(listener: object, **kwargs: object) -> None:
        calls.append("serve")
        if fail is not None:
            raise fail

    monkeypatch.setattr(tether, "listen", listen)
    monkeypatch.setattr(tether, "serve", serve)
    return calls


def test_gps_tether_prints_where_to_connect_and_serves_until_ctrl_c(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    seen = _record_exec(monkeypatch)
    calls = _tether_calls(monkeypatch, fail=KeyboardInterrupt())
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_OK
    assert calls == ["listen 10110", "serve", "closed"]
    assert seen == [], "no socat, no gpspipe: nothing is executed"
    out = capsys.readouterr().out
    assert "host 127.0.0.1, port 10110" in out


def test_gps_tether_names_a_port_already_in_use(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import errno

    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    calls = _tether_calls(monkeypatch, fail=OSError(errno.EADDRINUSE, "Address already in use"))
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_FAILED
    assert calls == ["listen 10110"]
    err = capsys.readouterr().err
    assert "Address already in use" in err and "127.0.0.1 port 10110" in err


def test_gps_tether_refuses_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    calls = _tether_calls(monkeypatch)
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_FAILED
    assert calls == []
    assert "not as root" in capsys.readouterr().err


def test_a_symlink_in_place_of_the_config_is_refused_and_not_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conf = _as(monkeypatch, tmp_path)
    conf.parent.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere.conf"
    elsewhere.write_text("[Units]\ntype=metric\n")
    conf.symlink_to(elsewhere)
    seen = _record_exec(monkeypatch)
    assert cli.main(["maps", "qmapshack"]) == cli.EXIT_FAILED
    assert seen == []
    assert conf.is_symlink() and elsewhere.read_text() == "[Units]\ntype=metric\n"
    err = capsys.readouterr().err
    assert "symbolic link" in err and "was not started" in err


def test_a_config_that_is_not_a_regular_file_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = _as(monkeypatch, tmp_path)
    conf.mkdir(parents=True)
    seen = _record_exec(monkeypatch)
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_FAILED
    assert seen == [] and conf.is_dir()


def test_the_edit_is_a_rename_in_the_same_directory_and_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conf = _as(monkeypatch, tmp_path)
    conf.parent.mkdir(parents=True)
    conf.write_text("[Units]\ntype=metric\n")
    before = conf.stat().st_ino
    renames: list[tuple[str, str]] = []
    real_replace = os.replace

    def replace(src: str, dst: str) -> None:
        renames.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_OK
    ((src, dst),) = renames
    assert Path(src).parent == conf.parent and Path(dst) == conf
    assert conf.stat().st_ino != before, "rewritten in place rather than renamed over"
    assert sorted(p.name for p in conf.parent.iterdir()) == ["QMapShack.conf"]
    err = capsys.readouterr().err
    assert str(conf) in err, "the change is announced"
    assert "[General]" not in err, "nothing was moved, so no move is claimed"


def test_a_config_already_naming_our_directories_is_not_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = _as(monkeypatch, tmp_path)
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_OK
    first = conf.stat()
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_OK
    assert conf.stat().st_ino == first.st_ino and conf.stat().st_mtime_ns == first.st_mtime_ns


@pytest.mark.parametrize("verb", ["qmapshack", "gps-tether"])
def test_json_is_refused_with_one_error_document_and_nothing_runs(
    verb: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A launcher that execs a GUI or a server has no document to give (D-059)."""
    import json

    conf = _as(monkeypatch, tmp_path)
    seen = _record_exec(monkeypatch)
    assert cli.main(["maps", verb, "--json"]) == cli.EXIT_UNPLANNABLE
    doc = json.loads(capsys.readouterr().out)
    assert doc["kind"] == "error" and doc["command"] == f"maps {verb}"
    assert "no --json form" in doc["message"]
    assert seen == [] and not conf.exists()


def test_a_config_qt_wrote_with_empty_lists_is_edited_and_qmapshack_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``@Invalid()`` is Qt's empty list: the ordinary returning user (D-061)."""
    conf = _as(monkeypatch, tmp_path)
    conf.parent.mkdir(parents=True)
    conf.write_text("[Canvas]\ndemPaths=@Invalid()\nmapPath=@Invalid()\n")
    seen = _record_exec(monkeypatch)
    with pytest.raises(Exec):
        cli.main(["maps", "qmapshack"])
    assert seen == [["qmapshack", "qmapshack"]]
    assert "@Invalid()" not in conf.read_text()


def test_an_earlier_launchers_general_keys_are_moved_to_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bench, 2026-09-29: QMapShack reads the lists under [Canvas] only (D-061)."""
    data = "/usr/local/share/hammunition/data"
    conf = _as(monkeypatch, tmp_path)
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "[General]\n"
        f"mapPath={data}/osm-garmin, {data}/dem-qmapshack/contours\n"
        f"demPaths={data}/dem-qmapshack/dem\n"
        "\n"
        "[Canvas]\n"
        "mapPath=@Invalid()\n"
        "demPaths=@Invalid()\n"
    )
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_OK
    text = conf.read_text()
    general, canvas = text.split("[Canvas]\n")
    assert "mapPath" not in general and "demPaths" not in general
    assert f"mapPath={data}/osm-garmin, {data}/dem-qmapshack/contours\n" in canvas
    assert f"demPaths={data}/dem-qmapshack/dem\n" in canvas
    assert "moved from [General]" in capsys.readouterr().err


def test_an_unselected_routing_database_is_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bench, 2026-09-29: ``routino\\database=-1`` left the Database dropdown
    blank and routing silent, with the database loaded (D-061)."""
    data = "/usr/local/share/hammunition/data"
    conf = _as(monkeypatch, tmp_path)
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "[Canvas]\n"
        f"mapPath={data}/osm-garmin, {data}/dem-qmapshack/contours\n"
        f"demPaths={data}/dem-qmapshack/dem\n"
        "\n"
        "[Route]\n"
        f"routino\\paths={data}/osm-routino\n"
        "routino\\database=-1\n"
    )
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_OK
    text = conf.read_text()
    assert "routino\\database=0\n" in text and "=-1" not in text
    err = capsys.readouterr().err
    assert "Database" in err and "adding Hammunition" not in err


def test_a_fresh_config_selects_the_routing_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = _as(monkeypatch, tmp_path)
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == cli.EXIT_OK
    assert "routino\\database=0\n" in conf.read_text()
