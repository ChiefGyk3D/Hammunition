# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import urwid

from hammunition.console.context import Context
from hammunition.console.engine import Document
from hammunition.console.fmt import clean, first_line, mask
from hammunition.console.screens.base import ConfirmScreen, PromptScreen, Row, Screen, text


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    flag: str
    secret: bool = False
    clear_flag: str | None = None
    chooser: str | None = None


FIELDS: tuple[Field, ...] = (
    Field("callsign", "Callsign", "--callsign", secret=True),
    Field("grid_square", "Grid square", "--grid-square", secret=True),
    Field("node_alias", "Packet node alias", "--node-alias", secret=True),
    Field("map_regions", "Map regions", "--map-regions", secret=True, chooser="regions"),
    Field("map_freshness", "Map freshness", "--map-freshness"),
    Field("reference_books", "Kiwix books", "--reference-books", chooser="books"),
    Field("mirror", "LAN mirror", "--mirror", clear_flag="--clear-mirror"),
    Field("dem_source", "Elevation source", "--dem-source"),
    Field("rig", "Rig", "--rig", clear_flag="--clear-rig"),
    Field("rig_device", "Rig port", "--rig-device", secret=True),
    Field("rig_baud", "Rig baud rate", "--rig-baud"),
    Field("rig_ptt_line", "Rig PTT line", "--rig-ptt-line"),
    Field("rig_owner", "Rig owner", "--rig-owner"),
)


def display_value(field: Field, value: Any, revealed: bool) -> str:
    if value is None or value == []:
        return "not set"
    if isinstance(value, list):
        return (
            ", ".join(clean(v) for v in value)
            if (revealed or not field.secret)
            else f"{len(value)} set"
        )
    if field.secret and not revealed:
        return mask(str(value))
    return clean(value)


def set_argv(command: Callable[..., list[str]], field: Field, value: str) -> list[str]:
    """One argv element carries the flag and the value; it cannot be read as another flag."""
    return command("station", "set", f"{field.flag}={value}")


class ChooserScreen(Screen):
    """Pick several items from a list; capital A applies. Space and Enter toggle."""

    name = "chooser"

    def __init__(
        self,
        ctx: Context,
        title: str,
        load_items: Callable[[], list[tuple[str, str]]],
        selected: Sequence[str],
        on_apply: Callable[[list[str]], None],
        note: str = "",
        hide_carried: bool = False,
    ) -> None:
        super().__init__(ctx)
        self.title = title
        self.hide_carried = hide_carried
        self.revealed = False
        self._carried: list[str] = []
        self._load_items = load_items
        self.selected = list(selected)
        self._on_apply = on_apply
        self._note = note
        self._items: list[tuple[str, str]] = []
        self._hint = ""

    def on_show(self) -> None:
        self.load("items", self._load_items, self._store)
        self.redraw()

    def _store(self, items: list[tuple[str, str]]) -> None:
        known = {value for value, _ in items}
        self._carried = [v for v in self.selected if v not in known]
        self._items = ([] if self.hide_carried else [(v, v) for v in self._carried]) + items

    def on_hide(self) -> None:
        self.revealed = False
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = [
            text(self._note, "dim"),
            text(
                "Enter toggles; A applies the whole selection; b goes back and changes nothing.",
                "dim",
            ),
        ]
        if self._hint:
            rows.append(text(self._hint, "warn"))
        if self.status.get("items") == "loading":
            rows.append(text("Loading..."))
        elif self.status.get("items") == "error":
            rows.append(text(self.errors["items"], "fail"))
        if self.hide_carried and self._carried:
            if self.revealed:
                for value in self._carried:
                    rows.append(self._row(value, value))
            else:
                rows.append(text(f"{len(self._carried)} carried, hidden; press v to show.", "dim"))
        for value, label in self._items:
            rows.append(self._row(value, label))
        self.set_rows(rows)

    def _row(self, value: str, label: str) -> Row:
        row = Row(f"[{'x' if value in self.selected else ' '}] {label}", value)
        urwid.connect_signal(row, "activate", self._toggle)
        return row

    def _toggle(self, row: Row) -> None:
        value = str(row.value)
        if value in self.selected:
            self.selected.remove(value)
        else:
            self.selected.append(value)
        self.redraw()

    def keypress(self, key: str) -> str | None:
        if key == "v" and self.hide_carried:
            self.revealed = not self.revealed
            self.redraw()
            return None
        if key == "A":
            if not self.selected:
                self._hint = "Select at least one first. Nothing was run."
                self.redraw()
                return None
            self.ctx.pop()
            self._on_apply(list(self.selected))
            return None
        return key


class StationScreen(Screen):
    name = "station"
    title = "Station"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.revealed = False
        self.note = ""
        self._doc: Document | None = None
        self._saved = False  # a run exited 0 and its read-back has not finished

    def on_show(self) -> None:
        self.load("station", lambda: self.ctx.engine.read("station", "show"), self._store)
        self.redraw()

    def _store(self, doc: Document) -> None:
        self._doc = doc
        if self._saved:
            self._saved = False
            self.note = "Saved. The values below were read back from the engine."

    def on_hide(self) -> None:
        self.revealed = False
        self.redraw()

    def redraw(self) -> None:
        if self._saved and self.status.get("station") == "error":
            self._saved = False
            self.note = "The engine reported success, but reading the values back failed."
        rows: list[urwid.Widget] = [
            text(
                "Station values are saved by the engine, never by this console. Enter changes one; v reveals or hides; c clears.",
                "dim",
            )
        ]
        if self.note:
            rows.append(text(self.note, "warn"))
        if self.status.get("station") == "error":
            rows.append(text(self.errors["station"], "fail"))
        elif self._doc is not None:
            for field in FIELDS:
                value = self._doc.body.get(field.key)
                row = Row(f"{field.label:<20} {display_value(field, value, self.revealed)}", field)
                urwid.connect_signal(row, "activate", self._edit)
                rows.append(row)
        else:
            rows.append(text("Reading the station..."))
        self.set_rows(rows)

    def keypress(self, key: str) -> str | None:
        if key == "v":
            self.revealed = not self.revealed
            self.redraw()
            return None
        if key == "c":
            field = self.focused_value()
            if isinstance(field, Field) and field.clear_flag:
                self._confirm_clear(field.clear_flag)
                return None
        return key

    def _confirm_clear(self, flag: str) -> None:
        argv = self.ctx.engine.command("station", "set", flag)
        self.ctx.push(
            ConfirmScreen(
                self.ctx,
                f"Clear: station set {flag}",
                [
                    "This runs the engine's own command, which removes a station value:",
                    "",
                    "  " + " ".join(argv),
                ],
                lambda: self._run(argv, f"station set {flag}"),
            )
        )

    def _run(self, argv: list[str], title: str) -> None:
        self.ctx.run_pane(argv, title, self._after_set)

    def _after_set(self, code: int | None) -> None:
        if code == 0:
            self._saved = True
            self.note = "Saved. Reading the values back from the engine..."
        else:
            said = f"exit {code}" if code is not None else "no exit code recorded"
            self.note = f"The engine run ended with {said}; its own words were in the pane."
        self.ctx.pop()

    def _field(self, key: str) -> Field:
        return next(f for f in FIELDS if f.key == key)

    def _edit(self, row: Row) -> None:
        field = row.value
        if not isinstance(field, Field):
            return
        if field.chooser == "books":
            self._choose_books()
        elif field.chooser == "regions":
            self.ctx.push(
                PromptScreen(
                    self.ctx,
                    "Search Geofabrik regions",
                    "contains: ",
                    self._search_regions,
                    note="Part of a region name, for example: vermont",
                )
            )
        else:
            self.ctx.push(
                PromptScreen(
                    self.ctx,
                    f"Set {field.label.lower()}",
                    f"{field.label}: ",
                    lambda value: self._set(field, value),
                )
            )

    def _set(self, field: Field, value: str) -> None:
        if value:
            self._run(set_argv(self.ctx.engine.command, field, value), f"station set {field.flag}")

    def _current(self, key: str) -> list[str]:
        value = self._doc.body.get(key) if self._doc else None
        return [str(v) for v in value] if isinstance(value, list) else []

    def _choose_books(self) -> None:
        field = self._field("reference_books")

        def items() -> list[tuple[str, str]]:
            books = self.ctx.engine.read("reference", "books").body.get("books")
            return (
                [
                    (
                        str(b["id"]),
                        f"{b['id']}  {first_line(str(b.get('title') or ''))}  {b.get('licence') or ''}",
                    )
                    for b in books
                    if isinstance(b, dict) and "id" in b
                ]
                if isinstance(books, list)
                else []
            )

        self.ctx.push(
            ChooserScreen(
                self.ctx,
                "Kiwix books",
                items,
                self._current("reference_books"),
                lambda ids: self._run(
                    set_argv(self.ctx.engine.command, field, ",".join(ids)),
                    f"station set {field.flag}",
                ),
                note="Replaces the whole list. Each book's licence is shown before you choose.",
            )
        )

    def _search_regions(self, term: str) -> None:
        if not term:
            return
        if term.startswith("-"):
            self.note = "A search term does not start with '-'. Nothing was run."
            self.redraw()
            return
        field = self._field("map_regions")

        def items() -> list[tuple[str, str]]:
            found = self.ctx.engine.read("maps", "regions", term).body.get("regions")
            return [(str(r), str(r)) for r in found] if isinstance(found, list) else []

        self.ctx.push(
            ChooserScreen(
                self.ctx,
                "Regions matching your search",
                items,
                self._current("map_regions"),
                lambda ids: self._run(
                    set_argv(self.ctx.engine.command, field, ",".join(ids)),
                    f"station set {field.flag}",
                ),
                note="Replaces the whole list; regions you already carry are kept (v shows them).",
                hide_carried=True,
            )
        )
