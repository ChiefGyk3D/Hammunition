# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the clock follows, read without privilege.  D-058.

ntpsec answers ``ntpq -pn`` (the peers, with ``*`` or ``o`` on the one it
follows) and ``ntpq -c rv`` (``reftime``, when it last synchronised, and
``clock``, now) to any local user. Holdover age is ``clock - reftime``.

Always ``-n``: without it ntpq resolves every peer address, and with the
network down that waits on DNS that is not there -- the one situation this
feature exists for.

The same :func:`gather` feeds ``hammunition time``, ``doctor`` and the
helper's ``time state`` JSON the tray polls, so all three say the same thing.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from hammunition.backends.base import BackendError, Command, CommandRunner, SubprocessRunner
from hammunition.gpstime import files
from hammunition.gpstime.mode import DEFAULT_MODE, GPS_MODES, Mode, TimeError, read_mode

if TYPE_CHECKING:  # pragma: no cover
    from hammunition.hardware.power import Parkable

__all__ = [
    "APPARMOR_RULE",
    "GPS_CLASS",
    "HOLDOVER_WARN_SECONDS",
    "JSON_KEYS",
    "Following",
    "GpsState",
    "Peer",
    "TimeState",
    "describe",
    "dhcp_config_in_use",
    "format_duration",
    "gather",
    "gps_from",
    "grants_installed",
    "has_rtc",
    "ntp_time",
    "parse_peers",
    "parse_rv",
    "run_ntpq",
]

Following = Literal["network", "gps", "none", "unknown"]
GpsState = Literal["absent", "awake", "parked"]
GPS_CLASS = "gps-receiver"
APPARMOR_RULE = "capability ipc_owner,"
HOLDOVER_WARN_SECONDS = 86_400

JSON_KEYS: tuple[str, ...] = (
    "mode",
    "mode_set",
    "daemon",
    "gps",
    "following",
    "offset_ms",
    "last_sync",
    "last_source",
    "holdover_seconds",
    "rtc",
    "grants",
    "dhcp_config",
    "problems",
)
"""The object ``hammunition-devctl time state`` prints; hammunition-tray reads it."""


@dataclass(frozen=True)
class Peer:
    tally: str
    remote: str
    refid: str
    reach: str
    offset_ms: float | None


@dataclass(frozen=True)
class TimeState:
    mode: Mode
    mode_set: bool
    daemon: str | None
    gps: GpsState
    following: Following
    offset_ms: float | None
    last_sync: datetime | None
    last_source: str | None
    holdover_seconds: int | None
    rtc: bool
    grants: bool
    dhcp_config: bool
    problems: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "mode_set": self.mode_set,
            "daemon": self.daemon,
            "gps": self.gps,
            "following": self.following,
            "offset_ms": self.offset_ms,
            "last_sync": None if self.last_sync is None else self.last_sync.isoformat(),
            "last_source": self.last_source,
            "holdover_seconds": self.holdover_seconds,
            "rtc": self.rtc,
            "grants": self.grants,
            "dhcp_config": self.dhcp_config,
            "problems": list(self.problems),
        }


def parse_peers(text: str) -> list[Peer]:
    peers: list[Peer] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("remote") or line.startswith("="):
            continue
        fields = line[1:].split()
        if len(fields) < 10:
            continue
        try:
            offset: float | None = float(fields[8])
        except ValueError:
            offset = None
        peers.append(
            Peer(
                tally=line[0], remote=fields[0], refid=fields[1], reach=fields[6], offset_ms=offset
            )
        )
    return peers


def _selected(peers: list[Peer]) -> Peer | None:
    return next((p for p in peers if p.tally in ("*", "o")), None)


def _is_gps(peer: Peer) -> bool:
    return peer.refid == ".GPS." or peer.remote.startswith("SHM(")


_PAIR = re.compile(r'([a-z_]+)=("[^"]*"|[^,\n]*)')


def parse_rv(text: str) -> dict[str, str]:
    return {key: value.strip().strip('"') for key, value in _PAIR.findall(text)}


def ntp_time(value: str | None) -> datetime | None:
    """``ee64fbdf.6ef30ae5 2026-09-28T14:44:47.433Z`` -> a UTC datetime; all-zero -> None."""
    if not value:
        return None
    stamp, _, iso = value.partition(" ")
    if not iso or not stamp.strip("0."):
        return None
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def has_rtc() -> bool:
    try:
        return any(Path(files.RTC_CLASS).iterdir())
    except OSError:
        return False


def grants_installed() -> bool:
    """The drop-in, and where ntpd runs under AppArmor, the local rule."""
    if not Path(files.DROPIN).is_file():
        return False
    if not Path(files.APPARMOR_PROFILE).is_file():
        return True
    try:
        return APPARMOR_RULE in Path(files.APPARMOR_LOCAL).read_text().splitlines()
    except OSError:
        return False


def dhcp_config_in_use() -> bool:
    """True when ntpsec's wrapper would start ntpd on the DHCP-supplied file."""
    if not Path(files.DHCP_CONF).exists():
        return False
    try:
        default = Path(files.NTPSEC_DEFAULT).read_text()
    except OSError:
        return True
    return re.search(r"""^\s*IGNORE_DHCP=["']?yes["']?\s*$""", default, re.MULTILINE) is None


def gps_from(found: Sequence[Parkable]) -> GpsState:
    """From the parkable survey: awake if any GPS receiver is awake."""
    mine = [p for p in found if p.name == GPS_CLASS]
    if not mine:
        return "absent"
    return "awake" if any(not p.parked for p in mine) else "parked"


def run_ntpq(args: tuple[str, ...], runner: CommandRunner | None = None) -> str | None:
    command = Command(argv=("ntpq", *args), description="Ask ntpd what the clock follows")
    try:
        result = (runner or SubprocessRunner()).run(command)
    except BackendError:
        return None
    return result.stdout if result.ok else None


def _now() -> datetime:
    return datetime.now(UTC)


def gather(
    *,
    gps: GpsState,
    ntpq: Callable[[tuple[str, ...]], str | None] = run_ntpq,
    now: Callable[[], datetime] = _now,
) -> TimeState:
    problems: list[str] = []
    try:
        mode, mode_set = read_mode()
    except TimeError as exc:
        mode, mode_set = DEFAULT_MODE, False
        problems.append(str(exc))
    rtc = has_rtc()

    if not Path(files.NTP_CONF).is_file():
        return TimeState(
            mode=mode,
            mode_set=mode_set,
            daemon=None,
            gps=gps,
            following="unknown",
            offset_ms=None,
            last_sync=None,
            last_source=None,
            holdover_seconds=None,
            rtc=rtc,
            grants=False,
            dhcp_config=False,
            problems=tuple(problems),
        )

    following: Following = "unknown"
    offset: float | None = None
    last: datetime | None = None
    source: str | None = None
    holdover: int | None = None
    peers_text = ntpq(("-pn",))
    rv_text = ntpq(("-c", "rv"))
    if peers_text is None or rv_text is None:
        problems.append(
            "ntpq got no answer from ntpd; `systemctl status ntpsec` says whether it is running"
        )
    else:
        peer = _selected(parse_peers(peers_text))
        rv = parse_rv(rv_text)
        last = ntp_time(rv.get("reftime"))
        clock = ntp_time(rv.get("clock")) or now()
        if last is not None:
            source = "gps" if rv.get("refid", "") in ("GPS", ".GPS.") else "network"
        if peer is None:
            following = "none"
            holdover = None if last is None else max(0, int((clock - last).total_seconds()))
        else:
            following = "gps" if _is_gps(peer) else "network"
            offset = peer.offset_ms

    return TimeState(
        mode=mode,
        mode_set=mode_set,
        daemon="ntpsec",
        gps=gps,
        following=following,
        offset_ms=offset,
        last_sync=last,
        last_source=source,
        holdover_seconds=holdover,
        rtc=rtc,
        grants=grants_installed(),
        dhcp_config=dhcp_config_in_use(),
        problems=tuple(problems),
    )


def format_duration(seconds: int) -> str:
    minutes = seconds // 60
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


def _offset(t: TimeState) -> str:
    return "" if t.offset_ms is None else f" (offset {t.offset_ms:+.1f} ms)"


def describe(t: TimeState) -> list[str]:
    """Plain sentences for ``hammunition time``. The tray words the same facts itself."""
    lines = [f"Time mode: {t.mode}" + ("" if t.mode_set else " (the default; never set)")]
    if t.daemon is None:
        lines.append(
            "This machine's time daemon is not ntpsec, and only ntpsec can take time from "
            "a GPS here (D-058). No daemon is switched for you; the mode is kept for when "
            "one can use it."
        )
    if t.gps == "absent":
        tail = f"; {t.mode} takes effect when one is" if t.mode in GPS_MODES else ""
        lines.append(f"GPS receiver: none attached{tail}")
    elif t.gps == "parked":
        lines.append("GPS receiver: parked, so GPS time is off until it is woken")
    else:
        lines.append("GPS receiver: awake")

    if t.following == "network":
        lines.append("The clock follows: the network" + _offset(t))
    elif t.following == "gps":
        lines.append(
            "The clock follows: the GPS"
            + _offset(t)
            + ". NMEA over USB is good to tens of milliseconds: fine for FT8 and logs."
        )
    elif t.following == "none" and t.last_sync is None:
        lines.append("The clock follows: nothing, and ntpd has not synchronised since it started")
    elif t.following == "none" and t.last_sync is not None:
        src = "the GPS" if t.last_source == "gps" else "the network"
        lines.append(
            f"The clock follows: nothing. Holdover since {t.last_sync:%H:%M} UTC "
            f"({format_duration(t.holdover_seconds or 0)}), last synchronised from {src}; "
            f"the hardware clock and ntpd's drift file carry it meanwhile."
        )
    elif t.daemon is not None:
        lines.append("The clock follows: unknown")

    if t.daemon is not None and t.mode in GPS_MODES and not t.grants:
        lines.append(
            "ntpd cannot read gpsd's time yet: `hammunition hardware apply` installs the "
            "two grants it needs."
        )
    if t.dhcp_config:
        lines.append(
            f"ntpd was started on a DHCP-supplied configuration ({files.DHCP_CONF}) instead "
            f"of {files.NTP_CONF}; whether it reads Hammunition's ntp.d file then is not "
            f'measured. Set IGNORE_DHCP="yes" in {files.NTPSEC_DEFAULT} to use the mode.'
        )
    if not t.rtc:
        lines.append(
            "No hardware clock (RTC): after a power-off with no network and no GPS the date "
            "is wrong. Fit a battery-backed RTC module; fake-hwclock, which `hammunition "
            "hardware apply` offers, restores only the last saved time."
        )
    lines += [f"note: {p}" for p in t.problems]
    return lines
