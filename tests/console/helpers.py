# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared test helpers."""

from __future__ import annotations

import json
import shlex
import stat
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import urwid

from hammunition.console import guard
from hammunition.console.config import Config
from hammunition.console.context import Shared
from hammunition.console.engine import Document, accept, parse_document
from hammunition.console.verbs import require_json_verb
from hammunition.console.worker import Background, SyncBackground

from .fake_hammunition import respond

FIXTURES = Path(__file__).parent / "fixtures"
TESTS_DIR = Path(__file__).resolve().parent.parent  # on PYTHONPATH, `console.<module>` is a harness
REPO = Path(__file__).resolve().parents[2]
SRC_DIR = REPO / "src"
PACKAGE_DIR = SRC_DIR / "hammunition" / "console"
FAKE = Path(__file__).parent / "fake_hammunition.py"


def load(name: str) -> dict[str, Any]:
    """A recorded fixture's document, by file stem."""
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    assert isinstance(data, dict)
    return data


def make_shim(directory: Path) -> Path:
    """A directory holding an executable `hammunition` that runs the fake with this interpreter."""
    bin_dir = directory / "shim-bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "hammunition"
    shim.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} "$@"\n'
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def render(widget: urwid.Widget, cols: int = 80, rows: int = 24) -> str:
    """A box widget drawn to text, trailing blanks trimmed."""
    canvas = widget.render((cols, rows), focus=True)
    return "\n".join(line.decode("utf-8").rstrip() for line in canvas.text)


class FakeEngine:
    """Answers reads from the fixtures through the same mapping the fake script uses."""

    binary = "hammunition"

    def __init__(self, suffix: str = "", station: str = "set") -> None:
        self.suffix, self.station = suffix, station
        self.calls: list[tuple[str, ...]] = []
        self.timeouts: dict[tuple[str, ...], float | None] = {}
        self.refused: list[
            tuple[str, ...]
        ] = []  # reads with no --json form: a bug in a screen, however it is handled
        self._overrides: dict[tuple[str, ...], Document | BaseException] = {}

    def command(self, *words: str) -> list[str]:
        return [self.binary, *words]

    def set(self, words: Sequence[str], result: Document | BaseException) -> None:
        self._overrides[tuple(words)] = result

    def read(self, *words: str, timeout: float | None = 180.0) -> Document:
        self.timeouts[tuple(words)] = timeout
        try:
            require_json_verb(words)
        except BaseException:
            self.refused.append(tuple(words))
            raise
        guard.assert_clean_read(words)
        self.calls.append(tuple(words))
        override = self._overrides.get(tuple(words))
        if isinstance(override, BaseException):
            raise override
        if override is not None:
            return override
        answered = respond(["hammunition", *words, "--json"], FIXTURES, self.suffix, self.station)
        assert answered is not None, f"no fixture maps {words}"
        return accept(parse_document(answered[0], answered[1]))


def document(
    kind: str, body: Mapping[str, Any] | None = None, *, exit_code: int = 0, engine: str = "0.20.0"
) -> Document:
    """A Document built in a test (for a shape no fixture has)."""
    full = {"schema": "hammunition/1", "kind": kind, "engine": engine, **(body or {})}
    return Document(kind, engine, "hammunition/1", exit_code, full)


@dataclass
class PaneRequest:
    argv: list[str]
    title: str
    on_exit: Callable[[int | None], None]


@dataclass
class FakeContext:
    engine: Any = field(default_factory=FakeEngine)
    config: Config = field(default_factory=Config)
    bg: Background = field(default_factory=SyncBackground)
    shared: Shared = field(default_factory=Shared)
    pushed: list[Any] = field(default_factory=list)
    replaced: list[Any] = field(default_factory=list)
    opened: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    panes: list[PaneRequest] = field(default_factory=list)
    timers: list[tuple[float, Callable[[], None]]] = field(default_factory=list)
    fatals: list[BaseException] = field(default_factory=list)
    popped: int = 0
    saved: int = 0
    header_refreshes: int = 0

    def push(self, screen: Any) -> None:
        self.pushed.append(screen)
        screen.on_show()

    def pop(self, count: int = 1) -> None:
        self.popped += count

    def replace(self, screen: Any) -> None:
        self.replaced.append(screen)
        screen.on_show()

    def open_screen(self, name: str, **kwargs: Any) -> None:
        self.opened.append((name, kwargs))

    def run_pane(
        self, argv: Sequence[str], title: str, on_exit: Callable[[int | None], None]
    ) -> None:
        self.panes.append(PaneRequest(guard.checked_argv(argv), title, on_exit))

    def fatal(self, exc: BaseException) -> None:
        self.fatals.append(exc)

    def refresh_header(self) -> None:
        self.header_refreshes += 1

    def after(self, seconds: float, fn: Callable[[], None]) -> None:
        self.timers.append((seconds, fn))

    def save_config(self) -> None:
        self.saved += 1
