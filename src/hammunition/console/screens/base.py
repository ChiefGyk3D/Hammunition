# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar, cast

import urwid

from hammunition.console.context import Context
from hammunition.console.engine import EngineMissing, EngineRefused, UnknownSchema
from hammunition.console.fmt import clean

T = TypeVar("T")
FATAL: tuple[type[Exception], ...] = (EngineMissing, UnknownSchema)


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, EngineRefused):
        return clean(f"the engine refused (exit {exc.exit_code}): {exc.message.strip()}")
    return clean(f"{type(exc).__name__}: {exc}")


def text(content: str, attr: str | None = None) -> urwid.Widget:
    return urwid.AttrMap(urwid.Text(clean(content)), attr)


class Row(urwid.WidgetWrap):
    """One line of a list. Enter emits `activate` with the row; `value` is the caller's."""

    signals = ["activate"]  # noqa: RUF012  (urwid reads this class list)

    def __init__(
        self,
        content: str,
        value: object = None,
        *,
        attr: str | None = None,
        selectable: bool = True,
    ) -> None:
        self.value = value
        self._selectable = selectable
        self._text = urwid.Text(clean(content), wrap="clip")
        super().__init__(urwid.AttrMap(self._text, attr, focus_map="focus"))

    def selectable(self) -> bool:
        return self._selectable

    def set_text(self, content: str) -> None:
        self._text.set_text(clean(content))

    def keypress(self, size: Any, key: str) -> str | None:
        if key == "enter" and self._selectable:
            urwid.emit_signal(self, "activate", self)
            return None
        return key


class Screen:
    """A screen: rows in a list, loaded from the engine, redrawn from state."""

    name = ""
    title = ""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.status: dict[str, str] = {}
        self.errors: dict[str, str] = {}
        self._walker: urwid.SimpleFocusListWalker[urwid.Widget] = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)

    def widget(self) -> urwid.Widget:
        return self._list

    def on_show(self) -> None:
        """Called on first show and again whenever the screen is returned to or refreshed."""

    def on_hide(self) -> None:
        pass

    def keypress(self, key: str) -> str | None:
        """Keys the focused widget did not take. Return None when handled."""
        return key

    def redraw(self) -> None:
        pass

    def set_rows(self, rows: Sequence[urwid.Widget]) -> None:
        position = self._walker.focus if len(self._walker) else 0
        self._walker[:] = list(rows)
        if rows:
            self._walker.set_focus(min(position or 0, len(rows) - 1))

    def focused_value(self) -> object:
        widget = self._walker.get_focus()[0] if len(self._walker) else None
        return getattr(widget, "value", None)

    def load(self, key: str, call: Callable[[], T], done: Callable[[T], None]) -> None:
        self.status[key] = "loading"
        self.errors.pop(key, None)

        def finished(result: T | None, error: BaseException | None) -> None:
            if error is None:
                self.status[key] = "ok"
                done(cast(T, result))
            elif isinstance(error, FATAL):
                self.ctx.fatal(error)
                return
            else:
                self.status[key] = "error"
                self.errors[key] = describe_error(error)
            self.redraw()

        self.ctx.bg.submit(call, finished)


class PromptScreen(Screen):
    """One line of typed input. Enter submits (empty means the caller treats it as cancel)."""

    name = "prompt"

    def __init__(
        self,
        ctx: Context,
        title: str,
        label: str,
        on_submit: Callable[[str], None],
        *,
        note: str = "",
        mask: str | None = None,
        initial: str = "",
    ) -> None:
        super().__init__(ctx)
        self.title = title
        self._on_submit = on_submit
        self._edit = urwid.Edit(label, edit_text=initial, mask=mask)
        rows: list[urwid.Widget] = [
            text(note),
            self._edit,
            text(
                "Enter accepts; Esc cancels (b is typed into the box). Nothing is saved by the console itself."
            ),
        ]
        self._walker[:] = rows
        self._walker.set_focus(1)

    def keypress(self, key: str) -> str | None:
        if key == "enter":
            value = self._edit.edit_text.strip()
            self._edit.set_edit_text("")  # a masked value does not outlive its submission
            self.ctx.pop()
            self._on_submit(value)
            return None
        return key


class ConfirmScreen(Screen):
    """Shows what will run. Capital R runs it in a pane; Back changes nothing."""

    name = "confirm"

    def __init__(
        self, ctx: Context, title: str, lines: Sequence[str], on_confirm: Callable[[], None]
    ) -> None:
        super().__init__(ctx)
        self.title = title
        self._on_confirm = on_confirm
        self._walker[:] = [text(line) for line in lines] + [
            text(""),
            text("R run this in a terminal pane   b back (changes nothing)", "key"),
        ]

    def keypress(self, key: str) -> str | None:
        if key == "R":
            self.ctx.pop()
            self._on_confirm()
            return None
        return key


class MessageScreen(Screen):
    name = "message"

    def __init__(self, ctx: Context, title: str, lines: Sequence[str]) -> None:
        super().__init__(ctx)
        self.title = title
        self._walker[:] = [text(line) for line in lines]
