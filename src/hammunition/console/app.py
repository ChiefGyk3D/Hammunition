# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The application shell: the screen stack, the one-line header, global keys,
the size guard, fatal-error screens, the crash log and the main loop."""

from __future__ import annotations

import importlib
import os
import signal
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

import urwid

from hammunition.console import config as config_mod
from hammunition.console.config import SCREENS, Config
from hammunition.console.context import EngineLike, Shared
from hammunition.console.engine import Engine
from hammunition.console.fmt import clean
from hammunition.console.screens.base import MessageScreen, Screen
from hammunition.console.worker import Background, ThreadBackground
from hammunition.interface.envelope import engine_version as _engine_version

MIN_COLS, MIN_ROWS = 80, 24
FOOTER = "b back   ? help   q quit   r refresh   Enter open"
SCREEN_CLASSES = {
    "home": "hammunition.console.screens.home:HomeScreen",
    "install": "hammunition.console.screens.install:InstallScreen",
    "station": "hammunition.console.screens.station:StationScreen",
    "logs": "hammunition.console.screens.logs:LogsScreen",
    "update": "hammunition.console.screens.update:UpdateScreen",
    "help": "hammunition.console.screens.help:HelpScreen",
}


def palette(theme: str) -> list[tuple[str, ...]]:
    if theme == "light":
        return [
            ("header", "white", "dark blue"),
            ("footer", "black", "light gray"),
            ("title", "black,bold", "light gray"),
            ("focus", "white", "dark blue"),
            ("key", "dark blue,bold", "default"),
            ("warn", "brown", "default"),
            ("fail", "dark red", "default"),
            ("ok", "dark green", "default"),
            ("dim", "dark gray", "default"),
        ]
    return [
        ("header", "white", "dark blue"),
        ("footer", "black", "light gray"),
        ("title", "white,bold", "dark gray"),
        ("focus", "black", "light cyan"),
        ("key", "yellow", "default"),
        ("warn", "yellow", "default"),
        ("fail", "light red", "default"),
        ("ok", "light green", "default"),
        ("dim", "dark gray", "default"),
    ]


class SizeGuard(urwid.WidgetWrap):
    """Draws a one-line request instead of the screen when the terminal is under 80x24."""

    def __init__(self, inner: urwid.Widget) -> None:
        self._inner = inner
        self.too_small = False
        super().__init__(inner)

    @staticmethod
    def _too_small(size: tuple[int, int]) -> bool:
        return size[0] < MIN_COLS or size[1] < MIN_ROWS

    def render(self, size: Any, focus: bool = False) -> Any:
        self.too_small = self._too_small(size)
        if self.too_small:
            message = f"Please enlarge the terminal to at least {MIN_COLS}x{MIN_ROWS} (it is {size[0]}x{size[1]})."
            return urwid.Filler(urwid.Text(message), "top").render(size, focus)
        return self._inner.render(size, focus)

    def keypress(self, size: Any, key: str) -> str | None:
        return key if self._too_small(size) else self._inner.keypress(size, key)


class Shell:
    def __init__(
        self,
        engine: EngineLike,
        config: Config,
        bg: Background,
        *,
        pane_factory: Callable[[Sequence[str], str, Callable[[int | None], None]], Screen],
        after: Callable[[float, Callable[[], None]], None],
        registry: Mapping[str, Callable[..., Screen]] | None = None,
        save: Callable[[Config], Any] | None = None,
    ) -> None:
        self.engine = engine
        self.config = config
        self.bg = bg
        self.shared = Shared()
        self.stack: list[Screen] = []
        self.registry = dict(registry or {})
        self._pane_factory = pane_factory
        self._after = after
        self._save = save or (lambda cfg: config_mod.save(cfg))
        self._header = urwid.Text("", wrap="clip")
        self._frame = urwid.Frame(
            urwid.SolidFill(" "),
            header=urwid.AttrMap(self._header, "header"),
            footer=urwid.AttrMap(urwid.Text(FOOTER, wrap="clip"), "footer"),
        )
        self.root: urwid.Widget = SizeGuard(self._frame)
        self.refresh_header()

    # -- Context ---------------------------------------------------------
    def _show(self, screen: Screen) -> None:
        title = urwid.AttrMap(urwid.Text(" " + clean(screen.title), wrap="clip"), "title")
        self._frame.body = urwid.Frame(screen.widget(), header=title)
        screen.on_show()

    def push(self, screen: Screen) -> None:
        self.stack.append(screen)
        self._show(screen)

    def pop(self, count: int = 1) -> None:
        popped = False
        for _ in range(count):
            if len(self.stack) > 1:
                self.stack.pop().on_hide()
                popped = True
        if popped:
            self._show(self.stack[-1])

    def replace(self, screen: Screen) -> None:
        if self.stack:
            self.stack.pop().on_hide()
        self.push(screen)

    def open_screen(self, name: str, **kwargs: Any) -> None:
        if name == "home":
            for screen in self.stack:
                screen.on_hide()
            self.stack.clear()
        screen_class = self.registry[name]
        screen = screen_class(self, **kwargs)
        if name in SCREENS:
            self.config.last_screen = name
            self.save_config()
        self.push(screen)

    def run_pane(
        self, argv: Sequence[str], title: str, on_exit: Callable[[int | None], None]
    ) -> None:
        self.push(self._pane_factory(argv, title, on_exit))

    def fatal(self, exc: BaseException) -> None:
        for screen in self.stack:
            screen.on_hide()
        self.stack.clear()
        self.push(MessageScreen(self, "Cannot continue", [str(exc), "", "Press q to quit."]))

    def refresh_header(self) -> None:
        self._header.set_text(clean(self.shared.header_text()))

    def after(self, seconds: float, fn: Callable[[], None]) -> None:
        self._after(seconds, fn)

    def save_config(self) -> None:
        self._save(self.config)

    # -- keys ------------------------------------------------------------
    def handle_key(self, key: Any) -> None:
        if not isinstance(key, str) or not self.stack:
            return
        if isinstance(self.root, SizeGuard) and self.root.too_small:
            # Only the message is on screen: no hidden screen may act on a key.
            if key == "q" and not self._pane_running():
                raise urwid.ExitMainLoop
            return
        top = self.stack[-1]
        if top.keypress(key) is None:
            return
        if key == "q":
            if not self._pane_running():
                raise urwid.ExitMainLoop
            return
        if key in ("b", "esc"):
            self.pop()
        elif key == "?":
            self.open_screen("help", about=top.name)
        elif key == "r":
            top.on_show()

    def _pane_running(self) -> bool:
        """True while an unfinished pane is anywhere on the stack: quitting would make
        urwid's exit kill the engine mid-transaction. Only SIGHUP ends a run."""
        return any(s.name == "pane" and not getattr(s, "finished", False) for s in self.stack)

    def hangup(self) -> NoReturn:
        for screen in self.stack:
            getattr(screen, "on_hangup", lambda: None)()
        raise urwid.ExitMainLoop


def _lazy(path: str) -> Callable[..., Screen]:
    def factory(ctx: Any, **kwargs: Any) -> Screen:
        module, _, cls = path.partition(":")
        screen: Screen = getattr(importlib.import_module(module), cls)(ctx, **kwargs)
        return screen

    return factory


def build_registry() -> dict[str, Callable[..., Screen]]:
    return {name: _lazy(path) for name, path in SCREEN_CLASSES.items()}


def write_crash_log(exc: BaseException, directory: Path, engine_version: str = "?") -> Path | None:
    """The exception's type and its frames (file:line in function). Never its message
    and never source lines: a message can carry a station value or plan content."""
    frames = traceback.extract_tb(exc.__traceback__)
    lines = [
        f"hammunition {_engine_version()}",
        f"engine: {clean(engine_version)}",
        f"exception: {type(exc).__name__}",
        "frames (file:line in function; no message, no source):",
    ]
    lines += [f"  {Path(f.filename).name}:{f.lineno} in {f.name}" for f in frames]
    path = directory / "crash.log"
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        return None
    return path


def run(environ: Mapping[str, str], engine: EngineLike | None = None) -> int:
    cfg = config_mod.load(config_mod.config_path(environ))
    engine = Engine(environ=environ) if engine is None else engine
    bg = ThreadBackground()
    loop_box: list[urwid.MainLoop] = []

    def after(seconds: float, fn: Callable[[], None]) -> None:
        loop_box[0].set_alarm_in(seconds, lambda *_: fn())

    def pane_factory(
        argv: Sequence[str], title: str, on_exit: Callable[[int | None], None]
    ) -> Screen:
        # pane.py arrives in a later task; resolved by name until then.
        pane_class = importlib.import_module("hammunition.console.pane").PaneScreen
        screen: Screen = pane_class(shell, argv, title, on_exit, loop=loop_box[0], environ=environ)
        return screen

    shell = Shell(
        engine,
        cfg,
        bg,
        pane_factory=pane_factory,
        after=after,
        registry=build_registry(),
        save=lambda c: config_mod.save(c, config_mod.config_path(environ)),
    )
    loop = urwid.MainLoop(shell.root, palette(cfg.theme), unhandled_input=shell.handle_key)
    loop_box.append(loop)
    bg.attach(loop)
    signal.signal(signal.SIGHUP, lambda *_: shell.hangup())

    def start(*_: Any) -> None:
        shell.open_screen("home")
        if cfg.last_screen != "home":
            shell.open_screen(cfg.last_screen)

    loop.set_alarm_in(0, start)  # the first on_show runs under the live loop
    return run_guarded(loop.run, environ, shell)


def run_guarded(body: Callable[[], object], environ: Mapping[str, str], shell: Shell) -> int:
    """Run the loop; an exception from it (or a startup alarm) becomes a crash log and exit 1."""
    try:
        body()
    except Exception as exc:
        path = write_crash_log(exc, config_mod.config_dir(environ), shell.shared.engine_version)
        where = f" Details (no message text) are in {path}." if path else ""
        print(f"hammunition console crashed: {type(exc).__name__}.{where}", file=sys.stderr)
        return 1
    return 0
