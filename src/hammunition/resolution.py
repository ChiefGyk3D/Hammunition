# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where a plan's facts come from when the publisher may not be asked.

One :class:`ResolutionContext` is made per run and shared by every resolver.
Online it changes nothing until a publisher has spent its retries
(:class:`~hammunition.catalogue.PublisherUnavailable`); then, if a Bunker is
enrolled and its catalogue verified, the record the Bunker kept answers
instead, and the plan says so on the line it affects. Offline, the publisher
is never asked: the verified catalogue answers, or the item is refused by
name.

This module is a leaf: stdlib, :mod:`hammunition.catalogue` and
:mod:`hammunition.signers` only, so every resolver can import it without a
cycle. What needs the planner or the backends (the deferral an unresolved
item becomes, the data preflight) lives in :mod:`hammunition.plan`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol, TypeVar

from hammunition.catalogue import CatalogueArtifact, PublisherUnavailable
from hammunition.signers import VerifiedCatalogue

__all__ = [
    "NO_BUNKER",
    "CatalogueMiss",
    "InputTransport",
    "ResolutionContext",
    "TextProbe",
]

T = TypeVar("T")

#: The refusal for an offline run with nothing enrolled.
NO_BUNKER = "no Bunker enrolled; hammunition mirror enrol URL"


class InputTransport(Protocol):
    """Reads one mirror path, failing as ``OSError`` (``CatalogueInputs``)."""

    def read(self, relative: str, *, max_bytes: int) -> bytes: ...


class TextProbe(Protocol):
    """A plan-time probe that can fetch a page of text."""

    def text(self, url: str) -> str: ...


class CatalogueMiss(ValueError):
    """The catalogue cannot answer: nothing enrolled, no such entry, or an
    entry that is not current. The message names what was asked for."""


@dataclass
class ResolutionContext:
    offline: bool = False
    verified: VerifiedCatalogue | None = None
    enrolment_id: str | None = None
    inputs: InputTransport | None = None
    notes: dict[tuple[str, str], str] = field(default_factory=dict)
    _notes_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def entry(self, unit: str, name: str) -> CatalogueArtifact:
        if self.verified is None:
            raise CatalogueMiss(NO_BUNKER)
        row = self.verified.catalogue.artifact(unit, name, self.enrolment_id)
        if row is None:
            raise CatalogueMiss(
                f"{unit}/{name}: not on Bunker {self.verified.catalogue.bunker.name}, "
                "publisher unreachable"
            )
        if row.status != "current" or row.path is None or row.sha256 is None or row.size is None:
            raise CatalogueMiss(
                f"{unit}/{name}: Bunker entry is {row.status}: {row.reason or 'not current'}"
            )
        return row

    def require_payload(
        self, unit: str, name: str, *, sha256: str | None = None, size: int | None = None
    ) -> CatalogueArtifact:
        """The entry, which must also match the repository's own pin."""
        row = self.entry(unit, name)
        if sha256 is not None and row.sha256 != sha256:
            raise CatalogueMiss(
                f"{unit}/{name}: Bunker copy does not match the repository sha256 pin"
            )
        if size is not None and row.size != size:
            raise CatalogueMiss(f"{unit}/{name}: Bunker copy does not match the expected size")
        return row

    def unverified(self, unit: str, name: str) -> CatalogueArtifact:
        """An entry whose publisher offers no digest, which the Bunker labels so."""
        row = self.entry(unit, name)
        if row.publisher_check not in ("unverified-fetch", "unverified-zip"):
            raise CatalogueMiss(f"{unit}/{name}: expected an explicitly unverified catalogue entry")
        return row

    def note(self, unit: str, name: str, *, fallback: bool) -> str:
        """The provenance line for an item the catalogue answered, kept for the plan.

        Every line the signer vouches for carries its warnings (a weak key, a
        catalogue older than thirty days)."""
        if self.verified is None:
            raise CatalogueMiss(NO_BUNKER)
        v = self.verified
        prefix = "publisher unreachable; " if fallback else "offline; "
        text = (
            f"{prefix}resolved from Bunker {v.catalogue.bunker.name} ({v.key.id}), "
            f"recorded {v.catalogue.generated}"
        )
        if v.warnings:
            text += "; " + "; ".join(v.warnings)
        with self._notes_lock:
            self.notes[(unit, name)] = text
        return text

    def choose(self, unit: str, name: str, online: Callable[[], T], recorded: Callable[[], T]) -> T:
        """*online* while the publisher answers; *recorded* when it cannot be asked.

        Call it outside the retrying probe, so the catalogue is consulted once
        per item and only after the retries are spent. A certificate that does
        not verify and an HTTP 404 are answers, not outages, and pass through."""
        if self.offline and self.verified is None:
            raise CatalogueMiss(NO_BUNKER)
        if not self.offline:
            try:
                return online()
            except PublisherUnavailable:
                if self.verified is None:
                    raise
        result = recorded()
        self.note(unit, name, fallback=not self.offline)
        return result
