# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The script the resume unit runs as root after a suspend (issue #177).

Everything it touches is a fake: ``gpsdctl`` and ``systemctl`` are shell
scripts that record their argv, gpsd is a loopback server answering
``?DEVICES;``, and ``/dev`` is a temporary directory holding a ``gps0``
symlink to a ``ttyACM0`` file, exactly the shape gpsd's own udev rule makes.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from hammunition.hardware import gps_resume_script as script


@dataclass
class Stream:
    """A watch answer: these reports, then the connection is held open silently."""

    reports: list[dict[str, object]]


def alive(device: str) -> Stream:
    return Stream([{"class": "SKY", "device": device, "satellites": []}])


class FakeGpsd:
    """A loopback gpsd: a VERSION banner, then one DEVICES reply per ``?DEVICES;``.

    ``answers`` is consumed one per connection: a list of paths is a reply,
    ``None`` is a gpsd that accepts and never answers.
    """

    def __init__(
        self,
        answers: list[list[str] | Stream | None],
        watches: list[Stream | None] | None = None,
    ) -> None:
        self.answers = list(answers)
        self.watches = None if watches is None else list(watches)
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
        while True:  # accept() raising is how close() ends the loop
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            if self._stop:
                conn.close()
                return
            conn.sendall(b'{"class":"VERSION","release":"3.25","proto_major":3}\r\n')
            data = b""
            while b";" not in data:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk
            queue = self.watches if self.watches is not None and b"WATCH" in data else self.answers
            answer = queue.pop(0) if queue else []
            self.asked += 1
            if answer is None:
                self._held.append(conn)
                continue
            if isinstance(answer, Stream):
                for report in answer.reports:
                    conn.sendall(json.dumps(report).encode() + b"\r\n")
                self._held.append(conn)
                continue
            devices = [{"class": "DEVICE", "path": p, "driver": "u-blox"} for p in answer]
            reply = json.dumps({"class": "DEVICES", "devices": devices})
            conn.sendall(reply.encode() + b"\r\n")
            conn.close()

    def close(self) -> None:
        """Stop serving and wait for the thread: ``shutdown`` wakes ``accept()``
        (a bare ``close`` does not on Linux, and the thread would then accept
        on whichever socket next reuses the descriptor number)."""
        self._stop = True
        with contextlib.suppress(OSError):
            self.server.shutdown(socket.SHUT_RDWR)
        self.server.close()
        self.thread.join(timeout=5.0)
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
    runlog = tmp_path / "run" / "gps-resume.log"
    runlog.parent.mkdir()
    return {
        "dev": dev,
        "log": log,
        "runlog": runlog,
        "control": control,
        "sysfs": tmp_path / "sys",
        **tools,
    }


def _receiver(dev: Path, number: int = 0, tty: str = "ttyACM0") -> None:
    (dev / tty).write_text("")
    (dev / f"gps{number}").symlink_to(tty)


@pytest.fixture
def gpsd() -> Iterator[list[FakeGpsd]]:
    made: list[FakeGpsd] = []
    yield made
    for server in made:
        server.close()


def _argv(
    m: dict[str, Path],
    server: FakeGpsd | None,
    timeout: float = 2.0,
    data_window: float = 1.0,
) -> list[str]:
    """The script's argv against the fake machine.

    ``data_window`` is how long a data check waits before calling a receiver
    silent. A check returns the moment every receiver has reported, so a test
    whose receiver answers at once pays nothing for a long window; the default
    is for the tests that need a window to *expire*, and it is a second rather
    than the 0.4 s it was because a loaded CI runner once took longer than that
    to schedule the fake gpsd's thread (Python 3.14, 2026-10-04).
    """
    port = server.port if server is not None else 9
    return [
        "--data-window",
        f"{data_window:g}",
        "--cycle-pause",
        "0.01",
        "--reenum-window",
        "0.5",
        "--relist-window",
        "0.3",
        "--sysfs",
        str(m["sysfs"]),
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
        "--log-file",
        str(m["runlog"]),
    ]


def _ran(m: dict[str, Path]) -> list[str]:
    if not m["log"].exists():
        return []
    return m["log"].read_text().splitlines()


def test_a_closed_fake_gpsd_has_no_thread_left_in_accept() -> None:
    """The fixture's hygiene, held by a test because it once was not: a thread
    still blocked in ``accept()`` on a closed descriptor accepts for whichever
    later socket Linux hands that descriptor number, and answers it from a
    queue that is empty or another test's (three different tests failed on CI
    on 2026-10-04 with replies no fake in them could give)."""
    server = FakeGpsd([["/dev/ttyACM0"]])
    server.close()
    server.thread.join(timeout=2.0)
    assert not server.thread.is_alive()


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
    server = FakeGpsd([[tty], [tty], alive(tty)])
    gpsd.append(server)
    assert script.main(_argv(machine, server, data_window=5.0)) == 0
    socket_env = f"GPSD_SOCKET={machine['control']}"
    assert _ran(machine) == [
        f"gpsdctl remove {tty} {socket_env}",
        f"gpsdctl add {tty} {socket_env}",
    ]
    out = capsys.readouterr().out.splitlines()
    assert any(line.startswith(f"gpsdctl remove {tty}") for line in out)
    assert any(line.startswith(f"gpsdctl add {tty}") for line in out)
    assert server.asked == 3


def test_a_receiver_gpsd_knows_by_its_gps_name_keeps_that_name(
    machine: dict[str, Path], gpsd: list[FakeGpsd]
) -> None:
    """DEVICES="/dev/gps0" in /etc/default/gpsd: re-adding the tty would give
    gpsd a second handle on the same port."""
    _receiver(machine["dev"])
    link = str(machine["dev"] / "gps0")
    server = FakeGpsd([[link], [link], alive(link)])
    gpsd.append(server)
    assert script.main(_argv(machine, server, data_window=5.0)) == 0
    assert [line.split()[:3] for line in _ran(machine)] == [
        ["gpsdctl", "remove", link],
        ["gpsdctl", "add", link],
    ]


def test_every_receiver_in_number_order(machine: dict[str, Path], gpsd: list[FakeGpsd]) -> None:
    _receiver(machine["dev"], 10, "ttyACM2")
    _receiver(machine["dev"], 2, "ttyUSB0")
    ttys = [str(machine["dev"] / "ttyUSB0"), str(machine["dev"] / "ttyACM2")]
    server = FakeGpsd(
        [ttys, ttys, Stream([{"class": "TPV", "device": t, "mode": 1} for t in ttys])]
    )
    gpsd.append(server)
    assert script.main(_argv(machine, server, data_window=5.0)) == 0
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
    server = FakeGpsd([[tty], [], alive(tty)])
    gpsd.append(server)
    assert script.main(_argv(machine, server, data_window=5.0)) == 0
    assert _ran(machine)[-1].startswith("systemctl try-restart gpsd.service")
    assert "no device" in capsys.readouterr().out


def test_a_gpsd_that_does_not_answer_in_time_is_restarted(
    machine: dict[str, Path], gpsd: list[FakeGpsd], capsys: pytest.CaptureFixture[str]
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([None, None, alive(tty)])
    gpsd.append(server)
    assert script.main(_argv(machine, server, timeout=0.3, data_window=5.0)) == 0
    ran = _ran(machine)
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
    assert script.main(argv) == 1  # nothing to watch either: silence
    assert _ran(machine)[-1].startswith("systemctl try-restart gpsd.service")


def test_a_failed_restart_fails_the_unit(machine: dict[str, Path], gpsd: list[FakeGpsd]) -> None:
    _receiver(machine["dev"])
    machine["systemctl"].write_text(f'#!/bin/sh\necho "systemctl $*" >> {machine["log"]}\nexit 1\n')
    server = FakeGpsd([[], []])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 1


def test_a_failing_gpsdctl_is_logged_and_data_decides_the_exit(
    machine: dict[str, Path], gpsd: list[FakeGpsd], capsys: pytest.CaptureFixture[str]
) -> None:
    _receiver(machine["dev"])
    machine["gpsdctl"].write_text(
        f'#!/bin/sh\necho "gpsdctl $*" >> {machine["log"]}\necho "no gpsd" >&2\nexit 1\n'
    )
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], alive(tty)])
    gpsd.append(server)
    assert script.main(_argv(machine, server, data_window=5.0)) == 0
    out = capsys.readouterr().out
    assert "failed: no gpsd" in out
    assert server.asked == 3


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
    server = FakeGpsd([[tty], [tty], alive(tty)])
    gpsd.append(server)
    result = subprocess.run(
        [sys.executable, "-I", str(installed), *_argv(machine, server, data_window=5.0)],
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
    assert len(result.stdout.splitlines()) == 4


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


# ---- the data check and the single escalation (issue #177) ----------------


@pytest.fixture
def usb(machine: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """A sysfs tree with the real layering and a recorder in place of the write.

    ``3-5`` is a hub (ids 0424:2422), ``3-5.1`` the receiver (ids set), and
    ``3-5.1:1.0`` its interface, which is what the tty's ``device`` names.
    Writing ``0`` removes the tty node, ``1`` brings it back.
    """
    sysfs = machine["sysfs"]
    hub = sysfs / "devices" / "pci0000:00" / "3-5"
    device = hub / "3-5.1"
    iface = device / "3-5.1:1.0"
    iface.mkdir(parents=True)
    for node, ids in ((hub, ("0424", "2422")), (device, ("1546", "01a9"))):
        (node / "idVendor").write_text(ids[0] + "\n")
        (node / "idProduct").write_text(ids[1] + "\n")
        (node / "authorized").write_text("1\n")
    tty = sysfs / "class" / "tty" / "ttyACM0"
    tty.mkdir(parents=True)
    (tty / "device").symlink_to(iface)
    writes: list[tuple[str, str]] = []
    node = machine["dev"] / "ttyACM0"

    def fake_write(path: str, value: str) -> None:
        writes.append((path, value))
        if value == "0":
            node.unlink(missing_ok=True)
        else:
            node.write_text("")

    monkeypatch.setattr(script, "write_value", fake_write)
    return {"writes": writes, "hub": hub, "device": device, "iface": iface}


def _writes(u: dict[str, object]) -> list[tuple[str, str]]:
    w = u["writes"]
    assert isinstance(w, list)
    return w


def test_data_after_the_re_add_means_no_cycle_and_exit_0(
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], alive(tty)])
    gpsd.append(server)
    assert script.main(_argv(machine, server, data_window=5.0)) == 0
    assert _writes(usb) == []
    assert "data from" in capsys.readouterr().out


def test_satellites_without_a_fix_and_a_mode_report_count_as_alive(
    machine: dict[str, Path], usb: dict[str, object], gpsd: list[FakeGpsd]
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd(
        [[tty], [tty], Stream([{"class": "WATCH"}, {"class": "TPV", "device": tty, "mode": 1}])]
    )
    gpsd.append(server)
    assert script.main(_argv(machine, server, data_window=5.0)) == 0
    assert _writes(usb) == []


def test_a_report_for_another_device_is_not_this_receivers_data(
    machine: dict[str, Path], usb: dict[str, object], gpsd: list[FakeGpsd]
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], alive("/dev/ttyUSB9"), [tty], alive(tty)])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 0
    assert [v for _, v in _writes(usb)] == ["0", "1"]


def test_silent_then_alive_after_one_power_cycle(
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], None, [tty], alive(tty)])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 0
    target = str(usb["device"] / "authorized")  # type: ignore[operator]
    assert _writes(usb) == [(target, "0"), (target, "1")]
    out = capsys.readouterr().out.splitlines()
    steps = [
        "data check:",
        "silent; wrote 0 to",
        "wrote 1 to",
        "re-enumerated",
        "gpsd lists",
        "data check after the cycle: data from",
    ]
    at = -1
    for step in steps:
        later = [n for n, line in enumerate(out) if step in line and n > at]
        assert later, (step, out)
        at = later[0]
    assert not any("park gps-receiver" in line for line in out)
    assert not any(line.startswith("systemctl") for line in _ran(machine))


def test_gpsd_not_listing_the_tty_after_the_cycle_gets_a_gpsdctl_add(
    machine: dict[str, Path], usb: dict[str, object], gpsd: list[FakeGpsd]
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty]], watches=[None, alive(tty)])  # gpsd never lists it again
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 0
    assert any(line.startswith(f"gpsdctl add {tty}") for line in _ran(machine)[2:])


def test_silent_after_the_cycle_exits_1_and_names_the_manual_steps(
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], None, [tty], None])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 1
    assert len(_writes(usb)) == 2  # one cycle, never a loop
    last = capsys.readouterr().out.splitlines()[-1]
    assert "hammunition hardware park gps-receiver" in last
    assert "hammunition hardware wake gps-receiver" in last


def test_no_authorized_file_falls_back_to_one_restart(
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    capsys: pytest.CaptureFixture[str],
) -> None:
    (usb["device"] / "authorized").unlink()  # type: ignore[operator]
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], None])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 1
    assert _writes(usb) == []
    restarts = [line for line in _ran(machine) if line.startswith("systemctl try-restart")]
    assert len(restarts) == 1
    assert "no USB power cycle possible" in capsys.readouterr().out


def test_the_walk_stops_at_the_receiver_never_at_the_hub(
    machine: dict[str, Path], usb: dict[str, object], gpsd: list[FakeGpsd]
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], None, [tty], alive(tty)])
    gpsd.append(server)
    script.main(_argv(machine, server))
    assert all(not path.startswith(str(usb["hub"]) + "/authorized") for path, _ in _writes(usb))
    assert all("3-5.1/authorized" in path for path, _ in _writes(usb))


def test_a_receiver_directory_without_ids_is_never_replaced_by_its_hub(
    machine: dict[str, Path], usb: dict[str, object], gpsd: list[FakeGpsd]
) -> None:
    """If 3-5.1 had no ids the walk would reach hub 3-5; the interface is not
    the hub's child, so it is refused and the hub is never written."""
    (usb["device"] / "idVendor").unlink()  # type: ignore[operator]
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], None])
    gpsd.append(server)
    assert script.main(_argv(machine, server)) == 1
    assert _writes(usb) == []


@pytest.mark.parametrize(
    "path",
    [
        "/sys/devices/../etc/authorized",
        "/sys/devices/pci0000:00/3-5.1/../3-5/authorized",
        "/sys/devices/pci0000:00/3-5.1/driver/unbind",
        "/sys/devices/pci0000:00/not-a-usb-address/authorized",
        "/sys/devices//3-5.1/authorized",
        "/etc/3-5.1/authorized",
        "/sys/devices/authorized",
    ],
)
def test_the_lexical_guard_refuses_a_bad_path(path: str) -> None:
    with pytest.raises(ValueError):
        script.guard_authorized(path, "/sys")


def test_the_lexical_guard_accepts_the_real_shape() -> None:
    path = "/sys/devices/pci0000:00/0000:00:14.0/usb3/3-5/3-5.1/authorized"
    assert script.guard_authorized(path, "/sys") == path


def test_a_write_never_lands_outside_the_fake_tree(
    machine: dict[str, Path],
    usb: dict[str, object],
    gpsd: list[FakeGpsd],
    tmp_path: Path,
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], None, [tty], alive(tty)])
    gpsd.append(server)
    script.main(_argv(machine, server))
    assert _writes(usb)
    for path, _ in _writes(usb):
        assert path.startswith(str(machine["sysfs"].resolve()) + "/devices/")


def test_the_real_write_goes_to_a_real_file(machine: dict[str, Path], tmp_path: Path) -> None:
    target = tmp_path / "authorized"
    script.write_value(str(target), "0")
    assert target.read_text() == "0"


# ---- the log file beside the journal (issue #177) -------------------------


def test_a_run_writes_its_lines_to_a_0644_log_and_the_next_run_replaces_it(
    machine: dict[str, Path],
) -> None:
    runlog = machine["runlog"]
    runlog.write_text("a previous run\n")
    runlog.chmod(0o600)
    assert script.main(_argv(machine, None)) == 0
    text = runlog.read_text()
    assert "a previous run" not in text
    lines = text.splitlines()
    assert lines[0].startswith("gps-resume run started 20")
    assert "nothing to do" in lines[1]
    assert lines[-1] == "gps-resume run finished: exit 0"
    assert runlog.stat().st_mode & 0o777 == 0o644


def test_the_log_carries_what_the_journal_does(
    machine: dict[str, Path], gpsd: list[FakeGpsd], capsys: pytest.CaptureFixture[str]
) -> None:
    _receiver(machine["dev"])
    tty = str(machine["dev"] / "ttyACM0")
    server = FakeGpsd([[tty], [tty], alive(tty)])
    gpsd.append(server)
    assert script.main(_argv(machine, server, data_window=5.0)) == 0
    printed = capsys.readouterr().out.splitlines()
    logged = machine["runlog"].read_text().splitlines()
    assert logged[1:-1] == printed
    assert "gpsdctl remove" in logged[1]


def test_a_log_that_cannot_be_written_never_stops_the_run(
    machine: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _argv(machine, None)
    argv[argv.index("--log-file") + 1] = str(machine["runlog"].parent / "absent" / "x.log")
    assert script.main(argv) == 0
    assert "nothing to do" in capsys.readouterr().out
    assert script._LOG == []


def test_a_log_path_that_is_a_symlink_is_not_followed(
    machine: dict[str, Path], tmp_path: Path
) -> None:
    victim = tmp_path / "victim"
    victim.write_text("keep")
    machine["runlog"].symlink_to(victim)
    assert script.main(_argv(machine, None)) == 0
    assert victim.read_text() == "keep"
