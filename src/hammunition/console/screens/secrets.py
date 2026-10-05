# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Secrets screen (issue #321, D-081): where each secret would come from, and three
ways to supply one. The console never sees a value the engine holds: the engine's
`secrets status` says only which source answers. A value typed here is kept in this
process's memory for the engine commands the console starts, and nowhere else."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import urwid

from hammunition.console.context import Context
from hammunition.console.engine import Document
from hammunition.console.fmt import clean
from hammunition.console.screens.base import (
    ConfirmScreen,
    MessageScreen,
    PromptScreen,
    Row,
    Screen,
    text,
)
from hammunition.console.session import SessionRefused

PLACEHOLDER = re.compile(r"^[A-Z]{2,}$")  # `XX` in the engine's example command
ARGUMENT = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,39}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")  # a Doppler project or config name


def _s(value: object, default: str = "?") -> str:
    return default if value is None else str(value)


class SecretsScreen(Screen):
    name = "secrets"
    title = "Secrets"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self._doc: Document | None = None
        self.note = ""
        self._project = ""

    def on_show(self) -> None:
        self.load("secrets", lambda: self.ctx.engine.read("secrets", "status"), self._store)
        self.redraw()

    def _store(self, doc: Document) -> None:
        self._doc = doc

    def _rows(self) -> list[Mapping[str, Any]]:
        rows = self._doc.body.get("secrets") if self._doc else None
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

    def _current(self) -> Mapping[str, Any] | None:
        value = self.focused_value()
        return value if isinstance(value, dict) else None

    def redraw(self) -> None:
        rows: list[urwid.Widget] = [
            text(
                "Keys for downloads that need one. This shows where each would come from, never "
                "its value. g get one   d use Doppler   e enter for this session   x forget it   f run its command",
                "dim",
            ),
            text(
                "A value you enter is kept in this console's memory only: handed to the engine "
                "commands it starts, written nowhere, cleared when you quit.",
                "dim",
            ),
        ]
        if self.note:
            rows.append(text(self.note, "warn"))
        if self.status.get("secrets") == "error":
            rows.append(text(self.errors["secrets"], "fail"))
        elif self._doc is None:
            rows.append(text("Reading the secrets..."))
        else:
            rows += self._doppler_lines()
            for secret in self._rows():
                rows += self._secret_rows(secret)
        self.set_rows(rows)

    def _doppler_lines(self) -> list[urwid.Widget]:
        d = self._doc.body.get("doppler") if self._doc else None
        d = d if isinstance(d, dict) else {}
        if d.get("configured"):
            line = f"Doppler: project {_s(d.get('project'))}, config {_s(d.get('config'))}"
        else:
            line = "Doppler: not configured (press d on a secret)"
        line += "; `doppler` on PATH" if d.get("cli_on_path") else "; `doppler` not on PATH"
        return [text(""), text(line)]

    def _secret_rows(self, secret: Mapping[str, Any]) -> list[urwid.Widget]:
        name = _s(secret.get("name"))
        in_session = name in self.ctx.session.names()
        if in_session:
            state, attr = "available (entered for this session)", "ok"
        elif secret.get("available"):
            state, attr = f"available (source: {_s(secret.get('source'))})", "ok"
        else:
            state, attr = "not available", "warn"
        row = Row(f"{name}  {state}", secret, attr=attr)
        out: list[urwid.Widget] = [text(""), row, text(f"  {_s(secret.get('purpose'))}", "dim")]
        out.append(text(f"  {_s(secret.get('detail'))}", "dim"))
        if secret.get("unit"):
            out.append(
                text(
                    f"  needs the unit: hammunition install {_s(secret['unit'])} (Install, by name)",
                    "dim",
                )
            )
        out.append(text(f"  first command it unlocks: {_s(secret.get('command'))}", "dim"))
        return out

    def keypress(self, key: str) -> str | None:
        secret = self._current()
        if key not in ("g", "d", "e", "x", "f") or secret is None:
            return key
        name = _s(secret.get("name"))
        if key == "g":
            self.ctx.push(
                MessageScreen(
                    self.ctx,
                    f"Get a {name} token",
                    [
                        f"Open this page in your own browser: {_s(secret.get('get_url'))}",
                        "",
                        f"There, {_s(secret.get('get_how'))}.",
                        "The console opens no browser and fetches nothing. Then press d (Doppler) or e (this session).",
                    ],
                )
            )
        elif key == "d":
            self.ctx.push(
                PromptScreen(
                    self.ctx,
                    "Doppler project",
                    "Project name: ",
                    self._got_project,
                    note="Names only, never a token. Hammunition reads the secret from Doppler when a command needs it.",
                )
            )
        elif key == "e":
            self.ctx.push(
                PromptScreen(
                    self.ctx,
                    f"Enter {name} for this session",
                    "Value (hidden): ",
                    lambda value: self._enter(name, value),
                    note="Kept in this console's memory only. Written nowhere, cleared when you quit.",
                    mask="*",
                )
            )
        elif key == "x":
            self.ctx.session.forget(name)
            self.note = f"The session value for {name} was forgotten."
            self.on_show()
        else:
            self._run_command(secret)
        return None

    def _enter(self, name: str, value: str) -> None:
        if not value:
            return
        try:
            self.ctx.session.set(name, value)
        except SessionRefused as exc:
            self.note = clean(str(exc))
            self.redraw()
            return
        self.note = f"{name} is set for this session. Nothing was written."
        self.on_show()

    def _got_project(self, project: str) -> None:
        if not project:
            return
        if not NAME.match(project):
            self.note = (
                "A Doppler project name is letters, digits, '.', '_' or '-'. Nothing was run."
            )
            self.redraw()
            return
        self._project = project
        self.ctx.push(
            PromptScreen(
                self.ctx,
                "Doppler config",
                "Config name: ",
                self._got_config,
                note=f"Project {project}. Names only, never a token.",
            )
        )

    def _got_config(self, config: str) -> None:
        if not config:
            return
        if not NAME.match(config):
            self.note = (
                "A Doppler config name is letters, digits, '.', '_' or '-'. Nothing was run."
            )
            self.redraw()
            return
        argv = self.ctx.engine.command(
            "station", "set", f"--doppler-project={self._project}", f"--doppler-config={config}"
        )
        self.ctx.push(
            ConfirmScreen(
                self.ctx,
                "Use Doppler",
                [
                    "This runs the engine's own command, which saves two names:",
                    "",
                    "  " + " ".join(argv),
                ],
                lambda: self.ctx.run_pane(argv, "station set --doppler", self._after),
            )
        )

    def _after(self, code: int | None) -> None:
        said = (
            "Saved."
            if code == 0
            else f"The engine run ended with exit {code}; its words were in the pane."
        )
        self.note = said
        self.ctx.pop()
        self.on_show()

    def _run_command(self, secret: Mapping[str, Any]) -> None:
        name = _s(secret.get("name"))
        if not secret.get("available") and name not in self.ctx.session.names():
            self.note = (
                f"No source answers for {name} yet: press e to enter it for this session, "
                "or d to name a Doppler project. Nothing was run."
            )
            self.redraw()
            return
        words = _s(secret.get("command"), "").split()[1:]  # drop `hammunition`
        slots = [i for i, w in enumerate(words) if PLACEHOLDER.match(w)]
        if not words or len(slots) > 1:
            self.note = (
                "The engine's command has no shape the console can fill in. Nothing was run."
            )
            self.redraw()
            return
        if not slots:
            self._confirm(words)
            return
        slot = slots[0]
        self.ctx.push(
            PromptScreen(
                self.ctx,
                "Run the command",
                f"{words[slot]} (e.g. a state): ",
                lambda value: self._filled(words, slot, value),
                note=f"hammunition {' '.join(words)}",
            )
        )

    def _filled(self, words: list[str], slot: int, value: str) -> None:
        if not value:
            return
        if not ARGUMENT.match(value):
            self.note = "That is not a state name or code. Nothing was run."
            self.redraw()
            return
        self._confirm([*words[:slot], value, *words[slot + 1 :]])

    def _confirm(self, words: list[str]) -> None:
        argv = self.ctx.engine.command(*words)
        self.ctx.push(
            ConfirmScreen(
                self.ctx,
                "Run: " + " ".join(words[:3]),
                [
                    "This runs the engine's own command; it prints its terms and asks nothing the console answers:",
                    "",
                    "  " + " ".join(argv),
                ],
                lambda: self.ctx.run_pane(argv, " ".join(words[:3]), self._after_run),
            )
        )

    def _after_run(self, code: int | None) -> None:
        self.note = (
            "The fetch finished."
            if code == 0
            else f"The engine run ended with exit {code}; its words were in the pane."
        )
        self.ctx.pop()
