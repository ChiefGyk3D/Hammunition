# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The first-run checklist (spec section 6). Pure: documents in, steps out. State is
never stored, so the checklist is always true; skipping lasts for the session."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

STARTER = "station"
MARK = {"done": "[x]", "todo": "[ ]", "unknown": "[?]", "skipped": "[-]"}


@dataclass(frozen=True)
class Step:
    number: int
    key: str
    label: str
    state: str
    detail: str


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _starter(catalog: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    for entry in (catalog or {}).get("profiles") or []:
        if isinstance(entry, dict) and entry.get("name") == STARTER:
            return entry
    return None


def steps(
    station: Mapping[str, Any] | None, catalog: Mapping[str, Any] | None, skipped: Collection[str]
) -> list[Step]:
    if station is None:
        s1, d1 = "unknown", "reading the station"
    elif station.get("callsign") is not None and station.get("grid_square") is not None:
        s1, d1 = "done", "the engine has your callsign and grid square"
    else:
        s1, d1 = "todo", "the engine needs your callsign and grid square; Enter opens Station"
    entry = _starter(catalog)
    known = entry is not None and _int(entry.get("members")) and _int(entry.get("installed"))
    if known and entry is not None:
        s3 = "done" if entry["installed"] >= 1 else "todo"
        s4 = "done" if entry["members"] > 0 and entry["installed"] == entry["members"] else "todo"
        d3 = f"the {STARTER} profile is the floor everything stands on; Enter opens Install with it selected"
        d4 = f"{entry['installed']} of {entry['members']} of its units installed; Enter shows the plan"
    else:
        s3 = s4 = "unknown"
        d3 = d4 = "the engine does not report installed state yet"
    raw = [
        (1, "station", "Set your station", s1, d1),
        (
            2,
            "hardware",
            "Apply the hardware rules",
            "unknown",
            "the engine does not yet report whether the udev rules and groups are applied; Enter shows the command, which prints its own plan",
        ),
        (3, "pick", "Pick a profile", s3, d3),
        (4, "install", f"Install {STARTER}", s4, d4),
    ]
    return [
        Step(n, k, label, "skipped" if k in skipped and st != "done" else st, d)
        for n, k, label, st, d in raw
    ]


def show_checklist(items: list[Step]) -> bool:
    return any(s.state in ("todo", "unknown") for s in items)
