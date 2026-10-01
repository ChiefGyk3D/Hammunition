# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``artifacts`` as data.  D-070, D-059.

The contract Hammunition Bunker mirrors from: every remote data artifact
the engine would fetch for an explicit selection. Nothing in it is the
operator's; the selection is what the command was given.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from hammunition.backends.data import human_size
from hammunition.interface.envelope import Strict, described

__all__ = ["CHECKS", "ArtifactEntry", "ArtifactsDocument", "render_artifacts"]

#: How an artifact is verified. ``sha256-publisher`` (a ``.sha256`` or
#: ``.meta4`` the publisher serves) is in the Bunker contract; no catalog
#: unit produces it today.
CHECKS = ("sha256", "md5-publisher", "etag-md5", "sha256-publisher")


@dataclass(frozen=True)
class ArtifactEntry(Strict):
    """One remote artifact, or one the selection cannot list and why."""

    unit: str = described("the catalog unit (`osm-regions`, `dem-copernicus`, `country-files`)")
    name: str | None = described(
        "the artifact's stable name within the unit: a region path, a tile name, a data "
        "file's name. A LAN mirror serves it at `<mirror>/<unit>/<name>`. Null only for a "
        "deferred entry that covers the whole unit"
    )
    url: str | None = described("the publisher URL the engine itself fetches; null when deferred")
    check: str | None = described(
        "how the download is verified: `sha256` (pinned by Hammunition), `md5-publisher` "
        "(Geofabrik's published MD5), `etag-md5` (the Copernicus object's ETag), "
        "`sha1-publisher` (the SHA-1 and size in CoMaps' own map index at the pinned "
        "commit, carried in the catalog) or `sha256-publisher` (no unit uses it today); "
        "null when deferred"
    )
    digest: str | None = described(
        "the expected digest, in hex, of the kind `check` names: the pin, or the publisher's "
        "checksum as the engine read it while resolving; null when deferred"
    )
    checksum_url: str | None = described(
        "where a publisher checksum is read: the `.md5` beside a Geofabrik file, or the tile "
        "URL whose `HEAD` carries the ETag; null for a pinned sha256 and when deferred"
    )
    size: int | None = described("bytes, known before the fetch; null when deferred")
    licence: str = described("the licence line the plan prints for the unit")
    deferred: str | None = described(
        "null, or why this artifact cannot be listed for this selection"
    )


@dataclass(frozen=True)
class ArtifactsDocument(Strict):
    """Every remote data artifact the engine would fetch for the selection
    given (D-070): `data` units, map regions and terrain tiles. No station
    file is read; the regions are the ones on the command line. What cannot
    be listed is listed as deferred, with the reason, never dropped."""

    KIND: ClassVar[str] = "artifacts"

    map_regions: tuple[str, ...] = described("the `--map-regions` given; empty when none")
    map_freshness: str = described("the `--map-freshness` given, `yearly` when none")
    units: tuple[str, ...] = described("the units listed, in order")
    artifacts: tuple[ArtifactEntry, ...] = described(
        "one entry per artifact, deferred ones included"
    )


def render_artifacts(doc: ArtifactsDocument) -> list[str]:
    """``artifacts`` as the terminal shows it: one line per artifact."""
    lines = [
        f"Remote data artifacts for {len(doc.units)} unit(s), "
        f"{len(doc.map_regions)} map region(s), freshness {doc.map_freshness}:"
    ]
    listed = [e for e in doc.artifacts if e.deferred is None]
    deferred: Sequence[ArtifactEntry] = [e for e in doc.artifacts if e.deferred is not None]
    for entry in listed:
        size = human_size(entry.size) if entry.size is not None else "?"
        lines.append(f"  {entry.unit}  {entry.name}  {size}  {entry.check}  {entry.url}")
    if not listed:
        lines.append("  (none)")
    if deferred:
        lines.append("Deferred:")
        for entry in deferred:
            lines.append(f"  {entry.unit}  {entry.name or '(all)'}: {entry.deferred}")
    return lines
