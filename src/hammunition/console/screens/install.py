# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import urwid

from hammunition.console.context import Context
from hammunition.console.engine import Document
from hammunition.console.fmt import clean, human_size
from hammunition.console.screens.base import Row, Screen, text
from hammunition.console.screens.plan import PlanScreen


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def profile_state(entry: Mapping[str, Any]) -> str:
    """Installed state from E1's fields; 'unknown' when the engine does not send them."""
    members, installed, size = (
        entry.get("members"),
        entry.get("installed"),
        entry.get("installed_size_bytes"),
    )
    if _int(members) and _int(installed):
        return f"{installed} of {members} installed" + (
            f", {human_size(size)}" if isinstance(size, int) and not isinstance(size, bool) else ""
        )
    packages = entry.get("packages")
    return f"{len(packages) if isinstance(packages, list) else 0} units, state unknown"


def profile_text(entry: Mapping[str, Any]) -> str:
    gate = "G" if entry.get("consent_gated") is True else " "
    return (
        f"{clean(entry.get('name') or '?'):<18} {clean(entry.get('stage') or ''):<9} "
        f"{profile_state(entry):<26} {gate}  {clean(entry.get('summary') or '')}"
    )


def unit_text(entry: Mapping[str, Any]) -> str:
    return (
        f"{clean(entry.get('name') or '?'):<26} {clean(entry.get('status') or ''):<12} "
        f"{clean(entry.get('resolves_here') or 'not here'):<10} {clean(entry.get('summary') or '')}"
    )


class InstallScreen(Screen):
    name = "install"
    title = "Install"

    def __init__(self, ctx: Context, highlight: str | None = None) -> None:
        super().__init__(ctx)
        self.mode = "profiles"
        self.note = ""
        self._highlight = highlight
        self._catalog: Document | None = None
        self._name_edit = urwid.Edit("Install by name (separate several with spaces): ")
        self._detail = urwid.Text("")
        self._frame = urwid.Frame(self._list, footer=urwid.Pile([urwid.Divider("-"), self._detail]))
        urwid.connect_signal(self._walker, "modified", self._focus_changed)

    def widget(self) -> urwid.Widget:
        return self._frame

    def on_show(self) -> None:
        self.load("list", lambda: self.ctx.engine.read("list"), self._store)
        self.redraw()

    def _store(self, doc: Document) -> None:
        self._catalog = doc

    def _entries(self, key: str) -> list[Mapping[str, Any]]:
        value = self._catalog.body.get(key) if self._catalog else None
        return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []

    def redraw(self) -> None:
        rows: list[urwid.Widget] = [self._name_edit]
        if self.note:
            rows.append(text(self.note, "warn"))
        if self.status.get("list") == "loading":
            rows.append(text("Reading the catalog..."))
        elif self.status.get("list") == "error":
            rows.append(text(self.errors["list"], "fail"))
        else:
            kind = "profile" if self.mode == "profiles" else "unit"
            rows.append(
                text(
                    ("Profiles" if kind == "profile" else "Units")
                    + "   (Tab switches; Enter plans the install; U plans an uninstall; G = asks you to type yes first)",
                    "dim",
                )
            )
            for entry in self._entries("profiles" if kind == "profile" else "packages"):
                row = Row(
                    profile_text(entry) if kind == "profile" else unit_text(entry), (kind, entry)
                )
                urwid.connect_signal(row, "activate", self._open)
                rows.append(row)
        self.set_rows(rows)
        self._focus_highlight()
        self._focus_changed()

    def _focus_highlight(self) -> None:
        if not self._highlight:
            return
        for index, row in enumerate(self._walker):
            value = getattr(row, "value", None)
            if isinstance(value, tuple) and value[1].get("name") == self._highlight:
                self._walker.set_focus(index)
                self._highlight = None
                return

    def _focus_changed(self) -> None:
        value = self.focused_value()
        lines: list[str] = []
        if isinstance(value, tuple) and value[0] == "profile":
            docs = value[1].get("documentation")
            docs = docs if isinstance(docs, dict) else {}
            for label, key in (
                ("Why together", "why_together"),
                ("Set up by hand afterwards", "manual_configuration"),
                ("Disk", "disk_footprint_hint"),
            ):
                if docs.get(key):
                    lines.append(f"{label}: {docs[key]}")
        elif isinstance(value, tuple):
            lines.append(
                f"{value[1].get('summary') or ''}  [{', '.join(str(c) for c in value[1].get('categories') or [])}]"
            )
        self._detail.set_text(clean("\n".join(lines)))

    def _open(self, row: Row) -> None:
        self._plan("install", row)

    def _plan(self, action: str, row: Any) -> None:
        value = getattr(row, "value", None)
        if isinstance(value, tuple) and isinstance(value[1].get("name"), str):
            self.ctx.push(PlanScreen(self.ctx, action, [value[1]["name"]]))

    def _submit_name(self) -> None:
        names = self._name_edit.edit_text.split()
        if not names:
            return
        if any(name.startswith("-") for name in names):
            self.note = "A name does not start with '-'. Nothing was run."
            self.redraw()
            return
        self.note = ""
        self.ctx.push(PlanScreen(self.ctx, "install", names))

    def keypress(self, key: str) -> str | None:
        if key == "tab":
            self.mode = "units" if self.mode == "profiles" else "profiles"
            self.redraw()
            return None
        if key == "enter" and self._walker.get_focus()[0] is self._name_edit:
            self._submit_name()
            return None
        if key == "U" and self.mode == "profiles":
            focus = self._walker.get_focus()[0]
            self._plan("uninstall", focus)
            return None
        if key == "i" and self.mode == "profiles":
            value = self.focused_value()
            if isinstance(value, tuple) and isinstance(value[1].get("name"), str):
                from hammunition.console.screens.help import ProfileDocsScreen

                self.ctx.push(ProfileDocsScreen(self.ctx, value[1]["name"]))
                return None
        return key
