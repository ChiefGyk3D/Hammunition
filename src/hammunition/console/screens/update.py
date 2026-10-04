# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed versus the catalog (D-053), as the engine reports it. The apt upgrade the
report offers runs in a pane (apt shows what it will change and asks); the rebuilds go
through the same plan screen as any install, so they too are planned first."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, Sequence
from typing import Any

import urwid

from hammunition.console.context import Context
from hammunition.console.engine import Document
from hammunition.console.fmt import clean
from hammunition.console.guard import apt_upgrade_argv
from hammunition.console.screens.base import ConfirmScreen, Row, Screen, text
from hammunition.console.screens.plan import PlanScreen

_UNIT = re.compile(r"^[a-z0-9][a-z0-9._+-]*$")
_COUNT_LABELS = (
    ("up_to_date", "up to date"),
    ("candidate_differs", "with a different apt candidate"),
    ("behind_pin", "behind the catalog's pin"),
    ("not_installed", "not installed"),
    ("unknown", "unknown"),
    ("on_install", "re-checked on install"),
    ("manual", "manual"),
)
_ATTR = {
    "up to date": "ok",
    "behind the pin": "warn",
    "candidate differs": "warn",
    "retired": "fail",
}


def rebuild_names(command: str | None) -> list[str] | None:
    """The unit names in `hammunition install NAME...`, or None unless it is exactly that."""
    if not command:
        return None
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    names = words[2:]
    if (
        words[:2] != ["hammunition", "install"]
        or not names
        or not all(_UNIT.match(n) for n in names)
    ):
        return None
    return names


def counts_text(counts: Mapping[str, Any]) -> str:
    known = [
        (counts[key], label) for key, label in _COUNT_LABELS if isinstance(counts.get(key), int)
    ]
    if not known:
        return "counts unknown"
    # Zero counts are left out so the line fits an 80-column terminal.
    return ", ".join(f"{n} {label}" for n, label in known if n) or "0 units to compare"


class UpdateScreen(Screen):
    name = "update"

    def __init__(self, ctx: Context, names: Sequence[str] = ()) -> None:
        super().__init__(ctx)
        self.names = list(names)
        self.title = "Update" + (f": {' '.join(self.names)}" if self.names else "")
        self.upstream = False
        self.note = ""
        self._doc: Document | None = None
        self._catalog: Document | None = None

    def on_show(self) -> None:
        self._doc = None
        words = ["update", *self.names] + (["--upstream"] if self.upstream else [])
        self.load(
            "update", lambda: self.ctx.engine.read(*words), lambda d: setattr(self, "_doc", d)
        )
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self.note:
            rows.append(text(self.note, "warn"))
        if self.status.get("update") == "loading":
            rows.append(text("Comparing (nothing is run, nothing is fetched)..."))
        elif self.status.get("update") == "error":
            rows += [text(self.errors["update"], "fail"), text("")]
            if not self.names:
                rows += self._by_profile()
        elif self._doc is not None:
            rows += self._report(self._doc.body)
        self.set_rows(rows)

    def _by_profile(self) -> list[urwid.Widget]:
        if self._catalog is None:
            self.ctx.bg.submit(lambda: self.ctx.engine.read("list"), self._catalog_loaded)
            return [text("Update by profile instead (reading the profiles)...")]
        rows: list[urwid.Widget] = [text("Update by profile instead (Enter):", "key")]
        for entry in self._catalog.body.get("profiles") or []:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                row = Row(f"  {clean(entry['name'])}", entry["name"])
                urwid.connect_signal(row, "activate", self._open_profile)
                rows.append(row)
        return rows

    def _catalog_loaded(self, doc: Document | None, error: BaseException | None) -> None:
        if doc is not None:
            self._catalog = doc
            self.redraw()

    def _open_profile(self, row: Row) -> None:
        self.ctx.push(UpdateScreen(self.ctx, names=[str(row.value)]))

    def _report(self, body: Mapping[str, Any]) -> list[urwid.Widget]:
        counts = body.get("counts")
        rows: list[urwid.Widget] = [
            text(counts_text(counts if isinstance(counts, dict) else {})),
            text(str(body.get("lists_note") or ""), "dim"),
            text(
                "A run the apt upgrade   B plan the rebuilds   u also ask upstream (asks GitHub, git hosts and PyPI; off by default)",
                "key",
            ),
            text(""),
        ]
        for row in body.get("rows") or []:
            if isinstance(row, dict):
                state = str(row.get("state") or "?")
                rows.append(
                    text(
                        f"{clean(row.get('unit') or '?'):<26} {clean(state):<20} {clean(row.get('detail') or '')}",
                        _ATTR.get(state),
                    )
                )
        upstream = body.get("upstream")
        if isinstance(upstream, list):
            rows += [
                text(""),
                text("Upstream (the catalog's pin against what upstream publishes):", "key"),
            ]
            for row in upstream:
                if isinstance(row, dict):
                    rows.append(
                        text(
                            f"{clean(row.get('unit') or '?'):<22} {clean(row.get('state') or '?'):<18} "
                            f"catalog {clean(row.get('catalog') or '?')}  upstream {clean(row.get('upstream') or 'unanswered')}"
                        )
                    )
        return rows

    def _command(self, key: str) -> str | None:
        value = self._doc.body.get(key) if self._doc else None
        return value if isinstance(value, str) else None

    def keypress(self, key: str) -> str | None:
        if key == "u":
            self.upstream = not self.upstream
            self.on_show()
            return None
        if key == "A":
            self._offer_upgrade()
            return None
        if key == "B":
            self._offer_rebuild()
            return None
        return key

    def _offer_upgrade(self) -> None:
        command = self._command("upgrade_command")
        if command is None:
            self.note = "No apt upgrade is offered."
        elif (argv := apt_upgrade_argv(command)) is None:
            self.note = f"The upgrade command is not in the shape the console runs; run it yourself: {first(command)}"
        else:
            self.note = ""
            self.ctx.push(
                ConfirmScreen(
                    self.ctx,
                    "Upgrade apt packages",
                    [
                        "This runs in a terminal pane; apt shows what it will change and asks you first:",
                        "",
                        "  " + " ".join(argv),
                    ],
                    lambda: self.ctx.run_pane(argv, "apt upgrade", lambda code: self.ctx.pop()),
                )
            )
            return
        self.redraw()

    def _offer_rebuild(self) -> None:
        command = self._command("rebuild_command")
        names = rebuild_names(command)
        if command is None:
            self.note = "Nothing is behind the pin."
        elif names is None:
            self.note = f"The rebuild command is not in the shape the console plans; run it yourself: {first(command)}"
        else:
            self.note = ""
            self.ctx.push(PlanScreen(self.ctx, "install", names))
            return
        self.redraw()


def first(command: str) -> str:
    return clean(command)[:200]
