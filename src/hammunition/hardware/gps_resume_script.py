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
   ``systemctl try-restart gpsd.service``, which restarts gpsd only if it is
   running. This catches gpsd losing the device or hanging. It does **not**
   catch a receiver gpsd still lists that stays silent after the re-add: no
   data check is made, so that case needs the operator's manual steps.

The exit status is 1 when the restart or any ``gpsdctl add`` failed, so
``systemctl status`` shows it.

gpsd's TCP port is read only after the control socket is seen, but a local
account could still answer on 127.0.0.1:2947 when gpsd's socket is not
holding it. The reply only chooses between the two paths this script found
in ``/dev`` and whether to restart gpsd; no path or command is taken from it.

The park and wake cycle is not done here: it is the heaviest recovery, and it
is the operator's (docs/hardware/power-control.md, "After suspend").

Standard library only. The file is installed whole under
``/usr/local/libexec/`` and run by ``/usr/bin/python3 -I``, which gpsd's own
package depends on; it imports nothing from Hammunition. The options exist
for the test suite; the unit passes none.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

_GPS = re.compile(r"gps([0-9]+)")


def log(message: str) -> None:
    print(message, flush=True)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hammunition-gps-resume")
    parser.add_argument("--dev", default="/dev")
    parser.add_argument("--gpsdctl", default="/usr/sbin/gpsdctl")
    parser.add_argument("--systemctl", default="/usr/bin/systemctl")
    parser.add_argument("--control-socket", default="/run/gpsd.sock")
    parser.add_argument("--gpsd-host", default="127.0.0.1")
    parser.add_argument("--gpsd-port", type=int, default=2947)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args(argv)

    found = receivers(Path(args.dev))
    if not found:
        log("no /dev/gpsN: no receiver attached, or it is parked; nothing to do")
        return 0
    if not os.path.exists(args.control_socket):
        log(f"{args.control_socket} is absent: gpsd is not running; nothing to do")
        return 0

    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "GPSD_SOCKET": args.control_socket}
    known = devices(args.gpsd_host, args.gpsd_port, args.timeout)
    added = True
    for link, node in found:
        path = link if known is not None and link in known else node
        if known is None or path in known:
            ok, detail = run([args.gpsdctl, "remove", path], env)
            log(f"gpsdctl remove {path} ({link}): {_outcome(ok, detail)}")
        ok, detail = run([args.gpsdctl, "add", path], env)
        log(f"gpsdctl add {path} ({link}): {_outcome(ok, detail)}")
        added = added and ok

    after = devices(args.gpsd_host, args.gpsd_port, args.timeout)
    if after:
        log(f"gpsd reports {len(after)} device(s): {', '.join(after)}")
        return 0 if added else 1
    why = "no answer" if after is None else "no device"
    ok, detail = run([args.systemctl, "try-restart", "gpsd.service"], env)
    log(f"gpsd gave {why} to ?DEVICES; systemctl try-restart gpsd.service: {_outcome(ok, detail)}")
    return 0 if ok and added else 1


if __name__ == "__main__":
    raise SystemExit(main())
