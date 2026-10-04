# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Give gpsd a fresh open of each GPS receiver after a resume.  Issue #177.

Run as root by ``hammunition-gps-resume.service`` once the machine is back
from suspend or hibernation. Measured on the field laptop (#177): a USB
receiver is not re-enumerated across a suspend, so nothing removes and re-adds
it, and gpsd can keep a tty that has gone quiet. Every recovery that worked
gave gpsd a fresh open of the receiver.

What it does, one journal line per action:

1. No ``/dev/gpsN`` (gpsd's own udev rule makes them): nothing. A parked or
   unplugged receiver is never woken.
2. No gpsd control socket: nothing. ``gpsdctl add`` would start a gpsd of its
   own outside systemd.
3. For each receiver, ``gpsdctl remove`` then ``gpsdctl add``, by the path gpsd
   reports for it (``?DEVICES;``): the tty, as ``gpsdctl@`` registers it, or
   ``/dev/gpsN`` where gpsd was configured with that name.
4. ``?DEVICES;`` again, two seconds at most. No device, or no answer:
   ``systemctl try-restart gpsd.service``.
5. **Data check.** gpsd's socket is watched (``?WATCH``) for ``--data-window``
   seconds (20). A ``SKY`` or ``TPV`` report for the receiver, or any report
   with ``mode`` of 1 or more, means it is alive. Satellites without a fix are
   alive (a cold fix takes a minute); silence is the fault.
6. **Escalation, only on silence, once per receiver.** The receiver's own USB
   device directory is found by walking up from ``/sys/class/tty/<tty>/device``
   to the first directory with ``idVendor`` and ``idProduct`` whose child is the
   tty's interface (``<device>:1.0``), so a hub is never taken for the receiver.
   Its ``authorized`` is written ``0``, then ``1`` after ``--cycle-pause``
   seconds: the switch ``hammunition hardware park`` and ``wake`` use, and a
   power cycle that loses the receiver's warm start. The path passes a lexical
   guard (under ``<sysfs>/devices/``, no ``..``, a USB address, the one leaf
   ``authorized``). When the tty is back, gpsd's own hook re-adds it; if gpsd
   does not list it within ``--relist-window`` seconds, ``gpsdctl add`` does.
   The data check is then repeated once. With no ``authorized`` or no device
   found, it falls back to ``systemctl try-restart gpsd.service`` (once).

Every line is also written to ``/run/hammunition/gps-resume.log`` (0644,
replaced at the start of each run, ``--log-file``): the journal of a system
unit needs ``systemd-journal`` membership, and ``hammunition hardware
gps-resume-report`` reads this file instead. A log that cannot be written
never stops the run.

The exit status is 0 only when data was seen from every receiver. Otherwise it
is 1 and the last line names the manual steps, so ``systemctl status`` shows
them.

gpsd's TCP port is read only after the control socket is seen, but a local
account could still answer on 127.0.0.1:2947 when gpsd's socket is not
holding it. The reply only chooses between the paths this script found in
``/dev`` and ``/sys`` and whether the receiver is alive; no path or command is
taken from it.

Standard library only. The file is installed whole under
``/usr/local/libexec/`` and run by ``/usr/bin/python3 -I``, which gpsd's own
package depends on; it imports nothing from Hammunition. The options exist
for the test suite; the unit passes none.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import socket
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

_GPS = re.compile(r"gps([0-9]+)")
_USB_ADDRESS = re.compile(r"[0-9]+-[0-9]+(\.[0-9]+)*")
_MANUAL = (
    "recovery failed: park and wake the receiver from the tray, or run "
    "`hammunition hardware park gps-receiver` then `hammunition hardware wake gps-receiver`"
)


_LOG: list[int] = []
"""The open log file's descriptor, when there is one (a list, not a global)."""


def open_log(path: str) -> None:
    """Replace the log with a new one, 0644. Never raises: no log is not a fault."""
    close_log()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    except OSError:
        return
    with contextlib.suppress(OSError):
        os.fchmod(fd, 0o644)
    _LOG.append(fd)


def close_log() -> None:
    while _LOG:
        with contextlib.suppress(OSError):
            os.close(_LOG.pop())


def log(message: str, *, echo: bool = True) -> None:
    """One line to stdout (the journal) and to the log file; ``echo=False`` is the
    file alone, for the lines the journal already stamps itself."""
    if echo:
        print(message, flush=True)
    if _LOG:
        with contextlib.suppress(OSError):
            os.write(_LOG[0], (message + "\n").encode("utf-8", "replace"))


def receivers(dev: Path) -> list[tuple[str, str]]:
    """``(/dev/gpsN, the device node it names)`` for each receiver, by number."""
    try:
        entries = list(dev.iterdir())
    except OSError:
        return []
    root = Path(os.path.realpath(dev))
    found: list[tuple[int, str, str]] = []
    for entry in entries:
        match = _GPS.fullmatch(entry.name)
        if match is None or not entry.is_symlink():
            continue
        node = Path(os.path.realpath(entry))
        if node.parent != root or not node.exists():
            log(f"{entry} does not name a device node in {dev}; skipped")
            continue
        found.append((int(match.group(1)), str(entry), str(dev / node.name)))
    return [(link, node) for _, link, node in sorted(found)]


def devices(host: str, port: int, timeout: float) -> list[str] | None:
    """The device paths gpsd reports, or None when it does not answer in time."""
    deadline = time.monotonic() + timeout
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(b"?DEVICES;\n")
            buffer = b""
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                sock.settimeout(left)
                chunk = sock.recv(4096)
                if not chunk:
                    return None
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(message, dict) or message.get("class") != "DEVICES":
                        continue
                    listed = message.get("devices")
                    if not isinstance(listed, list):
                        return []
                    return [
                        d["path"]
                        for d in listed
                        if isinstance(d, dict) and isinstance(d.get("path"), str)
                    ]
    except OSError:
        return None


def run(argv: list[str], env: dict[str, str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=15, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    said = (result.stderr or result.stdout).strip().splitlines()
    return result.returncode == 0, said[-1] if said else f"exit {result.returncode}"


def _outcome(ok: bool, detail: str) -> str:
    return "ok" if ok else f"failed: {detail}"


def watch(host: str, port: int, names: dict[int, set[str]], window: float) -> dict[int, float]:
    """Watch gpsd for ``window`` seconds; ``{receiver: seconds until its first report}``.

    ``names`` maps a receiver's index to the device paths gpsd might call it.
    """
    alive: dict[int, float] = {}
    start = time.monotonic()
    deadline = start + window
    try:
        with socket.create_connection((host, port), timeout=min(window, 2.0)) as sock:
            sock.sendall(b'?WATCH={"enable":true,"json":true};\n')
            buffer = b""
            while len(alive) < len(names):
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                sock.settimeout(left)
                try:
                    chunk = sock.recv(4096)
                except TimeoutError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(message, dict):
                        continue
                    device = message.get("device")
                    mode = message.get("mode")
                    live = message.get("class") in ("SKY", "TPV") or (
                        isinstance(mode, int) and not isinstance(mode, bool) and mode >= 1
                    )
                    if not live or not isinstance(device, str):
                        continue
                    for index, known in names.items():
                        if device in known and index not in alive:
                            alive[index] = time.monotonic() - start
    except OSError:
        pass
    return alive


def guard_authorized(path: str, sysfs: str) -> str:
    """The ``authorized`` file of a USB device under ``<sysfs>/devices/``, or ValueError.

    Lexical, as ``hammunition.hardware.power.guard`` is: ``..`` is refused, the
    path is not resolved, and the leaf must be exactly ``authorized`` in a
    directory named like a USB address.
    """
    if ".." in path.split("/") or os.path.normpath(path) != path:
        raise ValueError(f"{path!r} is not a normalised path")
    root = os.path.normpath(sysfs).rstrip("/") + "/devices/"
    if not path.startswith(root):
        raise ValueError(f"{path!r} is not under {root}")
    parts = path[len(root) :].split("/")
    if len(parts) < 2 or "" in parts or parts[-1] != "authorized":
        raise ValueError(f"{path!r} is not a device's authorized file")
    if _USB_ADDRESS.fullmatch(parts[-2]) is None:
        raise ValueError(f"{parts[-2]!r} is not a USB device address")
    return path


def usb_authorized(tty: str, sysfs: str) -> str:
    """The receiver's own ``authorized`` file, found from its tty, or ValueError."""
    root = os.path.realpath(sysfs)
    start = os.path.realpath(os.path.join(sysfs, "class", "tty", tty, "device"))
    if not os.path.isdir(start):
        raise ValueError(f"/sys/class/tty/{tty}/device is absent")
    child = start
    node = start
    while node.startswith(root + "/devices/"):
        if os.path.isfile(os.path.join(node, "idVendor")) and os.path.isfile(
            os.path.join(node, "idProduct")
        ):
            if not os.path.basename(child).startswith(os.path.basename(node) + ":"):
                raise ValueError(f"{node} is not the USB device the tty's interface belongs to")
            target = os.path.join(node, "authorized")
            if not os.path.isfile(target):
                raise ValueError(f"{node} has no authorized file")
            return guard_authorized(target, root)
        child, node = node, os.path.dirname(node)
    raise ValueError("no USB device directory above the tty")


def write_value(path: str, value: str) -> None:
    with open(path, "w", encoding="ascii") as handle:
        handle.write(value)


def wait_for(predicate: Callable[[], bool], window: float) -> bool:
    deadline = time.monotonic() + window
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(0.2, max(deadline - time.monotonic(), 0.0)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hammunition-gps-resume")
    parser.add_argument("--dev", default="/dev")
    parser.add_argument("--sysfs", default="/sys")
    parser.add_argument("--gpsdctl", default="/usr/sbin/gpsdctl")
    parser.add_argument("--systemctl", default="/usr/bin/systemctl")
    parser.add_argument("--control-socket", default="/run/gpsd.sock")
    parser.add_argument("--gpsd-host", default="127.0.0.1")
    parser.add_argument("--gpsd-port", type=int, default=2947)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--data-window", type=float, default=20.0)
    parser.add_argument("--cycle-pause", type=float, default=3.0)
    parser.add_argument("--reenum-window", type=float, default=10.0)
    parser.add_argument("--relist-window", type=float, default=5.0)
    parser.add_argument("--log-file", default="/run/hammunition/gps-resume.log")
    args = parser.parse_args(argv)
    open_log(args.log_file)
    try:
        log(
            f"gps-resume run started {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}",
            echo=False,
        )
        code = _run(args)
        log(f"gps-resume run finished: exit {code}", echo=False)
        return code
    finally:
        close_log()


def _run(args: argparse.Namespace) -> int:
    found = receivers(Path(args.dev))
    if not found:
        log("no /dev/gpsN: no receiver attached, or it is parked; nothing to do")
        return 0
    if not os.path.exists(args.control_socket):
        log(f"{args.control_socket} is absent: gpsd is not running; nothing to do")
        return 0

    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "GPSD_SOCKET": args.control_socket}
    known = devices(args.gpsd_host, args.gpsd_port, args.timeout)
    for link, node in found:
        path = link if known is not None and link in known else node
        if known is None or path in known:
            ok, detail = run([args.gpsdctl, "remove", path], env)
            log(f"gpsdctl remove {path} ({link}): {_outcome(ok, detail)}")
        ok, detail = run([args.gpsdctl, "add", path], env)
        log(f"gpsdctl add {path} ({link}): {_outcome(ok, detail)}")

    restarted = False
    after = devices(args.gpsd_host, args.gpsd_port, args.timeout)
    if after:
        log(f"gpsd reports {len(after)} device(s): {', '.join(after)}")
    else:
        why = "no answer" if after is None else "no device"
        ok, detail = run([args.systemctl, "try-restart", "gpsd.service"], env)
        restarted = True
        log(
            f"gpsd gave {why} to ?DEVICES; systemctl try-restart gpsd.service: {_outcome(ok, detail)}"
        )

    def names(link: str, node: str) -> set[str]:
        return {link, node, os.path.realpath(node), os.path.realpath(link)}

    def check(label: str, subset: dict[int, tuple[str, str]]) -> set[int]:
        seen = watch(
            args.gpsd_host,
            args.gpsd_port,
            {i: names(*pair) for i, pair in subset.items()},
            args.data_window,
        )
        for i, pair in subset.items():
            if i in seen:
                log(f"{label}: data from {pair[1]} within {seen[i]:.0f} s")
            else:
                log(f"{label}: {pair[1]} silent after {args.data_window:g} s")
        return set(seen)

    everyone = dict(enumerate(found))
    seen_first = check("data check", everyone)
    silent = {i: p for i, p in everyone.items() if i not in seen_first}
    for i, (link, node) in list(silent.items()):
        tty = os.path.basename(node)
        try:
            target = usb_authorized(tty, args.sysfs)
        except ValueError as exc:
            log(f"{tty}: no USB power cycle possible ({exc})")
            if not restarted:
                ok, detail = run([args.systemctl, "try-restart", "gpsd.service"], env)
                restarted = True
                log(f"systemctl try-restart gpsd.service: {_outcome(ok, detail)}")
            continue
        try:
            write_value(target, "0")
            log(f"{tty}: silent; wrote 0 to {target} (USB power cycle, once)")
            time.sleep(args.cycle_pause)
            write_value(target, "1")
            log(f"{tty}: wrote 1 to {target}")
        except OSError as exc:
            log(f"{tty}: writing {target} failed: {exc}")
            continue

        def back(n: str = node) -> bool:
            return os.path.exists(n)

        def listed(n: str = node) -> bool:
            return n in (devices(args.gpsd_host, args.gpsd_port, args.timeout) or [])

        if not wait_for(back, args.reenum_window):
            log(f"{tty}: did not reappear within {args.reenum_window:g} s")
            continue
        log(f"{tty}: re-enumerated")
        if not wait_for(listed, args.relist_window):
            ok, detail = run([args.gpsdctl, "add", node], env)
            log(
                f"gpsd did not list {node} within {args.relist_window:g} s; gpsdctl add: {_outcome(ok, detail)}"
            )
        else:
            log(f"gpsd lists {node}")
        if i in check("data check after the cycle", {i: (link, node)}):
            silent.pop(i)
    # Receivers that came back are those the second check saw.
    remaining = [node for i, (_, node) in everyone.items() if i in silent]
    if not remaining:
        return 0
    log(f"no data from {', '.join(remaining)}")
    log(_MANUAL)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
