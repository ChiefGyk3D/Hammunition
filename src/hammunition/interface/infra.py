# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps infra import`` and ``maps infra remove`` as data.  D-075, D-059.

Counts, paths, layer names and licence lines only, D-074's shape. Neither
document carries a place's name or position, a region, a region's box or
an extract's digest: the layers say where the operator is, and these are
the kind of output that gets pasted into an issue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hammunition.interface.envelope import Strict, described
from hammunition.interface.repeaters import RegistrationView, SkipView
from hammunition.interface.text import wrap

__all__ = [
    "InfraDocument",
    "InfraInputView",
    "InfraLayerView",
    "InfraRemovedDocument",
    "render_infra",
    "render_infra_removed",
]


@dataclass(frozen=True)
class InfraInputView(Strict):
    """One input read."""

    path: str = described(
        "the installed file, or a fetch's URL; for `osm-extract`, the directory of the "
        "region extracts, never a region's name"
    )
    format: str = described(
        "`osm-extract`, `faa-nasr-apt`, `eia-860m`, `wri-gppd`, `fcc-asr` or `nwr-ccl`"
    )
    sha256: str = described(
        "the digest of what was read; empty for `osm-extract`, whose extracts' digests "
        "would name the regions"
    )


@dataclass(frozen=True)
class InfraLayerView(Strict):
    """One layer this import wrote, or found empty."""

    layer_id: str = described(
        "`osm-medical`, `osm-responders`, `osm-supply`, `osm-shelter-candidates`, "
        "`osm-transport`, `osm-power`, `osm-telecom`, `osm-water`, `faa-airports`, "
        "`eia-plants`, `wri-plants`, `fcc-towers` or `nwr`"
    )
    name: str = described("the layer's name, as QMapShack and the browser map show it")
    written: int = described("points in the layer; 0 when this import found none")
    files: tuple[str, ...] = described(
        "the files written, mode 0600: GPX, POI, Navit textfile, GeoJSON; empty when none"
    )
    removed: tuple[str, ...] = described(
        "an earlier version's files, deleted because this import found no point for it"
    )
    active: bool = described(
        "whether the layer's area is active (D-082): true for every layer today, each theme "
        "being one file across every region, and while the station's `active_areas` is unset"
    )


@dataclass(frozen=True)
class InfraDocument(Strict):
    """Infrastructure layers written from one source (D-075). Counts, paths,
    names and licence lines only: no place, position or region is carried."""

    KIND: ClassVar[str] = "infra"

    route: str = described("`osm`, `nasr`, `eia`, `wri`, `fcc-asr` or `nwr`")
    licences: tuple[str, ...] = described("the source's licence line, printed before anything")
    inputs: tuple[InfraInputView, ...] = described("what was read")
    read: int = described("objects, rows or records read that belong in a layer")
    skipped: tuple[SkipView, ...] = described(
        "rows left out, by reason; `first` is empty when several extracts were read"
    )
    outside: int = described(
        "rows of a nationwide or worldwide file outside the regions' boxes; 0 for `osm`"
    )
    merged: int = described("points two extracts both held, kept once; 0 but for `osm`")
    notes: tuple[str, ...] = described(
        "sentences the text prints: an extract left out (by number), what another source covers"
    )
    layers: tuple[InfraLayerView, ...] = described("each layer, in layer order")
    directory: str = described("where the layers are, mode 0700")
    registered: tuple[RegistrationView, ...] = described(
        "QMapShack's and Navit's, in that order, for every overlay layer present"
    )


@dataclass(frozen=True)
class InfraRemovedDocument(Strict):
    """Infrastructure layers deleted and unregistered. Removing nothing is
    not an error: every list is then empty."""

    KIND: ClassVar[str] = "infra-removed"

    directory: str = described("where the layers are")
    layers: tuple[str, ...] = described(
        "the layer ids asked for: the one `--layer` named, else every layer"
    )
    removed: tuple[str, ...] = described("the files deleted")
    unregistered: tuple[RegistrationView, ...] = described(
        "QMapShack's and Navit's, in that order, for the overlay layers left"
    )


def _registration(view: RegistrationView) -> str:
    name = {"qmapshack": "QMapShack", "navit": "Navit"}[view.program]
    return f"{name}: {view.detail}"


def render_infra(doc: InfraDocument) -> list[str]:
    """``maps infra import`` and the fetches as the terminal shows them."""
    lines: list[str] = []
    for text in doc.licences:
        lines += [*wrap(text, indent=""), ""]
    for view in doc.inputs:
        lines.append(f"Input: {view.path} ({view.format})")
        if view.sha256:
            lines.append(f"  sha256 {view.sha256}")
    reasons = ", ".join(f"{s.reason}: {s.count}" for s in doc.skipped)
    skipped = sum(s.count for s in doc.skipped)
    lines.append(
        f"Read: {doc.read} objects, {skipped} skipped" + (f" ({reasons})" if reasons else "")
    )
    if doc.outside:
        lines.append(f"Outside your regions' boxes: {doc.outside}")
    if doc.merged:
        lines.append(f"In two extracts, kept once: {doc.merged}")
    lines += [f"Note: {note}" for note in doc.notes]
    for layer in doc.layers:
        if layer.written:
            lines.append(f"{layer.name}: {layer.written} points")
            lines += [f"  {path}" for path in layer.files]
        else:
            lines.append(f"{layer.name}: no points, not written")
            lines += [f"  removed {path}" for path in layer.removed]
    lines += [_registration(view) for view in doc.registered]
    lines += [
        "",
        "QMapShack: each layer is a POI collection in the POI Collections dock, and File >",
        "Load opens its GPX. Navit: start navit-offline. Browser: `hammunition reference",
        "serve` lists every layer beside the map.",
    ]
    return lines


def render_infra_removed(doc: InfraRemovedDocument) -> list[str]:
    """``maps infra remove`` as the terminal shows it."""
    if not doc.removed and all(v.outcome == "not there" for v in doc.unregistered):
        return [f"Nothing to remove in {doc.directory}."]
    lines = ["Removed:"] + [f"  {path}" for path in doc.removed]
    lines += [_registration(view) for view in doc.unregistered]
    return lines
