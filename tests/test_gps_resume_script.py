# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The script the resume unit runs as root after a suspend (issue #177).

Everything it touches is a fake: ``gpsdctl`` and ``systemctl`` are shell
scripts that record their argv, gpsd is a loopback server answering
``?DEVICES;``, and ``/dev`` is a temporary directory holding a ``gps0``
symlink to a ``ttyACM0`` file, exactly the shape gpsd's own udev rule makes.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from hammunition.hardware import gps_resume_script as script


class FakeGpsd:
    """A loopback gpsd: a VERSION banner, then one DEVICES reply per ``?DEVICES;``.

    ``answers`` is consumed one per connection: a list of paths is a reply,
    ``None`` is a gpsd that accepts and never answers.
    """

    def __init__(self, answers: list[list[str] | None]) -> None:
        self.answers = list(answers)
        self.asked = 0
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(4)
        self.port = self.server.getsockname()[1]
        self._stop = False
        self._held: list[socket.socket] = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while not self._stop:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            answer = self.answers.pop(0) if self.answers else []
            conn.sendall(b'{"class":"VERSION","release":"3.25","proto_major":3}\r\n')
            data = b""
            while b";" not in data:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk
            self.asked += 1
            if answer is None:
                self._held.append(conn)
                continue
            devices = [{"class": "DEVICE", "path": p, "driver": "u-blox"} for p in answer]
            reply = json.dumps({"class": "DEVICES", "devices": devices})
            conn.sendall(reply.encode() + b"\r\n")
            conn.close()

    def close(self) -> None:
        self._stop = True
        self.server.close()
        for conn in self._held:
            conn.close()


@pytest.fixture
def machine(tmp_path: Path) -> dict[str, Path]:
    dev = tmp_path / "dev"
    dev.mkdir()
    log = tmp_path / "ran.log"
    tools = {}
    for name, code in (("gpsdctl", 0), ("systemctl", 0)):
        tool = tmp_path / name
        tool.write_text(
            f'#!/bin/sh\necho "{name} $* GPSD_SOCKET=$GPSD_SOCKET" >> {log}\nexit {code}\n'
        )
        tool.chmod(0o755)
        tools[name] = tool
    control = tmp_path / "gpsd.sock"
    control.write_text("")
    return {"dev": dev, "log": log, "control": control, **tools}


def _receiver(dev: Path, number: int = 0, tty: str = "ttyACM0") -> None:
    (dev / tty).write_text("")
    (dev / f"gps{number}").symlink_to(tty)


@pytest.fixture
def gpsd() -> Iterator[list[FakeGpsd]]:
    made: list[FakeGpsd] = []
    yield made
    for server in made:
        server.close()


def _argv(m: dict[str, Path], server: FakeGpsd | None, timeout: float = 2.0) -> list[str]:
    port = server.port if server is not None else 9
    return [
        "--dev",
        str(m["dev"]),
        "--gpsdctl",
        str(m["gpsdctl"]),
        "--systemctl",
        str(m["systemctl"]),
        "--control-socket",
        str(m["control"]),
        "--gpsd-port",
        str(port),
        "--timeout",
        str(timeout),
    ]


def _ran(m: dict[str, Path]) -> list[str]:
    if not m["log"].exists():
        return []
    return m["log"].read_text().splitlines()


def test_no_gps_symlink_does_nothing_so_a_parked_receiver_stays_parked(
    machine: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    (machine["dev"] / "ttyACM0").write_text("")  # a tty, but no /dev/gpsN
    assert script.main(_argv(machine, None)) == 0
    assert _ran(machine) == []
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1 and "nothing to do" in out[0]


def test_a_receiver_gpsd_knows_by_its_tty_is_removed_and_added_by_that_path(
    machine: dict[str, Path], gpsd: list[FakeGpsd], capsys: pytest.CaptureFixture[str]
) -> None:
    """gpsdctl@ttyACM0 registers /dev/ttyACM0, so that is the path to hand back."""
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty]])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 0
    socket_env = f"GPSD_SOCKET={machine['control']}"
    assert _ran(machine) == [
        f"gpsdctl remove {tty} {socket_env}",
        f"gpsdctl add {tty} {socket_env}",
    ]
    out = capsys.readouterr().out.splitlines()
    assert any(line.startswith(f"gpsdctl remove {tty}") for line in out)
    assert any(line.startswith(f"gpsdctl add {tty}") for line in out)
    assert server.asked == 2


def test_a_receiver_gpsd_knows_by_its_gps_name_keeps_that_name(
    machine: dict[str, Path], gpsd: list[FakeGpsd]
) -> None:
    """DEVICES="/dev/gps0" in /etc/default/gpsd: re-adding the tty would give
    gpsd a second handle on the same port."""
    _receiver(machine["dev"])
    link = str(machine["dev"] / "gps0")
    server = FakeGpsd([[link], [link]])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 0
    assert [line.split()[:3] for line in _ran(machine)] == [
        ["gpsdctl", "remove", link],
        ["gpsdctl", "add", link],
    ]


def test_every_receiver_in_number_order(machine: dict[str, Path], gpsd: list[FakeGpsd]) -> None:
    _receiver(machine["dev"], 10, "ttyACM2")
    _receiver(machine["dev"], 2, "ttyUSB0")
    ttys = [str(machine["dev"] / "ttyUSB0"), str(machine["dev"] / "ttyACM2")]
    server = FakeGpsd([ttys, ttys])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 0
    assert [line.split()[1:3] for line in _ran(machine)] == [
        ["remove", ttys[0]],
        ["add", ttys[0]],
        ["remove", ttys[1]],
        ["add", ttys[1]],
    ]


def test_no_device_after_the_re_add_restarts_gpsd(
    machine: dict[str, Path], gpsd: list[FakeGpsd], capsys: pytest.CaptureFixture[str]
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], []])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 0
    assert _ran(machine)[-1].startswith("systemctl try-restart gpsd.service")
    assert "no device" in capsys.readouterr().out


def test_a_gpsd_that_does_not_answer_in_time_is_restarted(
    machine: dict[str, Path], gpsd: list[FakeGpsd], capsys: pytest.CaptureFixture[str]
) -> None:
    _receiver(machine["dev"])
    server = FakeGpsd([None, None])
    gpsd.append(server)
    assert script.main(_argv(machine, server, timeout=0.3)) == 0
    ran = _ran(machine)
    tty = str(machine["dev"] / "ttyACM0")
    # Not knowing what gpsd holds, the tty gpsdctl@ registers is cycled.
    assert [line.split()[:3] for line in ran[:2]] == [
        ["gpsdctl", "remove", tty],
        ["gpsdctl", "add", tty],
    ]
    assert ran[-1].startswith("systemctl try-restart gpsd.service")
    assert "no answer" in capsys.readouterr().out


def test_nothing_listening_counts_as_no_answer(machine: dict[str, Path]) -> None:
    _receiver(machine["dev"])
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    argv = _argv(machine, None)
    argv[argv.index("--gpsd-port") + 1] = str(port)
    assert script.main(argv) == 0
    assert _ran(machine)[-1].startswith("systemctl try-restart gpsd.service")


def test_a_failed_restart_fails_the_unit(machine: dict[str, Path], gpsd: list[FakeGpsd]) -> None:
    _receiver(machine["dev"])
    machine["systemctl"].write_text(f'#!/bin/sh\necho "systemctl $*" >> {machine["log"]}\nexit 1\n')
    server = FakeGpsd([[], []])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 1


def test_a_failing_gpsdctl_is_logged_and_the_check_still_runs(
    machine: dict[str, Path], gpsd: list[FakeGpsd], capsys: pytest.CaptureFixture[str]
) -> None:
    _receiver(machine["dev"])
    machine["gpsdctl"].write_text(
        f'#!/bin/sh\necho "gpsdctl $*" >> {machine["log"]}\necho "no gpsd" >&2\nexit 1\n'
    )
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty]])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 0
    out = capsys.readouterr().out
    assert "failed: no gpsd" in out
    assert server.asked == 2


def test_no_control_socket_means_no_gpsd_and_nothing_is_run(
    machine: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """gpsdctl add starts a gpsd of its own when none is listening; the unit
    must never leave one running outside systemd."""
    _receiver(machine["dev"])
    machine["control"].unlink()
    assert script.main(_argv(machine, None)) == 0
    assert _ran(machine) == []
    assert "gpsd is not running" in capsys.readouterr().out


def test_a_gps_symlink_pointing_outside_dev_is_skipped(
    machine: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path / "elsewhere"
    outside.write_text("")
    (machine["dev"] / "gps0").symlink_to(outside)
    assert script.main(_argv(machine, None)) == 0
    assert _ran(machine) == []
    out = capsys.readouterr().out
    assert "skipped" in out and "nothing to do" in out


def test_a_name_that_only_starts_with_gps_is_not_a_receiver(
    machine: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    (machine["dev"] / "ttyACM0").write_text("")
    (machine["dev"] / "gpsx").symlink_to("ttyACM0")
    (machine["dev"] / "gps0-old").symlink_to("ttyACM0")
    assert script.main(_argv(machine, None)) == 0
    assert _ran(machine) == []


def test_the_installed_file_runs_on_its_own(
    machine: dict[str, Path], gpsd: list[FakeGpsd], tmp_path: Path
) -> None:
    """What the unit runs is the composed file, under ``python3 -I``, with no
    Hammunition on its path: it must import nothing of ours."""
    from hammunition.hardware.gps_resume import script_content

    installed = tmp_path / "hammunition-gps-resume"
    installed.write_text(script_content())
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty]])
    gpsd.append(server)
    result = subprocess.run(
        [sys.executable, "-I", str(installed), *_argv(machine, server)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert [line.split()[:2] for line in _ran(machine)] == [
        ["gpsdctl", "remove"],
        ["gpsdctl", "add"],
    ]
    assert len(result.stdout.splitlines()) == 3


def test_the_script_imports_only_the_standard_library() -> None:
    import ast

    tree = ast.parse(Path(script.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported, "the walk found no imports at all"
    assert all(name in sys.stdlib_module_names or name == "__future__" for name in imported), (
        imported
    )
