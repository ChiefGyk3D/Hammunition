# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps repeaters import``, ``remove`` and ``list`` as data.  D-064, D-059.

Counts, paths and the layer's name only. Neither document carries a
repeater's callsign or position: the operator's export says where they
operate, and these are the kind of output that gets pasted into an issue.
``list`` is the exception, for programs: it carries every row, and its text
does not."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hammunition.interface.envelope import Strict, described
from hammunition.interface.text import wrap

__all__ = [
    "AllSourcesView",
    "CentreView",
    "InputView",
    "LayerSkipView",
    "LayerView",
    "RegistrationView",
    "RepeatersDocument",
    "RepeatersListDocument",
    "RepeatersRemovedDocument",
    "RowView",
    "SkipView",
    "render_all_sources",
    "render_removed",
    "render_repeaters",
    "render_repeaters_list",
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
        "`direwolf-log` (D-074); `acma-register` (D-074, amended 2026-10-01)"
    )
    read: int = described(
        "rows, objects, devices or waypoints in it; for `acma-register`, the transmitters "
        "on amateur repeater licences"
    )
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
    layers: tuple[str, ...] = described("the layer ids joined, in layer order")
    written: int = described("repeaters in it")
    merged: int = described(
        "rows joined to another layer's: the same output frequency, and within 0.02 "
        "degree, or the same callsign within 0.25 degree"
    )
    skipped: tuple[LayerSkipView, ...] = described("layers that could not be read")
    error: str | None = described(
        "why the file could not be rebuilt (the command then exits 1); null when it was"
    )


@dataclass(frozen=True)
class RepeatersDocument(Strict):
    """A repeater layer written from the operator's own export, hearham's
    list on request (D-064), or one of D-074's sources. Counts and paths
    only: no repeater's callsign or position, and no region, is carried."""

    KIND: ClassVar[str] = "repeaters"

    layer_id: str = described(
        "`export` (D-064's layer), `open-repeater`, `osm`, `etcc`, `brandmeister` or "
        "`aprs-heard` (D-074), `acma` (D-074, amended 2026-10-01), `repeaterbook-<AREA>` "
        "(one per state, #325)"
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


@dataclass(frozen=True)
class LayerView(Strict):
    """One layer read from the overlay directory."""

    id: str = described(
        "the layer's id: `export`, `acma`, `open-repeater`, `osm`, `etcc`, `brandmeister`, "
        "`aprs-heard`, `repeaterbook` (the earlier merged layer) or `repeaterbook-<AREA>`, one "
        "per state (`repeaterbook-OH`; RepeaterBook's `state_id` outside the US)"
    )
    area: str | None = described(
        "the `<AREA>` of a per-state layer (`OH`, `CA01`), null for every other layer, so a "
        "front end can group by it"
    )
    name: str = described("the layer's name, as QMapShack's project shows it")
    description: str = described("the layer's description, which carries each source's licence")
    day: str = described("YYYY-MM-DD: the layer's date")
    rows: int = described("repeaters in the layer")
    sources: tuple[str, ...] = described(
        "the distinct sources of its rows, as `repeaterbook-api`, `open-repeater-json` and the like"
    )
    personal_use: bool = described(
        "true when any source is RepeaterBook's: its terms keep the rows on this machine (D-081)"
    )
    unverified: bool = described(
        "true when any source is one the engine records as unverified: hearham, ETCC, "
        "Brandmeister, the ACMA register, RepeaterBook's API"
    )
    files: tuple[str, ...] = described("the layer's files that exist: GPX, POI, Navit, rows")


@dataclass(frozen=True)
class CentreView(Strict):
    """The point distances and bearings are measured from."""

    lat: float = described("degrees north")
    lon: float = described("degrees east")
    source: str = described(
        "`argument` (`--near`) or `station` (the station's grid square: the centre of its "
        "square, so a program that shows this is showing the operator's area)"
    )


@dataclass(frozen=True)
class RowView(Strict):
    """One repeater, after the layers were joined."""

    callsign: str = described("empty only for a waypoint whose name gave none")
    output_hz: int = described("output frequency in Hz; 0 only when a waypoint gave none")
    offset_hz: int | None = described("transmit minus receive in Hz, signed; null when unknown")
    tone: str = described("CTCSS in Hz as text; empty for none")
    mode: str = described(
        "`FM`, `FM, DMR` and the like: `modes` joined, or the source's own words when they "
        "say more than the vocabulary does; empty when unknown"
    )
    modes: tuple[str, ...] = described(
        "what it speaks, from `FM`, `DMR`, `D-STAR`, `YSF`, `P25`, `NXDN`, `M17`, `TETRA`, "
        "`ATV`, in that order; empty when the source says nothing or says a word outside "
        "the list (which stays in `mode`)"
    )
    band: str = described(
        "`10m`, `6m`, `2m`, `1.25m`, `70cm`, `33cm`, `23cm`, `13cm` from the output "
        "frequency, else `other`"
    )
    digital: dict[str, str] = described(
        "digital details the source supplied, never invented: `dmr_color_code`, "
        "`dmr_network`, `dmr_id`, `dstar_module`, `dstar_gateway`, `ysf_dgid`, `p25_nac`, "
        "`nxdn_ran`; empty when it supplied none"
    )
    distance_km: float | None = described(
        "great-circle kilometres from `centre` (haversine, 6371.0088 km sphere); null "
        "when there is no centre"
    )
    bearing_deg: float | None = described(
        "initial bearing from `centre` in degrees, 0 to 360, 0 north; null when there is no centre"
    )
    place: str = described("where it is, as the source says")
    notes: str = described("the source's notes")
    use: str = described("`OPEN`, `CLOSED` and the like; empty when unknown")
    status: str = described("the source's status; empty when unknown")
    updated: str = described("when the source last updated it; empty when unknown")
    label: str = described("a waypoint's name, when it gave no callsign or frequency")
    lat: float = described("degrees north")
    lon: float = described("degrees east")
    source: str = described("the source of the row kept, best first (D-074's precedence)")
    also: tuple[str, ...] = described("other sources that list the same machine, best first")
    layer: str = described("the id of the layer the kept row came from")
    personal_use: bool = described(
        "true when the source or any of `also` is RepeaterBook's: do not serve this row "
        "beyond the machine (D-081)"
    )


@dataclass(frozen=True)
class RepeatersListDocument(Strict):
    """The repeater layers on this machine, read back, for a program. Read-only:
    nothing is written, fetched or rebuilt. A layer that cannot be read is in
    `skipped` and the rest is returned, with exit 0; an empty directory is an
    empty document. Carries every row, so it is for local programs, not for
    pasting. D-074 (amended 2026-10-04)."""

    KIND: ClassVar[str] = "repeaters-list"

    directory: str = described("where the layers are")
    layers: tuple[LayerView, ...] = described(
        "every layer read, in layer order, the heard layer (`aprs-heard`) included"
    )
    skipped: tuple[LayerSkipView, ...] = described(
        "layers asked for or present that were not read, and why: no rows file, an unreadable "
        "one, an id that is not a layer, a layer not present"
    )
    rows: tuple[RowView, ...] = described(
        "the layers joined as `repeaters-all.gpx` is (D-074), in memory, without the heard layer"
    )
    merged: int = described("rows joined to another layer's")
    credits: tuple[str, ...] = described(
        "one attribution or licence text per distinct source present, to print beside the map"
    )
    centre: CentreView | None = described(
        "where distances are measured from: `--near`, else the station's grid square when "
        "one is set; null when neither, and every row's `distance_km` is then null"
    )
    within_km: float | None = described(
        "`--within`: rows farther than this from `centre` were left out; null when not asked"
    )


_NUMBERED = {
    "hand-csv": "lines",
    "repeaterbook-csv": "lines",
    "hearham-json": "rows",
    "open-repeater-json": "entries",
    "osm-extract": "objects",
    "etcc-csv": "lines",
    "brandmeister-json": "devices",
    "direwolf-log": "lines",
    "acma-register": "lines",
}


def render_all_sources(view: AllSourcesView) -> list[str]:
    lines = []
    if view.file is not None:
        lines.append(
            f"All sources: {view.written} repeaters from layers {', '.join(view.layers)}, "
            f"{view.merged} joined across sources (same frequency, and within 0.02 degree "
            f"or the same callsign within 0.25 degree), in {view.file}"
        )
    lines += [f"All sources: left out layer {s.layer}: {s.reason}" for s in view.skipped]
    if view.error is not None:
        lines.append(f"All sources: {view.error}")
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


def _row_line(row: RowView) -> str:
    from hammunition.repeaters import keying_line

    where = ""
    if row.distance_km is not None and row.bearing_deg is not None:
        where = f"{row.distance_km:6.1f} km {_compass(row.bearing_deg):<2}  "
    name = row.callsign or row.label
    keying = keying_line(
        row.output_hz, row.offset_hz, row.tone, row.modes or ((row.mode,) if row.mode else ())
    )
    parts = [f"{where}{name:<8} {row.band:<5} {keying}"]
    parts += [f"{k} {v}" for k, v in row.digital.items()]
    if row.place:
        parts.append(row.place)
    return "  " + "  ".join(p for p in parts if p)


def _compass(bearing: float) -> str:
    from hammunition.repeaters import compass

    return compass(bearing)


def render_repeaters_list(doc: RepeatersListDocument, rows: bool = False) -> list[str]:
    """``maps repeaters list`` as the terminal shows it: the layers, not the
    rows, unless the operator asked for a place, a band or a mode (*rows*), when
    the repeaters that match are listed, nearest first."""
    lines = [f"Repeater layers in {doc.directory}:"]
    if not doc.layers and not doc.skipped:
        return [f"No repeater layers in {doc.directory}."]
    for layer in doc.layers:
        line = f"  {layer.id}  {layer.rows}  {layer.day}  {layer.name}"
        if layer.personal_use:
            line += "  personal use"
        if layer.unverified:
            line += "  unverified"
        lines.append(line)
    lines += [f"  left out {s.layer}: {s.reason}" for s in doc.skipped]
    if rows:
        lines.append("")
        if doc.centre is not None:
            lines.append(
                f"Repeaters, nearest first from {doc.centre.lat:.4f}, {doc.centre.lon:.4f} "
                f"({'--near' if doc.centre.source == 'argument' else 'the station grid square'})"
                + (f", within {doc.within_km:g} km" if doc.within_km is not None else "")
                + ":"
            )
        else:
            lines.append("Repeaters (no position given, so no distances):")
        lines += [_row_line(r) for r in doc.rows] or ["  none match"]
        lines.append("")
    lines.append(
        f"{len(doc.rows)} repeaters across {len(doc.layers)} layers "
        f"({doc.merged} merged across sources)"
    )
    for text in doc.credits:
        lines += ["", *wrap(text, indent="")]
    return lines
