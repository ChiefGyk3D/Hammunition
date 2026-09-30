#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate the Kiwix book pins.  D-065.

Reads the hand-written allow-list, ``catalog/data/kiwix-books.yaml``, and
writes ``catalog/data/kiwix-pins.yaml``: for each allowed book, the dated file
Kiwix publishes today, its exact size and its sha256.

Where each number comes from: Kiwix's library index
(``https://download.kiwix.org/library/library_zim.xml``, about 20 MB) names
the current ``.meta4`` of every book and flavour, and each ``.meta4``
(MirrorBrain's Metalink, about 5 KB) carries the file's name, byte size and
sha-256. No ZIM is downloaded. Nothing Kiwix publishes is signed -- no
``.asc`` or ``.sig`` exists for the index or any file -- so the trust is TLS to
download.kiwix.org at the moment this runs, frozen into the pin.

**A pin dies on Kiwix's calendar.** The download directories keep the two
newest dated files of each book, so a pinned file disappears about two
publications after it was pinned (months for Wikipedia, about six months for
Stack Exchange). ``--check`` asks each pinned file's ``.meta4`` again and
exits 1 naming every one that is gone or has changed; the weekly pin-review
CI job runs it, and regenerating is running this script with no arguments.
A gone pin is never replaced by the newer file behind anyone's back: the
engine refuses it at plan time and names this script.

    scripts/gen_kiwix_pins.py                    # regenerate (about 20 MB + 5 KB a book)
    scripts/gen_kiwix_pins.py --check            # each pin's .meta4 again
    scripts/gen_kiwix_pins.py --check --offline  # the files' shape only
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.kiwix import (  # noqa: E402
    DOWNLOAD,
    GENERATED_MARK,
    Book,
    BookPin,
    KiwixError,
    file_date,
    load_books,
    load_pins,
    parse_library,
    parse_meta4,
)

DATA = REPO_ROOT / "catalog" / "data"
BOOKS = DATA / "kiwix-books.yaml"
PINS = DATA / "kiwix-pins.yaml"
LIBRARY_URL = "https://download.kiwix.org/library/library_zim.xml"
HOSTS = ("https://download.kiwix.org/", "https://lb.download.kiwix.org/")
TIMEOUT = 120.0
REGENERATE = (
    "Kiwix keeps two dated files per book, so a pin goes about two publications "
    "after it is made; regenerate with scripts/gen_kiwix_pins.py"
)

HEADER = f"""\
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0

# {GENERATED_MARK}. Do not edit by hand.
#
# One pin per book in catalog/data/kiwix-books.yaml: the dated file Kiwix
# published on the `measured` date, its exact size and sha256, read from the
# file's .meta4. Nothing Kiwix publishes is signed; the pin freezes what TLS
# to download.kiwix.org delivered that day. Kiwix keeps only the two newest
# dated files per book, so a pin dies about two publications after it is made
# and the weekly pin review goes red naming it.
#
# Regenerate: scripts/gen_kiwix_pins.py
# Check:      scripts/gen_kiwix_pins.py --check [--offline]
"""

Text = Callable[[str], str]


class Gone(Exception):
    """The URL answered 404 (or 410): the file is no longer published."""


def pin_for(book: Book, meta4_url: str, text: Text, measured: str) -> dict[str, Any]:
    """Measure one book from its ``.meta4``. Refuses a file that is not this book's."""
    category = meta4_url.split("/zim/", 1)[1].split("/", 1)[0] if "/zim/" in meta4_url else ""
    if category != book.category:
        raise SystemExit(
            f"{book.id}: Kiwix files it under {category!r}, the book list says "
            f"category {book.category!r}; correct catalog/data/kiwix-books.yaml"
        )
    file, size, sha256 = parse_meta4(text(meta4_url))
    if not file.startswith(f"{book.id}_"):
        raise SystemExit(f"{book.id}: its .meta4 names {file!r}, not a file of this book")
    return {
        "id": book.id,
        "file": file,
        "url": f"{DOWNLOAD}/{book.category}/{file}",
        "size": size,
        "sha256": sha256,
        "published": file_date(file),
        "measured": measured,
    }


def render(rows: Sequence[Mapping[str, Any]]) -> str:
    return f"{HEADER}\n" + yaml.safe_dump(
        {"pins": list(rows)}, sort_keys=False, default_flow_style=False
    )


def generate(books: Mapping[str, Book], text: Text, measured: str) -> list[dict[str, Any]]:
    library = parse_library(text(LIBRARY_URL))
    missing = [b.id for b in books.values() if (b.name, b.flavour) not in library]
    if missing:
        raise SystemExit(
            f"Kiwix's library lists no book for: {', '.join(missing)}. It was renamed or "
            f"withdrawn; correct catalog/data/kiwix-books.yaml. Nothing was written."
        )
    return [pin_for(b, library[(b.name, b.flavour)], text, measured) for b in books.values()]


def shape_problems(books: Mapping[str, Book], pins: Mapping[str, BookPin]) -> list[str]:
    problems = [
        f"{book_id}: in the book list and not pinned; regenerate"
        for book_id in books
        if book_id not in pins
    ]
    problems += [
        f"{book_id}: pinned and not in the book list; regenerate"
        for book_id in pins
        if book_id not in books
    ]
    if not problems and list(books) != list(pins):
        problems.append("the pins are not in the book list's order; regenerate")
    return problems


def online_problems(pins: Mapping[str, BookPin], text: Text) -> list[str]:
    problems: list[str] = []
    for pin in pins.values():
        try:
            file, size, sha256 = parse_meta4(text(f"{pin.url}.meta4"))
        except Gone:
            problems.append(f"{pin.id}: {pin.file} is gone from Kiwix. {REGENERATE}")
            continue
        except (KiwixError, OSError) as exc:
            problems.append(f"{pin.id}: its .meta4 could not be read: {exc}")
            continue
        if (file, size, sha256) != (pin.file, pin.size, pin.sha256):
            problems.append(
                f"{pin.id}: Kiwix now says {file}, {size} bytes, sha256 {sha256[:12]}…; "
                f"pinned {pin.file}, {pin.size} bytes, {pin.sha256[:12]}…"
            )
    return problems


# -- the network, used only when nothing is injected --------------------------


def _opener() -> urllib.request.OpenerDirector:
    director = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.HTTPSHandler(),
        urllib.request.HTTPRedirectHandler(),
        urllib.request.HTTPErrorProcessor(),
        urllib.request.HTTPDefaultErrorHandler(),
    ):
        director.add_handler(handler)
    return director


def real_text(url: str) -> str:
    if not url.startswith(HOSTS):
        raise SystemExit(f"refusing {url!r}: only download.kiwix.org is asked")
    request = urllib.request.Request(url, headers={"User-Agent": "hammunition"})
    try:
        with _opener().open(request, timeout=TIMEOUT) as response:
            final = response.geturl()
            if not final.startswith(HOSTS):
                raise SystemExit(f"refusing {url!r}: it redirected to {final!r}")
            body: bytes = response.read(64 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            raise Gone(url) from exc
        raise
    return body.decode("utf-8", errors="replace")


def _write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text)
    os.replace(temporary, path)


def main(
    argv: Sequence[str] | None = None,
    *,
    text: Text | None = None,
    today: date | None = None,
    books_path: Path = BOOKS,
    pins_path: Path = PINS,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="check the pin file; write nothing")
    parser.add_argument(
        "--offline", action="store_true", help="with --check: the shape only, no network"
    )
    args = parser.parse_args(argv)
    get_text = text or real_text
    try:
        books = load_books(books_path.read_text())
    except (OSError, KiwixError) as exc:
        raise SystemExit(f"{books_path}: {exc}") from exc

    if args.check:
        try:
            pins = load_pins(pins_path.read_text())
        except (OSError, KiwixError) as exc:
            raise SystemExit(f"{pins_path}: {exc}; regenerate") from exc
        problems = shape_problems(books, pins)
        if not problems and not args.offline:
            problems = online_problems(pins, get_text)
        if problems:
            print(f"{len(problems)} problem(s):")
            for problem in problems:
                print(f"  {problem}")
            return 1
        if args.offline:
            print(f"{pins_path.name} is well formed: {len(pins)} pin(s), one per listed book")
        else:
            print(f"{pins_path.name} is up to date: {len(pins)} pin(s) asked of Kiwix")
        return 0

    measured = (today or date.today()).isoformat()
    rows = generate(books, get_text, measured)
    _write(pins_path, render(rows))
    total = sum(int(r["size"]) for r in rows)
    print(f"wrote {pins_path.name}: {len(rows)} pin(s), {total:,} bytes in all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
