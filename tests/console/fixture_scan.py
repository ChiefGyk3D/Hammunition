# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Find anything in a fixture that could identify a person or a machine.

A callsign and a grid square are never public; neither is a hostname, a
serial, a username or a real home path. Fixtures use N0CALL, N0TST, FN31pr,
/home/user and the host name `host`."""

from __future__ import annotations

import getpass
import re
import socket

ALLOWED_CALLSIGNS = {"N0CALL", "N0TST"}
ALLOWED_GRIDS = {"FN31pr"}
# Words that look like a callsign or a grid but are not one. Every addition must
# be reviewed by a person and say why in a comment.
ALLOWED_WORDS: set[str] = {
    # Upstream authors' and projects' names in public catalog prose (list --json),
    # reviewed 2026-10-03: none is the maintainer's.
    "W1HKJ",  # the fldigi author's suite
    "HB9JNX",  # the parallel-port and USB packet modem drivers
    "SM5BSZ",  # Linrad's author
    "VE3NEA",  # Morse Runner's author
    "G8BPQ",  # BPQ / QtTermTCP's author
    "AA1AAA",  # FreeDATA's example station callsign, quoted from its docs
    "FN31",  # a four-character grid prefix quoted from HamClock's defaults
}

CALL = re.compile(r"\b(?:[A-Z]{1,2}|[0-9][A-Z])[0-9][A-Z]{1,3}\b")
GRID = re.compile(r"\b[A-R]{2}[0-9]{2}(?:[a-x]{2})?\b")
HOME = re.compile(r"/home/([A-Za-z0-9._-]+)")
BY_ID = re.compile(r"/dev/serial/by-id/(\S+)")


def host_pattern(host: str) -> re.Pattern[str]:
    """The host name where it is a host: a host name that is also a common word or a
    product name must not match as a bare word (`hammunition install`, `runner`)."""
    name = re.escape(host)
    return re.compile(
        rf"@{name}\b|\b{name}\.(?:local|lan|home|localdomain)\b|\bhostname\W{{1,3}}{name}\b", re.I
    )


def user_pattern(user: str) -> re.Pattern[str]:
    """The account name where it is an account: a home path, `user@`, `owner: user`."""
    name = re.escape(user)
    return re.compile(rf"/home/{name}\b|\b{name}@|\bowner\W{{1,3}}{name}\b", re.I)


def live_identity_findings(text: str) -> list[str]:
    """The live username and hostname as a bare substring. This is a recording-time
    check (capture_fixtures.py), not a test: what counts as a bare substring
    depends on the machine running it, and a test must not."""
    out: list[str] = []
    user = getpass.getuser()
    if len(user) >= 3 and user.lower() in text.lower():
        out.append("the recording account's name appears")
    host = socket.gethostname().split(".")[0]
    if len(host) >= 3 and host.lower() in text.lower():
        out.append("the recording host's name appears")
    return out


def findings(text: str) -> list[str]:
    out: list[str] = []
    for m in CALL.finditer(text):
        word = m.group(0)
        if word not in ALLOWED_CALLSIGNS and word not in ALLOWED_WORDS:
            out.append(f"callsign-like token {word!r}")
    for m in GRID.finditer(text):
        word = m.group(0)
        if word not in ALLOWED_GRIDS and word not in ALLOWED_WORDS:
            out.append(f"grid-square-like token {word!r}")
    for m in HOME.finditer(text):
        if m.group(1) != "user":
            out.append(f"home path for {m.group(1)!r} (use /home/user)")
    for m in BY_ID.finditer(text):
        if "FIXTURE" not in m.group(1):
            out.append(f"serial-bearing device path {m.group(0)!r} (use usb-FIXTURE-if00)")
    user = getpass.getuser()
    if len(user) >= 3 and user_pattern(user).search(text):
        out.append("the account name, as a home path, user@ or owner")
    host = socket.gethostname().split(".")[0]
    if len(host) >= 3 and host_pattern(host).search(text):
        out.append("the host name, as @host, host.local or hostname")
    return out
