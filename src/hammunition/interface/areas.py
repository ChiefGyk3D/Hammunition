# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps areas`` and ``maps activate`` as data.  D-082, D-059.

An *area* is a US state code or a map region: what an operator loads ahead of
an emergency and switches between on arrival. Both documents name areas
because the operator typed or loaded them; they carry no repeater and no
position. For local programs (the console, Hammunition Hill), not for pasting:
the areas say where the operator may be sent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hammunition.areas import Active, LoadedArea
from hammunition.backends.data import human_size
from hammunition.interface.envelope import Strict, described
from hammunition.interface.repeaters import RegistrationView

__all__ = [
    "ActivateDocument",
    "AreaLayerView",
    "AreaView",
    "AreasDocument",
    "BrowserView",
    "build_areas",
    "render_activate",
    "render_areas",
]


@dataclass(frozen=True)
class AreaLayerView(Strict):
    """One thing loaded for an area."""

    id: str = described(
        "for a state, the repeater layer's id (`repeaterbook-OH`); for a region, `extract` "
        "(the OpenStreetMap extract), `navit` (the converted Navit map) or `tiles` (the "
        "browser map's vector tiles)"
    )
    kind: str = described("`repeaters`, `extract`, `navit` or `tiles`")
    rows: int | None = described("repeaters in the layer; null for a region's files")
    size_bytes: int = described("the layer's files on disk, as the engine measures them")
    day: str | None = described(
        "YYYY-MM-DD: a repeater layer's date; a region's snapshot or file date; null when unknown"
    )
    files: tuple[str, ...] = described("the files that make it up, as they are on disk")


@dataclass(frozen=True)
class AreaView(Strict):
    """One state or region with files on disk."""

    area: str = described(
        "a state code (`OH`, or RepeaterBook's `state_id` outside the US) or a map region "
        "(`north-america/us/ohio`; the file slug when the station no longer names it)"
    )
    kind: str = described("`state` or `region`")
    active: bool = described(
        "whether it is drawn and registered: everything is while `active_areas` is unset. A "
        "state and the region that is the same ground (`OH`, `north-america/us/ohio`) are "
        "active together"
    )
    layers: tuple[AreaLayerView, ...] = described("what is loaded for it")
    size_bytes: int = described("every layer's files together")
    day: str | None = described("the newest layer's date; null when none is known")


@dataclass(frozen=True)
class AreasDocument(Strict):
    """Every area with files on disk, whether it is active, and what is
    always active. Read-only: nothing is written or fetched."""

    KIND: ClassVar[str] = "areas"

    active_areas: tuple[str, ...] | None = described(
        "the station's `active_areas`: null (unset) means everything loaded is active; an "
        "empty list means none is"
    )
    areas: tuple[AreaView, ...] = described("states first, then regions, each by name")
    always_active: tuple[str, ...] = described(
        "the layers that belong to no area (the operator's own import, ACMA, OpenStreetMap's "
        "repeaters, every infrastructure theme today), by layer id: they are registered "
        "whichever areas are active"
    )
    unloaded: tuple[str, ...] = described(
        "entries of `active_areas` that match nothing loaded: accepted, since the operator "
        "may fetch them next"
    )


@dataclass(frozen=True)
class BrowserView(Strict):
    """What the browser map (`reference serve`) will list."""

    regions: tuple[str, ...] = described(
        "the vector-tile files served, by file slug: the active regions' only"
    )
    overlays: tuple[str, ...] = described("the infrastructure layers drawn, by layer id")


@dataclass(frozen=True)
class ActivateDocument(Strict):
    """``maps activate``: the station value written, and what each program was
    told. Nothing is deleted, whichever areas are deactivated."""

    KIND: ClassVar[str] = "areas-activate"

    dry_run: bool = described("true when nothing was written")
    before: tuple[str, ...] | None = described("`active_areas` before; null was unset")
    after: tuple[str, ...] | None = described(
        "`active_areas` after: null for `--all` (everything loaded), an empty list for `--none`"
    )
    changed: bool = described("whether the station value differs")
    unloaded: tuple[str, ...] = described(
        "areas named that match nothing loaded; accepted all the same"
    )
    poi_files: tuple[str, ...] = described(
        "the `.poi` files QMapShack's POI collections will list: the active areas' and every "
        "layer that belongs to no area"
    )
    poi_paths: tuple[str, ...] = described(
        "what QMapShack's `[Canvas] poiPaths` names for them: the layer directories while "
        "everything is active, else `overlays/active-poi`, a directory of links to the files"
    )
    links_added: tuple[str, ...] = described("links made in that directory")
    links_dropped: tuple[str, ...] = described(
        "links taken out of it (only links: no layer file is touched)"
    )
    navit_overlays: tuple[str, ...] = described("the layers' Navit textfiles in Navit's map set")
    navit_regions: tuple[str, ...] = described(
        "the converted region maps left in Navit's map set, by file slug; empty when Navit "
        "has none installed"
    )
    navit_left_out: tuple[str, ...] = described("the converted region maps left out of it")
    browser: BrowserView = described("the browser map's list")
    registered: tuple[RegistrationView, ...] = described(
        "QMapShack's and Navit's, in that order; empty for a dry run"
    )
    notes: tuple[str, ...] = described("sentences the text prints")


def build_areas(
    tokens: tuple[str, ...] | None,
    loaded: tuple[LoadedArea, ...],
    always: tuple[str, ...],
    map_regions: tuple[str, ...] = (),
) -> AreasDocument:
    """The document for the station's ``active_areas`` *tokens* and what is
    loaded (:func:`hammunition.areas.collect`)."""
    active = Active(tokens)
    views = []
    for entry in loaded:
        on = (
            active.state(entry.area)
            if entry.kind == "state"
            else active.region(entry.area, map_regions)
        )
        layers = tuple(
            AreaLayerView(
                layer.id, layer.kind, layer.rows, layer.size_bytes, layer.day, layer.files
            )
            for layer in entry.layers
        )
        days = [layer.day for layer in entry.layers if layer.day]
        views.append(
            AreaView(
                area=entry.area,
                kind=entry.kind,
                active=on,
                layers=layers,
                size_bytes=sum(layer.size_bytes for layer in entry.layers),
                day=max(days) if days else None,
            )
        )
    return AreasDocument(
        active_areas=tokens,
        areas=tuple(views),
        always_active=always,
        unloaded=active.unloaded(
            [e.area for e in loaded if e.kind == "state"],
            [e.area for e in loaded if e.kind == "region"],
        ),
    )


def _scope(active: tuple[str, ...] | None) -> str:
    if active is None:
        return "everything loaded"
    return ", ".join(active) if active else "nothing"


def render_areas(doc: AreasDocument) -> list[str]:
    """``maps areas`` as the terminal shows it."""
    lines = [f"Active: {_scope(doc.active_areas)}"]
    if doc.active_areas is None:
        lines[0] += " (`hammunition maps activate CODE|REGION ...` picks where you are)"
    if not doc.areas:
        lines.append("No state or region is loaded.")
    for view in doc.areas:
        mark = "active" if view.active else "inactive"
        lines.append(
            f"  {view.area:<28} {view.kind:<7} {mark:<8} {len(view.layers)} "
            f"{'layer' if len(view.layers) == 1 else 'layers':<6} "
            f"{human_size(view.size_bytes):>9}  {view.day or ''}".rstrip()
        )
        lines += [
            f"      {layer.id}  {human_size(layer.size_bytes)}"
            + (f"  {layer.rows} repeaters" if layer.rows is not None else "")
            for layer in view.layers
        ]
    if doc.always_active:
        lines.append(f"Always active (no area): {', '.join(doc.always_active)}")
    lines += [f"Not loaded, accepted: {', '.join(doc.unloaded)}"] if doc.unloaded else []
    return lines


def render_activate(doc: ActivateDocument) -> list[str]:
    """``maps activate`` as the terminal shows it."""
    head = "Would set" if doc.dry_run else "Set"
    state = "unchanged" if not doc.changed else f"was {_scope(doc.before)}"
    lines = [f"{head} the active areas to {_scope(doc.after)} ({state})."]
    lines += [f"Not loaded, accepted: {', '.join(doc.unloaded)}"] if doc.unloaded else []
    lines.append(
        f"QMapShack POI files: {len(doc.poi_files)} in {', '.join(doc.poi_paths) or 'none'}"
    )
    if doc.links_added or doc.links_dropped:
        lines.append(f"  links: {len(doc.links_added)} added, {len(doc.links_dropped)} dropped")
    lines.append(
        f"Navit: {len(doc.navit_overlays)} overlay maps, {len(doc.navit_regions)} region maps"
        + (f" ({len(doc.navit_left_out)} left out)" if doc.navit_left_out else "")
    )
    lines.append(
        f"Browser map: {len(doc.browser.regions)} regions, {len(doc.browser.overlays)} overlays"
    )
    lines += [
        f"{'QMapShack' if r.program == 'qmapshack' else 'Navit'}: {r.detail}"
        for r in doc.registered
    ]
    lines += list(doc.notes)
    if doc.dry_run:
        lines.append("Dry run: nothing was written.")
    return lines
