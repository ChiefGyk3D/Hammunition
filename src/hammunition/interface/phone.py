# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps phone`` as data.  D-059, D-067."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hammunition.interface.envelope import Strict, described
from hammunition.phone import Result, Route

__all__ = ["PhoneDocument", "PhoneFileLine", "PhoneRouteLine", "phone_document"]


@dataclass(frozen=True)
class PhoneFileLine(Strict):
    """One phone file in the folder."""

    unit: str = described("the unit that built it: mapsforge-map, mapsforge-poi or osm-garmin")
    name: str = described("its name in the folder, `<region slug>.<map|poi|img>`")
    size: int = described("bytes")
    sha256: str = described("its sha256, as written in SHA256SUMS")
    copied: bool = described(
        "true when this run copied it; false when the copy was already current"
    )


@dataclass(frozen=True)
class PhoneRouteLine(Strict):
    """One way to carry the folder to a phone. The engine runs none of them."""

    name: str = described("the route")
    laptop: str = described("what the laptop needs")
    phone: str = described("what the phone needs")
    commands: tuple[str, ...] = described(
        "commands for the operator to run, in order; may be empty"
    )
    note: str = described("how to use it, and what it binds or modifies")


@dataclass(frozen=True)
class PhoneDocument(Strict):
    """The phone files gathered into one folder with a SHA256SUMS, and the
    routes to a phone. Names carry region slugs: for local programs, not for
    pasting. Nothing was transferred."""

    KIND: ClassVar[str] = "phone"

    directory: str = described("the folder, under the operator's XDG data directory")
    sums: str = described("the SHA256SUMS file beside them")
    files: tuple[PhoneFileLine, ...] = described("every phone file now in the folder")
    removed: tuple[str, ...] = described("our files removed because their region is gone")
    missing: tuple[str, ...] = described("phone units with nothing installed")
    routes: tuple[PhoneRouteLine, ...] = described("the ways to carry the folder to a phone")


def phone_document(
    result: Result | None, routes: tuple[Route, ...], *, directory: str, missing: tuple[str, ...]
) -> PhoneDocument:
    return PhoneDocument(
        directory=directory,
        sums=f"{directory}/SHA256SUMS",
        files=tuple(
            PhoneFileLine(unit=f.unit, name=f.name, size=f.size, sha256=f.sha256, copied=f.copied)
            for f in (result.files if result is not None else ())
        ),
        removed=result.removed if result is not None else (),
        missing=missing,
        routes=tuple(
            PhoneRouteLine(
                name=r.name, laptop=r.laptop, phone=r.phone, commands=r.commands, note=r.note
            )
            for r in routes
        ),
    )
