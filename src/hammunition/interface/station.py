# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``station show`` as data.  D-059."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from hammunition.interface.envelope import Strict, described
from hammunition.station import STATION_FIELDS, Station

__all__ = ["StationDocument", "build_station", "render_station"]


@dataclass(frozen=True)
class StationDocument(Strict):
    """The saved station values, the values themselves included -- map
    regions among them, per D-057.

    For a local front end filling in a form. Not for pasting into an issue,
    a forum or a chat: a callsign resolves to a name and a licence address,
    and a grid square or a map region says where the station is."""

    KIND: ClassVar[str] = "station"

    path: str = described("the station file")
    file_exists: bool = described("whether that file exists yet")
    callsign: str | None = described("the callsign; null when not set")
    grid_square: str | None = described("the Maidenhead locator; null when not set")
    node_alias: str | None = described("the packet node alias; null when not set")
    map_regions: tuple[str, ...] = described(
        "Geofabrik region paths carrying offline map data; empty when none are set"
    )
    map_freshness: str | None = described(
        "how often map data is refreshed: yearly, monthly or latest; "
        "null means the yearly default applies"
    )
    mirror: str | None = described(
        "the LAN mirror the verified fetch tries before the publisher, the same digest "
        "checked either way (D-070); null when none is set"
    )


def build_station(path: Path, station: Station) -> StationDocument:
    return StationDocument(
        path=str(path),
        file_exists=path.exists(),
        callsign=station.callsign,
        grid_square=station.grid_square,
        node_alias=station.node_alias,
        map_regions=station.map_regions,
        map_freshness=station.map_freshness,
        mirror=station.mirror,
    )


def render_station(doc: StationDocument) -> list[str]:
    """``station show`` as the terminal shows it."""
    lines = [f"Station configuration: {doc.path}"]
    if not doc.file_exists:
        lines.append("  (no file yet)")
    values = {name: getattr(doc, name) for name in sorted(STATION_FIELDS)}
    if (
        not any(values.values())
        and not doc.map_regions
        and doc.map_freshness is None
        and doc.mirror is None
    ):
        return [
            *lines,
            "",
            "Nothing set. `hammunition station set --callsign <yours>` starts it off.",
            "Nothing is invented on your behalf: a configuration file needing a value",
            "you have not given is reported as not written, and the package still installs.",
        ]
    lines.append("")
    lines += [f"  {name:<14} {value if value else '(not set)'}" for name, value in values.items()]
    # Region names reveal where the operator lives, so only a count is ever
    # printed here -- `station show` output is the kind of thing that gets
    # pasted into an issue.
    if doc.map_regions:
        lines.append(f"  {'map regions':<14} {len(doc.map_regions)} set")
    else:
        lines.append(f"  {'map regions':<14} (not set)")
    lines.append(f"  {'map freshness':<14} {doc.map_freshness or 'yearly'}")
    lines.append(f"  {'mirror':<14} {doc.mirror or '(not set)'}")
    return lines
