# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The only verbs the console ever reads with --json: the engine's "Commands" list
(docs/reference/json-interface.md) restricted to what the console uses. A command
with no JSON form refuses --json and runs nothing; reading one is a bug in a screen,
so it fails loudly here, before anything is spawned."""

from __future__ import annotations

from collections.abc import Sequence

JSON_VERBS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("status",),
        ("doctor",),
        ("list",),
        ("show",),
        ("logs",),
        ("update",),
        ("station", "show"),
        ("install",),
        ("uninstall",),
        ("maps", "regions"),
        ("reference", "books"),
    }
)
DRY_RUN_ONLY: frozenset[tuple[str, ...]] = frozenset({("install",), ("uninstall",)})


class NotAJsonVerb(Exception):
    """A screen asked for a document the engine does not print."""


def verb_of(words: Sequence[str]) -> tuple[str, ...]:
    for n in (2, 1):
        head = tuple(words[:n])
        if len(head) == n and head in JSON_VERBS:
            return head
    raise NotAJsonVerb(
        f"{' '.join(words[:2])!r} has no --json form; this is a bug in the screen table"
    )


def require_json_verb(words: Sequence[str]) -> None:
    verb = verb_of(words)
    if verb in DRY_RUN_ONLY and "--dry-run" not in words:
        raise NotAJsonVerb(
            f"`{verb[0]}` is only ever read with --dry-run: a real run is never driven through JSON"
        )
