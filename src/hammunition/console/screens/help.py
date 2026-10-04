# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import urwid

from hammunition.console.context import Context
from hammunition.console.engine import Document
from hammunition.console.fmt import clean
from hammunition.console.helptext import EXIT_CODES, KEYS, NEVER, SCREEN_HELP
from hammunition.console.screens.base import Row, Screen, text


def profile_lines(body: Mapping[str, Any]) -> list[str]:
    """What a profile is for, from the engine's `show` document. Never the gate's variable name."""
    docs = body.get("documentation")
    docs = docs if isinstance(docs, dict) else {}
    lines = [
        f"{clean(body.get('name') or '?')}  ({clean(body.get('stage') or '')})  {clean(body.get('summary') or '')}",
        "",
    ]
    for label, key in (
        ("What it installs", "what_it_installs"),
        ("Why these belong together", "why_together"),
        ("What it deliberately leaves out", "deliberately_excludes"),
        ("What you still set up by hand", "manual_configuration"),
        ("Disk", "disk_footprint_hint"),
    ):
        if docs.get(key):
            lines += [f"{label}:", f"  {clean(docs[key]).strip()}", ""]
    consent = body.get("consent")
    if isinstance(consent, dict) and consent.get("disclosure"):
        lines += [
            "You will be asked to type yes before this installs. The engine shows exactly this:",
            *[f"  {clean(row)}" for row in str(consent["disclosure"]).splitlines()],
            "",
        ]
    packages = body.get("packages")
    if isinstance(packages, list) and packages:
        lines += [f"Units ({len(packages)}): " + ", ".join(clean(p) for p in packages)]
    for s in body.get("suggests_one_of") or []:
        if isinstance(s, dict):
            lines.append(
                f"Choose one of {', '.join(clean(o) for o in s.get('options') or [])} for {clean(s.get('name') or '?')}"
                + (f" (recommended {clean(s['recommended'])})" if s.get("recommended") else "")
                + (f": {clean(s['reason'])}" if s.get("reason") else "")
            )
    return lines


class ProfileDocsScreen(Screen):
    name = "profile"

    def __init__(self, ctx: Context, profile: str) -> None:
        super().__init__(ctx)
        self.profile = profile
        self.title = f"Profile: {profile}"
        self._doc: Document | None = None

    def on_show(self) -> None:
        self.load(
            "show",
            lambda: self.ctx.engine.read("show", self.profile),
            lambda d: setattr(self, "_doc", d),
        )
        self.redraw()

    def redraw(self) -> None:
        if self.status.get("show") == "error":
            self.set_rows([text(self.errors["show"], "fail")])
        elif self._doc is not None:
            self.set_rows([text(line) for line in profile_lines(self._doc.body)])
        else:
            self.set_rows([text("Reading the profile...")])


class HelpScreen(Screen):
    name = "help"
    title = "Help"

    def __init__(self, ctx: Context, about: str = "") -> None:
        super().__init__(ctx)
        self._about = about
        self._catalog: Document | None = None

    def on_show(self) -> None:
        self.load(
            "list", lambda: self.ctx.engine.read("list"), lambda d: setattr(self, "_catalog", d)
        )
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self._about in SCREEN_HELP:
            rows += (
                [text(f"This screen ({self._about})", "key")]
                + [text(line) for line in SCREEN_HELP[self._about]]
                + [text("")]
            )
        rows += (
            [text("Keys", "key")]
            + [text(f"  {keys:<10} {meaning}") for keys, meaning in KEYS]
            + [text("")]
        )
        rows += (
            [text("What the console never does", "key")]
            + [text(f"  {line}") for line in NEVER]
            + [text("")]
        )
        rows += (
            [text("Exit codes", "key")]
            + [text(f"  {code:<10} {meaning}") for code, meaning in EXIT_CODES]
            + [text("")]
        )
        rows.append(text("Profiles (Enter shows what each is for)", "key"))
        if self.status.get("list") == "error":
            rows.append(text(self.errors["list"], "fail"))
        elif self._catalog is not None:
            for entry in self._catalog.body.get("profiles") or []:
                if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    row = Row(
                        f"  {clean(entry['name']):<18} {clean(entry.get('summary') or '')}",
                        entry["name"],
                    )
                    urwid.connect_signal(row, "activate", self._open)
                    rows.append(row)
        else:
            rows.append(text("  reading the profiles..."))
        self.set_rows(rows)

    def _open(self, row: Row) -> None:
        self.ctx.push(ProfileDocsScreen(self.ctx, str(row.value)))
