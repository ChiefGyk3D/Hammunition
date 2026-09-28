# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps regions`` as data.  D-059, D-057."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hammunition.interface.envelope import Strict, described

__all__ = ["RegionsDocument"]


@dataclass(frozen=True)
class RegionsDocument(Strict):
    """Geofabrik's region paths, filtered. Fetched from Geofabrik's index when
    this command runs, and only then; nothing here is the operator's."""

    KIND: ClassVar[str] = "regions"

    filter: str | None = described(
        "the case-insensitive substring asked for; null for every region"
    )
    regions: tuple[str, ...] = described("the matching region paths, in the index's order")
