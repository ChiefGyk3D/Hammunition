# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Measure the GPS takeover, read-only.  Issue #310, D-058.

``hammunition time measure --minutes N`` samples ``ntpq -pn`` and says, per
sample, what ntpd follows, the GPS refclock's reach and offset, and the best
network peer's; and at the end whether the GPS ever became the system peer and
how long that took. ``--pps`` adds a ``ppstest`` run on ``/dev/pps0`` and says
whether the pulses are real.

It asks ntpq and reads sysfs, and runs ``ppstest`` (which only reads the PPS
device). It writes nothing, changes no mode and no power state. Run it with the
network off to measure the takeover; with the network on, ntpd rejects the GPS
by design (D-058) and the answer is "never selected".
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from hammunition.gpstime.state import Peer, _is_gps, _selected, parse_peers

__all__ = [
    "PpsResult",
    "Sample",
    "Summary",
    "describe_sample",
    "measure",
    "pps_devices",
    "run_ppstest",
    "sample",
    "summarise",
]

_RANK = {"*": 0, "o": 0, "+": 1, "#": 2, "-": 3, "x": 4, ".": 5, " ": 6, "~": 6}
_ASSERT = re.compile(r"assert\s+([0-9.]+),\s*sequence:\s*(\d+)")


@dataclass(frozen=True)
class Sample:
    elapsed: float
    """Seconds since the first sample."""
    selected: str | None
    """The remote ntpd follows, ``None`` when it follows nothing."""
    gps: Peer | None
    network: Peer | None
    """The best network peer: the selected one, else the best-ranked by tally."""
    gps_selected: bool
    network_reaching: int
    network_total: int


def sample(ntpq_text: str, elapsed: float) -> Sample:
    peers = parse_peers(ntpq_text)
    gps = next((p for p in peers if _is_gps(p)), None)
    network_peers = [p for p in peers if not _is_gps(p)]
    chosen = _selected(peers)
    best = None
    if network_peers:
        best = min(network_peers, key=lambda p: (_RANK.get(p.tally, 6), p.remote))
    return Sample(
        elapsed=elapsed,
        selected=None if chosen is None else chosen.remote,
        gps=gps,
        network=best,
        gps_selected=chosen is not None and _is_gps(chosen),
        network_reaching=sum(1 for p in network_peers if p.reach not in ("0", "")),
        network_total=len(network_peers),
    )


def _peer(p: Peer | None) -> str:
    if p is None:
        return "absent"
    offset = "n/a" if p.offset_ms is None else f"{p.offset_ms:+.3f} ms"
    return f"{p.tally or ' '}{p.remote} reach {p.reach} offset {offset}"


def describe_sample(s: Sample) -> str:
    follows = "nothing" if s.selected is None else s.selected
    return (
        f"t+{s.elapsed:5.0f}s  follows {follows}  | GPS {_peer(s.gps)}  | "
        f"network {_peer(s.network)} ({s.network_reaching}/{s.network_total} reaching)"
    )


@dataclass(frozen=True)
class Summary:
    samples: int
    gps_seen: bool
    gps_selected_at: float | None
    """Seconds into the run when the GPS first became the system peer."""
    gps_selected_last: bool
    gps_reach_last: str | None
    gps_offset_range_ms: tuple[float, float] | None
    network_ever_reaching: bool
    network_gone_at: float | None
    """Seconds in when no network peer was reaching for the first time."""


def summarise(samples: list[Sample]) -> Summary:
    offsets = [
        s.gps.offset_ms for s in samples if s.gps is not None and s.gps.offset_ms is not None
    ]
    selected_at = next((s.elapsed for s in samples if s.gps_selected), None)
    gone = next((s.elapsed for s in samples if s.network_total and s.network_reaching == 0), None)
    last = samples[-1] if samples else None
    return Summary(
        samples=len(samples),
        gps_seen=any(s.gps is not None for s in samples),
        gps_selected_at=selected_at,
        gps_selected_last=bool(last and last.gps_selected),
        gps_reach_last=None if last is None or last.gps is None else last.gps.reach,
        gps_offset_range_ms=(min(offsets), max(offsets)) if offsets else None,
        network_ever_reaching=any(s.network_reaching for s in samples),
        network_gone_at=gone,
    )


def verdict(summary: Summary) -> list[str]:
    out = [f"{summary.samples} sample(s)."]
    if not summary.gps_seen:
        out.append(
            "The GPS refclock never appeared in `ntpq -pn`: GPS time is not configured "
            "(`hammunition time` says why; `hammunition hardware apply` installs it)."
        )
        return out
    if summary.gps_offset_range_ms is not None:
        low, high = summary.gps_offset_range_ms
        out.append(
            f"GPS offset ranged {low:+.3f} to {high:+.3f} ms; last reach {summary.gps_reach_last}."
        )
    if summary.gps_selected_at is not None:
        out.append(f"The GPS became the system peer {summary.gps_selected_at:.0f} s into the run.")
        if not summary.gps_selected_last:
            out.append("It was not the system peer at the last sample.")
    elif summary.network_gone_at is None:
        out.append(
            "The GPS was never the system peer, and network peers were reaching throughout: "
            "ntpd rejects the GPS while it has network peers (D-058, by design). "
            "Measure the takeover with the network off."
        )
    else:
        out.append(
            f"No network peer was reaching from {summary.network_gone_at:.0f} s on, "
            "and the GPS was never the system peer in the time measured: run longer "
            "(ntpd drops an unreachable peer slowly) and record how long."
        )
    return out


def measure(
    read_ntpq: Callable[[], str | None],
    *,
    minutes: float,
    interval: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    emit: Callable[[str], None] = print,
) -> list[Sample] | None:
    """Sample every ``interval`` seconds for ``minutes``; ``None`` when ntpq never answers.

    The first sample is at t+0 and the last at or before ``minutes``. An
    interrupt ends the run with what has been collected so far.
    """
    total = max(1, int(minutes * 60 // interval) + 1)
    samples: list[Sample] = []
    try:
        for index in range(total):
            text = read_ntpq()
            if text is None:
                emit(f"t+{index * interval:5.0f}s  ntpq did not answer")
            else:
                s = sample(text, index * interval)
                samples.append(s)
                emit(describe_sample(s))
            if index + 1 < total:
                sleep(interval)
    except KeyboardInterrupt:
        emit("interrupted; summarising what was collected")
    return samples or None


# ---- PPS --------------------------------------------------------------------


@dataclass(frozen=True)
class PpsResult:
    device_present: bool
    devices: tuple[str, ...]
    """``pps0 (name, path)`` per entry of /sys/class/pps."""
    ppstest: str | None
    """The ppstest binary, ``None`` when not installed."""
    pulses: int
    """Assert events whose sequence number advanced."""
    seconds: float
    error: str | None
    lines: tuple[str, ...]


def pps_devices(sysfs: str = "/sys", dev: str = "/dev") -> tuple[bool, tuple[str, ...]]:
    root = Path(sysfs) / "class" / "pps"
    found: list[str] = []
    try:
        entries = sorted(p for p in root.iterdir() if p.name.startswith("pps"))
    except OSError:
        entries = []

    def read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return "?"

    for entry in entries:
        found.append(f"{entry.name} (name {read(entry / 'name')}, path {read(entry / 'path')})")
    return Path(dev, "pps0").exists(), tuple(found)


def run_ppstest(
    seconds: float = 60.0,
    *,
    device: str = "/dev/pps0",
    sysfs: str = "/sys",
    dev: str = "/dev",
) -> PpsResult:
    present, listed = pps_devices(sysfs, dev)
    binary = shutil.which("ppstest")
    if binary is None:
        return PpsResult(
            present, listed, None, 0, seconds, "ppstest is not installed (package pps-tools)", ()
        )
    if not present:
        return PpsResult(present, listed, binary, 0, seconds, f"{device} does not exist", ())
    argv = [binary, device]
    stdbuf = shutil.which("stdbuf")
    if stdbuf is not None:
        argv = [stdbuf, "-oL", *argv]  # ppstest block-buffers a pipe; a kill would lose it
    ended_early = False
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=seconds, check=False)
        output = (done.stdout or "") + (done.stderr or "")
        ended_early = True
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout if exc.stdout is not None else b""
        output = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        err = exc.stderr if exc.stderr is not None else b""
        output += err.decode("utf-8", "replace") if isinstance(err, bytes) else err
    except OSError as exc:
        return PpsResult(present, listed, binary, 0, seconds, str(exc), ())
    lines = tuple(output.splitlines())
    sequences = [int(m.group(2)) for line in lines if (m := _ASSERT.search(line))]
    pulses = sum(1 for a, b in pairwise(sequences) if b > a)
    if sequences:
        pulses += 1
    failure = None
    if ended_early:
        said = lines[-1] if lines else "nothing"
        failure = f"ppstest ended before {seconds:g} s, saying: {said}"
    elif pulses == 0:
        failure = (
            "no pulses: ppstest only timed out or printed errors"
            if lines
            else "ppstest printed nothing in the time"
        )
    return PpsResult(present, listed, binary, pulses, seconds, failure, lines[-5:])
