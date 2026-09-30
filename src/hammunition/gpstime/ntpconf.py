# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Marked, reversible edits to ntpsec's ntp.conf.  D-058.

ntp.conf is a dpkg conffile, and two things GPS time needs cannot be said from
an include file (spec §4b): a lone GPS is ignored while ``tos minclock 4
minsane 3`` stands (unless Task 9 shows an ntp.d override works), and
``gps-only`` must stop the ``pool`` lines, because ``restrict nopeer`` no
longer holds pool associations back. So those lines are edited in place, and
every edit carries a marker that says exactly how to undo it:

- ``#hammunition-gps:off# <line>`` -- the original line, disabled.
- ``#hammunition-gps:was# <line>`` followed by ``<line> prefer`` -- the original
  kept, its preferred copy live on the next line.

:func:`restore` undoes both exactly, so the file's checksum matches the
package's again and dpkg stops asking on upgrade. :func:`transform` always
starts from :func:`restore`, so any mode reaches any other without edits
stacking. An anchor that is not there is a refusal, never a guess.
"""

from __future__ import annotations

import difflib
import re

from hammunition.gpstime import files
from hammunition.gpstime.mode import ROUTE, Mode, Route, TimeError, as_mode

__all__ = ["OFF", "WAS", "changes", "restore", "transform"]

OFF = "#hammunition-gps:off# "
WAS = "#hammunition-gps:was# "
TOS_LINE = re.compile(r"tos\s+minclock\s+\d+\s+minsane\s+\d+\s*")
SOURCE_LINE = re.compile(r"(?:pool|server)\s+\S.*")


def _split(text: str) -> tuple[list[str], bool]:
    return text.splitlines(), text.endswith("\n")


def _join(lines: list[str], trailing: bool) -> str:
    return "\n".join(lines) + ("\n" if trailing and lines else "")


def _preferred(line: str) -> str:
    return f"{line.rstrip()} prefer"


def restore(text: str) -> str:
    """``text`` with every Hammunition edit undone exactly."""
    lines, trailing = _split(text)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(OFF):
            out.append(line[len(OFF) :])
            i += 1
            continue
        if line.startswith(WAS):
            original = line[len(WAS) :]
            follower = lines[i + 1] if i + 1 < len(lines) else None
            if follower != _preferred(original):
                raise TimeError(
                    f"{files.NTP_CONF} line {i + 2} should read {_preferred(original)!r}, the "
                    f"copy Hammunition made of line {i + 1}, and reads {follower!r}: it was "
                    f"edited by hand. Put line {i + 1} back without its {WAS.strip()!r} "
                    f"prefix, delete line {i + 2}, and try again. Nothing was changed."
                )
            out.append(original)
            i += 2
            continue
        out.append(line)
        i += 1
    return _join(out, trailing)


def transform(text: str, mode: Mode, route: Route = ROUTE) -> str:
    """ntp.conf as ``mode`` needs it, from whatever mode ``text`` was left in."""
    mode = as_mode(mode)
    lines, trailing = _split(restore(text))
    tos_off = mode != "ntp-only" and not route.tos_in_ntp_d
    sources_off = mode == "gps-only"
    sources_prefer = mode == "auto" and route.auto_prefers_pools

    if tos_off and not any(TOS_LINE.fullmatch(ln) for ln in lines):
        raise TimeError(
            f"{files.NTP_CONF} has no line of the form `tos minclock N minsane N`. That "
            f"line stops a lone GPS setting the clock, and mode {mode} disables it; "
            f"without it there is nothing to anchor the edit to. Nothing was changed."
        )
    if (sources_off or sources_prefer) and not any(SOURCE_LINE.fullmatch(ln) for ln in lines):
        verb = "disable" if sources_off else "prefer"
        raise TimeError(
            f"{files.NTP_CONF} has no `pool` or `server` line for mode {mode} to {verb}. "
            f"Nothing was changed."
        )

    out: list[str] = []
    for line in lines:
        if (tos_off and TOS_LINE.fullmatch(line)) or (sources_off and SOURCE_LINE.fullmatch(line)):
            out.append(OFF + line)
        elif sources_prefer and SOURCE_LINE.fullmatch(line) and "prefer" not in line.split():
            out += [WAS + line, _preferred(line)]
        else:
            out.append(line)
    return _join(out, trailing)


def changes(before: str, after: str) -> list[str]:
    """The lines that leave and arrive, as ``- line`` and ``+ line``, for the plan."""
    return [
        ln
        for ln in difflib.ndiff(before.splitlines(), after.splitlines())
        if ln.startswith(("- ", "+ "))
    ]
