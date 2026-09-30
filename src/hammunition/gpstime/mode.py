# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The time mode, its file, and the ntp.d file it becomes.  D-058.

The maintainer's rules: ``auto`` is the default, the mode persists until
changed, and a parked receiver never feeds the clock whatever the mode says.
The last needs nothing here: a parked receiver's SHM segment stops updating
and ntpd drops it from selection by its own reachability rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from hammunition.gpstime import files

__all__ = [
    "DEFAULT_MODE",
    "GPS_MODES",
    "HELPER_HEADER",
    "MODES",
    "NMEA_TIME1",
    "ROUTE",
    "Mode",
    "Route",
    "TimeError",
    "as_mode",
    "parse_mode_file",
    "read_mode",
    "render_mode_file",
    "render_ntp_d",
]

Mode = Literal["auto", "prefer-gps", "ntp-only", "gps-only"]
MODES: tuple[Mode, ...] = ("auto", "prefer-gps", "ntp-only", "gps-only")
DEFAULT_MODE: Mode = "auto"
GPS_MODES: frozenset[Mode] = frozenset({"auto", "prefer-gps", "gps-only"})

HELPER_HEADER = "# Written by hammunition-devctl (D-058)"
"""The first line of every file the helper writes; `hardware unapply` removes a
file only when it starts with this."""

NMEA_TIME1 = "0.000"
"""Seconds added to the GPS's NMEA time to correct its latency over USB. Zero is
"no correction"; Task 9 measures the offset against the network and sets it."""

REFCLOCK = "refclock shm unit 0 refid GPS time1 {time1}"


class TimeError(Exception):
    """A time mode could not be read, planned or applied. The message says why and what to do."""


@dataclass(frozen=True)
class Route:
    """How a mode is expressed to ntpsec. Both fields rest on bench measurements
    (spec §4b; plan Task 9), and the code implements both ways of each."""

    tos_in_ntp_d: bool
    """True: ``tos minclock 1 minsane 1`` in the ntp.d file overrides ntp.conf's
    ``tos minclock 4 minsane 3``. False: that ntp.conf line is disabled with the
    marker instead."""

    auto_prefers_pools: bool
    """True: in ``auto`` each ntp.conf ``pool``/``server`` line gets ``prefer``."""


ROUTE = Route(tos_in_ntp_d=False, auto_prefers_pools=True)
"""Until Task 9: the conffile edit, which ntpsec documents, not the override,
which it does not; and the spec's own description of ``auto``."""


def as_mode(value: object) -> Mode:
    if isinstance(value, str) and value in MODES:
        return value
    raise TimeError(f"{value!r} is not a time mode. The modes are: {', '.join(MODES)}.")


def render_mode_file(mode: Mode) -> str:
    return f"{HELPER_HEADER}. Change it with `hammunition time mode`.\nmode: {as_mode(mode)}\n"


def parse_mode_file(text: str) -> Mode:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TimeError(
            f"{files.TIME_CONFIG} is not YAML ({exc}). `hammunition time mode MODE` rewrites it."
        ) from exc
    if not isinstance(data, dict) or set(data) != {"mode"}:
        raise TimeError(
            f"{files.TIME_CONFIG} should hold exactly one key, `mode`, and holds {data!r}. "
            f"`hammunition time mode MODE` rewrites it."
        )
    return as_mode(data["mode"])


def read_mode() -> tuple[Mode, bool]:
    """The mode, and whether the operator ever set it (unset reads as ``auto``)."""
    try:
        text = Path(files.TIME_CONFIG).read_text(encoding="utf-8")
    except FileNotFoundError:
        return DEFAULT_MODE, False
    return parse_mode_file(text), True


def render_ntp_d(mode: Mode, route: Route = ROUTE) -> str:
    """The whole of the ntp.d file for ``mode``. Nothing in it comes from anywhere else."""
    mode = as_mode(mode)
    head = (
        f"{HELPER_HEADER} for time mode {mode}.\n"
        "# Rewritten whole by `hammunition time mode`; change the mode, not this file.\n"
    )
    if mode == "ntp-only":
        return head + "# ntp-only: no GPS refclock, so the clock follows network servers only.\n"
    refclock = REFCLOCK.format(time1=NMEA_TIME1)
    if mode == "auto":
        refclock += " stratum 10"
    elif mode == "prefer-gps":
        refclock += " prefer"
    body = refclock + "\n"
    if route.tos_in_ntp_d:
        body += "tos minclock 1 minsane 1\n"
    return head + body
