# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``reference books`` as data.  D-065, D-059."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hammunition.interface.envelope import Strict, described

__all__ = ["BookRow", "BooksDocument"]


@dataclass(frozen=True)
class BookRow(Strict):
    """One book the catalog offers, with its pin."""

    id: str = described("the id station config takes (`station set --reference-books`)")
    title: str = described("what the book is")
    file: str | None = described("the pinned dated file; null when the book is not pinned")
    size: int | None = described("bytes of the pinned file; null when not pinned")
    licence: str = described("the publisher's licence line, printed in the plan too")
    licence_url: str = described("where the publisher states it")
    note: str | None = described("anything else the book list says of it")
    chosen: bool = described("whether station config chooses it")
    installed: bool = described("whether its pinned file is installed")


@dataclass(frozen=True)
class BooksDocument(Strict):
    """The Kiwix books the catalog offers. Read from the catalog and the disk;
    nothing is fetched."""

    KIND: ClassVar[str] = "books"

    books: tuple[BookRow, ...] = described(
        "every book in catalog/data/kiwix-books.yaml, in its order"
    )
