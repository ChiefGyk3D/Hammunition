# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps repeaters import`` and ``maps repeaters remove`` as data.  D-064, D-059.

Counts, paths and the layer's name only. Neither document carries a
repeater's callsign or position: the operator's export says where they
operate, and these are the kind of output that gets pasted into an issue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hammunition.interface.envelope import Strict, described
from hammunition.interface.text import wrap

__all__ = [
    "AllSourcesView",
    "InputView",
    "LayerSkipView",
    "RegistrationView",
    "RepeatersDocument",
    "RepeatersRemovedDocument",
    "SkipView",
    "render_all_sources",
    "render_removed",
    "render_repeaters",
]


@dataclass(frozen=True)
class SkipView(Strict):
    """Rows of one input left out for one reason."""

    reason: str = described("why, e.g. `no usable position` or `no callsign`")
    count: int = described("how many rows")
    first: tuple[int, ...] = described(
        "the first five: line numbers in a CSV, row numbers in JSON, waypoint numbers in a GPX"
    )


@dataclass(frozen=True)
class InputView(Strict):
    """One file read."""

    path: str = described(
        "the file as given; a fetch's URL; for `osm-extract`, the directory of the region "
        "extracts, never a region's name"
    )
    format: str = described(
        "`repeaterbook-gpx`, `repeaterbook-csv`, `hearham-json` or `hand-csv` (D-064); "
        "`open-repeater-json`, `osm-extract`, `etcc-csv`, `brandmeister-json` or "
        "`direwolf-log` (D-074)"
    )
    read: int = described("rows, objects, devices or waypoints in it")
    used: int = described("of those, the ones kept: a position and a callsign or frequency")
    skipped: tuple[SkipView, ...] = described("the rest, by reason")
    sha256: str = described(
        "the digest of what was read (several logs: of their bytes in order); empty for "
        "`osm-extract`, whose extracts' digests would name the regions"
    )


@dataclass(frozen=True)
class RegistrationView(Strict):
    """What a program was told about the layer."""

    program: str = described("`qmapshack` or `navit`")
    config: str = described("the file edited or written")
    outcome: str = described(
        "`added`, `already there`, `written`, `removed`, `not there`, `not written` or `refused`"
    )
    detail: str = described("the sentence the text prints after the outcome")


@dataclass(frozen=True)
class LayerSkipView(Strict):
    """A layer the all-sources file could not read."""

    layer: str = described("the layer's id")
    reason: str = described("why it was left out")


@dataclass(frozen=True)
class AllSourcesView(Strict):
    """``repeaters-all.gpx``: the directory layers joined (D-074)."""

    file: str | None = described(
        "the file, mode 0600; null when fewer than two directory layers could be read, "
        "and the file is then absent"
    )
    name: str = described("its name, `Repeaters (all sources, YYYY-MM-DD)`; empty when null")
    layers: tuple[str, ...] = described("the layer ids joined, in precedence order")
    written: int = described("repeaters in it")
    merged: int = described(
        "rows joined to another source's: same output frequency and the same callsign "
        "or within 0.02 degree"
    )
    skipped: tuple[LayerSkipView, ...] = described("layers that could not be read")


@dataclass(frozen=True)
class RepeatersDocument(Strict):
    """A repeater layer written from the operator's own export, hearham's
    list on request (D-064), or one of D-074's sources. Counts and paths
    only: no repeater's callsign or position, and no region, is carried."""

    KIND: ClassVar[str] = "repeaters"

    layer_id: str = described(
        "`export` (D-064's layer), `open-repeater`, `osm`, `etcc`, `brandmeister` or "
        "`aprs-heard` (D-074)"
    )
    layer: str = described("the layer's name, as QMapShack's project and POI file show it")
    exported: str = described(
        "YYYY-MM-DD: `--exported`, else the oldest input's modification date; a fetch's own date"
    )
    licences: tuple[str, ...] = described("each source's licence text, printed before anything")
    inputs: tuple[InputView, ...] = described("each file read, in the order given")
    read: int = described("rows read over every input")
    skipped: int = described("rows left out over every input")
    merged: int = described(
        "rows merged into another: same callsign, output frequency and position to 0.01 degree"
    )
    written: int = described("repeaters in the layer")
    directory: str = described("where the layer's files are, mode 0700")
    files: tuple[str, ...] = described(
        "the files written, mode 0600: GPX, POI, Navit textfile and the rows as data"
    )
    registered: tuple[RegistrationView, ...] = described(
        "QMapShack's and Navit's, in that order, for every layer present"
    )
    all_sources: AllSourcesView = described("the all-sources file, rebuilt after the write")


@dataclass(frozen=True)
class RepeatersRemovedDocument(Strict):
    """Repeater layers deleted and unregistered. Removing nothing is not an
    error: every list is then empty."""

    KIND: ClassVar[str] = "repeaters-removed"

    directory: str = described("where the layers are")
    layers: tuple[str, ...] = described(
        "the layer ids asked for: the one `--layer` named, else every layer"
    )
    removed: tuple[str, ...] = described("the files deleted")
    unregistered: tuple[RegistrationView, ...] = described(
        "QMapShack's and Navit's, in that order, for the layers left"
    )
    all_sources: AllSourcesView = described("the all-sources file, rebuilt from what is left")


_NUMBERED = {
    "hand-csv": "lines",
    "repeaterbook-csv": "lines",
    "hearham-json": "rows",
    "open-repeater-json": "entries",
    "osm-extract": "objects",
    "etcc-csv": "lines",
    "brandmeister-json": "devices",
    "direwolf-log": "lines",
}


def render_all_sources(view: AllSourcesView) -> list[str]:
    lines = []
    if view.file is not None:
        lines.append(
            f"All sources: {view.written} repeaters from layers {', '.join(view.layers)}, "
            f"{view.merged} joined across sources (same frequency, and the same callsign "
            f"or within 0.02 degree), in {view.file}"
        )
    lines += [f"All sources: left out layer {s.layer}: {s.reason}" for s in view.skipped]
    return lines


def _registration(view: RegistrationView) -> str:
    name = {"qmapshack": "QMapShack", "navit": "Navit"}[view.program]
    return f"{name}: {view.detail}"


def render_repeaters(doc: RepeatersDocument) -> list[str]:
    """``maps repeaters import`` as the terminal shows it."""
    lines: list[str] = []
    for text in doc.licences:
        lines += [*wrap(text, indent=""), ""]
    lines.append("Read:")
    for view in doc.inputs:
        lines.append(
            f"  {view.path} ({view.format}): {view.read} rows read, {view.read - view.used} skipped"
        )
        numbered = _NUMBERED.get(view.format, "waypoints")
        for skip in view.skipped:
            if not skip.first:  # several extracts read as one input
                lines.append(f"    {skip.reason}: {skip.count}")
                continue
            more = ", ..." if skip.count > len(skip.first) else ""
            first = ", ".join(str(n) for n in skip.first)
            lines.append(f"    {skip.reason}: {skip.count} ({numbered} {first}{more})")
    lines.append(
        f"Merged: {doc.merged} (same callsign, output frequency and position to 0.01 degree)"
    )
    lines.append(f"Written: {doc.written} repeaters, layer {doc.layer!r}")
    for path in doc.files:
        lines.append(f"  {path}")
    lines += render_all_sources(doc.all_sources)
    lines += [_registration(view) for view in doc.registered]
    lines += [
        "",
        f"QMapShack: File > Load opens {doc.files[0]} as a project; the POI collection is in",
        "the POI Collections dock. Navit: start navit-offline; repeaters list under POIs > Other.",
    ]
    return lines


def render_removed(doc: RepeatersRemovedDocument) -> list[str]:
    """``maps repeaters remove`` as the terminal shows it."""
    if not doc.removed and all(v.outcome == "not there" for v in doc.unregistered):
        return [f"Nothing to remove in {doc.directory}."]
    lines = ["Removed:"] + [f"  {path}" for path in doc.removed]
    lines += render_all_sources(doc.all_sources)
    lines += [_registration(view) for view in doc.unregistered]
    return lines
