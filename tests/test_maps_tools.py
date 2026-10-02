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


@pytest.fixture(autouse=True)
def _no_installed_tether(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests are about the engine's own copy; a developer machine that has
    hammunition-gps-tether installed must not turn them into a call-through."""
    monkeypatch.setattr(cli, "installed_tether", lambda: None)


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
    # Never the real home's repeater overlays (D-064): `maps qmapshack` looks there.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
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
        gpsd = kwargs.get("gpsd", tether.GPSD)
        calls.append("serve" if gpsd == tether.GPSD else f"serve gpsd {gpsd}")
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
    assert calls == ["listen 10110", "listen 10111", "serve", "closed", "closed"]
    assert seen == [], "no socat, no gpspipe: nothing is executed"
    out = capsys.readouterr().out
    assert "host 127.0.0.1, port 10110" in out
    assert "http://127.0.0.1:10111/position" in out


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


def test_gps_tether_takes_another_port_and_a_remote_gpsd(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    calls = _tether_calls(monkeypatch, fail=KeyboardInterrupt())
    argv = ["maps", "gps-tether", "--port", "10112", "--gpsd", "[2001:db8::7]:3000"]
    assert cli.main(argv) == cli.EXIT_OK
    assert calls == [
        "listen 10112",
        "listen 10111",
        "serve gpsd ('2001:db8::7', 3000)",
        "closed",
        "closed",
    ]
    out = capsys.readouterr().out
    assert "host 127.0.0.1, port 10112" in out
    assert "gpsd at [2001:db8::7] port 3000" in out


@pytest.mark.parametrize(
    ("argv", "words"),
    [
        (["--port", "1023"], "--port 1023"),
        (["--port", "65536"], "--port 65536"),
        (["--port", "ten"], "--port ten"),
        (["--gpsd", "::1"], "in brackets"),
        (["--gpsd", "pi.local:0"], "1 to 65535"),
        (["--gpsd", ""], "needs a host"),
        (["--position-port", "80"], "--position-port 80"),
        (["--port", "10111"], "are the same port"),
    ],
)
def test_gps_tether_refuses_a_bad_option_by_name_and_opens_nothing(
    argv: list[str],
    words: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    calls = _tether_calls(monkeypatch)
    assert cli.main(["maps", "gps-tether", *argv]) == cli.EXIT_FAILED
    assert calls == []
    assert words in capsys.readouterr().err


def test_gps_tether_reaches_a_fake_gpsd_through_the_gpsd_option(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole command, end to end: a fake gpsd on a random loopback port
    named with --gpsd, the tether on a spare --port, a real client."""
    import socket
    import threading
    import time

    import hammunition.gps_tether as tether
    from test_gps_tether import FIX_3D, FakeGpsd, _json

    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    gpsd = FakeGpsd(_json({"class": "VERSION"}, FIX_3D), repeat=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    stop = threading.Event()
    real_serve = tether.serve
    bound: list[tuple[str, int]] = []

    def serve(listener: socket.socket, **kwargs: object) -> None:
        bound.append(listener.getsockname())
        real_serve(listener, stop=stop, poll=0.02, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(tether, "serve", serve)
    argv = ["maps", "gps-tether", "--gpsd", f"127.0.0.1:{gpsd.address[1]}", "--port", str(port)]
    result: list[int] = []
    thread = threading.Thread(target=lambda: result.append(cli.main(argv)), daemon=True)
    thread.start()
    try:
        for _ in range(250):
            if bound:
                break
            time.sleep(0.02)
        assert bound == [("127.0.0.1", port)], "still loopback only"
        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            assert client.makefile("rb").readline().startswith(b"$GPRMC,140509.25,A,")
    finally:
        stop.set()
        thread.join(timeout=5)
        gpsd.close()
    assert result == [cli.EXIT_OK]
    assert gpsd.received == [tether.WATCH]
    assert f"gpsd at 127.0.0.1 port {gpsd.address[1]}" in capsys.readouterr().out


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


@pytest.mark.parametrize(
    "options",
    [["--gpsd", "192.0.2.10:3000", "--port", "10111"], ["--port", "80"], ["--gpsd", "::1"]],
)
def test_gps_tether_json_is_one_refusal_whatever_the_options(
    options: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The options change nothing about --json: the same one error document,
    naming no option, and nothing opened (D-059)."""
    import json

    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    calls = _tether_calls(monkeypatch)
    assert cli.main(["maps", "gps-tether", *options, "--json"]) == cli.EXIT_UNPLANNABLE
    out = capsys.readouterr().out
    doc = json.loads(out)  # the whole of stdout is one document
    assert set(doc) == {"schema", "kind", "engine", "command", "exit_code", "message"}
    assert doc["kind"] == "error" and doc["command"] == "maps gps-tether"
    assert "--gpsd" not in doc["message"] and "--port" not in doc["message"]
    assert calls == []


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
    assert (
        f"mapPath={data}/osm-garmin, {data}/dem-qmapshack/contours, {data}/ustopo-qmapshack\n"
        in canvas
    )
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
        f"mapPath={data}/osm-garmin, {data}/dem-qmapshack/contours, {data}/ustopo-qmapshack\n"
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


# ---------------------------------------------------------------- the GeoClue socket (D-069)


def _socket_calls(
    monkeypatch: pytest.MonkeyPatch, *, unix_fails: BaseException | None = None
) -> list[str]:
    """Stand-ins for both listeners, the server and the socket's removal."""
    import socket

    import hammunition.gps_tether as tether

    calls: list[str] = []

    class Listener:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            calls.append(f"closed {self.name}")

    def listen(port: int = tether.PORT) -> socket.socket:
        calls.append(f"listen {port}")
        return Listener(str(port))  # type: ignore[return-value]

    def listen_unix(path: str, **kwargs: object) -> tuple[socket.socket, tuple[int, int]]:
        calls.append(f"listen_unix {path}")
        if unix_fails is not None:
            raise unix_fails
        return Listener("unix"), (1, 2)  # type: ignore[return-value]

    def close_unix(listener: object, path: str, identity: tuple[int, int]) -> None:
        calls.append(f"close_unix {path} {identity}")

    def serve(listener: object, **kwargs: object) -> None:
        calls.append("serve with unix" if kwargs.get("unix") is not None else "serve")
        raise KeyboardInterrupt

    monkeypatch.setattr(tether, "listen", listen)
    monkeypatch.setattr(tether, "listen_unix", listen_unix)
    monkeypatch.setattr(tether, "close_unix", close_unix)
    monkeypatch.setattr(tether, "serve", serve)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    return calls


def _our_dropin() -> None:
    from hammunition import geoclue

    Path(geoclue.DROPIN).parent.mkdir(parents=True)
    Path(geoclue.DROPIN).write_text(geoclue.dropin_content())


def test_without_the_geoclue_files_no_socket_is_served(
    monkeypatch: pytest.MonkeyPatch, geoclue_files: Path
) -> None:
    calls = _socket_calls(monkeypatch)
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_OK
    assert not any("unix" in call for call in calls)


def test_with_the_geoclue_files_the_socket_is_served_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], geoclue_files: Path
) -> None:
    """The launcher runs `hammunition maps gps-tether` with no option; the
    drop-in's presence is what turns the socket on, so the menu entry needs no
    second form."""
    from hammunition import geoclue

    _our_dropin()
    calls = _socket_calls(monkeypatch)
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_OK
    assert calls == [
        "listen 10110",
        "listen 10111",
        f"listen_unix {geoclue.SOCKET}",
        "serve with unix",
        "closed 10110",
        "closed 10111",
        f"close_unix {geoclue.SOCKET} (1, 2)",
    ]
    assert geoclue.SOCKET in capsys.readouterr().out


def test_no_nmea_socket_leaves_it_off_with_the_files_in_place(
    monkeypatch: pytest.MonkeyPatch, geoclue_files: Path
) -> None:
    _our_dropin()
    calls = _socket_calls(monkeypatch)
    assert cli.main(["maps", "gps-tether", "--no-nmea-socket"]) == cli.EXIT_OK
    assert not any("unix" in call for call in calls)


def test_an_explicit_socket_is_served_without_the_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _socket_calls(monkeypatch)
    path = str(tmp_path / "n.sock")
    assert cli.main(["maps", "gps-tether", "--nmea-socket", path]) == cli.EXIT_OK
    assert f"listen_unix {path}" in calls and "serve with unix" in calls


def test_an_explicit_socket_that_cannot_be_made_stops_the_tether(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    calls = _socket_calls(monkeypatch, unix_fails=FileNotFoundError(2, "No such file or directory"))
    path = str(tmp_path / "missing" / "n.sock")
    assert cli.main(["maps", "gps-tether", "--nmea-socket", path]) == cli.EXIT_FAILED
    assert "serve" not in " ".join(calls)
    assert "closed 10110" in calls and "closed 10111" in calls
    assert path in capsys.readouterr().err


def test_the_default_socket_failing_is_a_note_and_tcp_still_serves(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], geoclue_files: Path
) -> None:
    """After a reboot before systemd-tmpfiles ran, say: QMapShack keeps working."""
    _our_dropin()
    calls = _socket_calls(monkeypatch, unix_fails=FileNotFoundError(2, "No such file or directory"))
    assert cli.main(["maps", "gps-tether"]) == cli.EXIT_OK
    assert "serve" in calls
    err = capsys.readouterr().err
    assert "systemd-tmpfiles --create" in err and "GeoClue" in err


def test_both_socket_options_at_once_are_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _socket_calls(monkeypatch)
    argv = ["maps", "gps-tether", "--nmea-socket", "/x/n.sock", "--no-nmea-socket"]
    assert cli.main(argv) == cli.EXIT_FAILED
    assert calls == []
    assert "--no-nmea-socket" in capsys.readouterr().err
