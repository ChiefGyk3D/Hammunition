# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
from typing import Any

import pytest
import urwid

from hammunition.console.app import (
    MIN_COLS,
    MIN_ROWS,
    Shell,
    SizeGuard,
    palette,
    run_guarded,
    write_crash_log,
)
from hammunition.console.config import Config
from hammunition.console.engine import EngineMissing, UnknownSchema
from hammunition.console.screens.base import Screen, text
from hammunition.console.worker import SyncBackground
from hammunition.interface.envelope import engine_version

from .helpers import FakeEngine, render


class Stub(Screen):
    def __init__(self, ctx: Any, name: str = "stub", **kw: Any) -> None:
        super().__init__(ctx)
        self.name, self.title = name, name.title()
        self.shown = self.hidden = 0
        self.kw = kw
        self.keys: list[str] = []

    def on_show(self) -> None:
        self.shown += 1
        self.redraw()

    def on_hide(self) -> None:
        self.hidden += 1

    def redraw(self) -> None:
        self.set_rows([text(f"{self.name} screen")])

    def keypress(self, key: str) -> str | None:
        self.keys.append(key)
        return None if key == "x" else key


def make(saved: list[Config] | None = None) -> Shell:
    registry: dict[str, Any] = {
        n: (lambda ctx, n=n, **kw: Stub(ctx, n, **kw)) for n in ("home", "install", "help")
    }
    sh = Shell(
        FakeEngine(),
        Config(),
        SyncBackground(),
        pane_factory=lambda argv, title, on_exit: Stub(sh, "pane"),
        after=lambda s, f: None,
        registry=registry,
        save=(saved.append if saved is not None else lambda c: None),
    )
    return sh


def test_open_screen_pushes_and_back_pops_and_reshows() -> None:
    sh = make()
    sh.open_screen("home")
    sh.open_screen("install")
    assert [s.name for s in sh.stack] == ["home", "install"]
    sh.handle_key("b")
    assert [s.name for s in sh.stack] == ["home"] and sh.stack[0].shown == 2  # type: ignore[attr-defined]


def test_pop_can_unwind_several_screens_and_shows_only_the_last() -> None:
    sh = make()
    sh.open_screen("home")
    sh.open_screen("install")
    sh.open_screen("help")
    home: Stub = sh.stack[0]  # type: ignore[assignment]
    install: Stub = sh.stack[1]  # type: ignore[assignment]
    sh.pop(2)
    assert [s.name for s in sh.stack] == ["home"] and home.shown == 2 and install.shown == 1
    sh.pop(5)
    assert len(sh.stack) == 1 and home.shown == 2  # nothing popped, nothing re-shown


def test_back_on_the_root_screen_does_nothing() -> None:
    sh = make()
    sh.open_screen("home")
    sh.handle_key("b")
    sh.handle_key("esc")
    assert len(sh.stack) == 1


def test_open_home_resets_the_stack_and_kwargs_reach_the_factory() -> None:
    sh = make()
    sh.open_screen("home")
    sh.open_screen("install", highlight="station")
    assert sh.stack[-1].kw == {"highlight": "station"}  # type: ignore[attr-defined]
    sh.open_screen("home")
    assert [s.name for s in sh.stack] == ["home"]


def test_last_screen_is_saved_when_a_top_level_screen_opens() -> None:
    saved: list[Config] = []
    sh = make(saved)
    sh.open_screen("install")
    assert sh.config.last_screen == "install" and saved and saved[-1].last_screen == "install"


def test_the_screen_gets_the_first_chance_at_a_key_then_the_globals() -> None:
    sh = make()
    sh.open_screen("home")
    top: Stub = sh.stack[-1]  # type: ignore[assignment]
    sh.handle_key("x")
    assert top.keys == ["x"] and len(sh.stack) == 1
    sh.handle_key("?")
    assert sh.stack[-1].name == "help" and sh.stack[-1].kw == {"about": "home"}  # type: ignore[attr-defined]


def test_q_quits() -> None:
    sh = make()
    sh.open_screen("home")
    with pytest.raises(urwid.ExitMainLoop):
        sh.handle_key("q")


def test_r_refreshes_the_current_screen() -> None:
    sh = make()
    sh.open_screen("home")
    sh.handle_key("r")
    assert sh.stack[-1].shown == 2  # type: ignore[attr-defined]


def test_mouse_events_are_ignored() -> None:
    sh = make()
    sh.open_screen("home")
    sh.handle_key(("mouse press", 1, 2, 3))  # type: ignore[arg-type]


def test_the_header_is_one_line_and_never_a_station_value() -> None:
    sh = make()
    sh.open_screen("home")
    sh.shared.engine_version, sh.shared.target, sh.shared.doctor, sh.shared.station_set = (
        "0.20.0",
        "Debian 13",
        (0, 1, 9),
        True,
    )
    sh.refresh_header()
    first = render(sh.root, 80, 24).splitlines()[0]
    assert first == "hammunition 0.20.0 | Debian 13 | doctor 0F 1W | station set"
    assert len(first) <= 80


def test_the_size_guard_asks_for_a_bigger_terminal_below_80x24() -> None:
    sh = make()
    sh.open_screen("home")
    assert f"{MIN_COLS}x{MIN_ROWS}" in render(sh.root, 79, 24)
    assert f"{MIN_COLS}x{MIN_ROWS}" in render(sh.root, 80, 23)
    assert f"{MIN_COLS}x{MIN_ROWS}" not in render(sh.root, 80, 24)
    assert isinstance(sh.root, SizeGuard) and sh.root.keypress((79, 24), "x") == "x"


@pytest.mark.parametrize(
    "exc,needle",
    [
        (EngineMissing("hammunition was not found on PATH"), "not found on PATH"),
        (UnknownSchema("a document of schema 'hammunition/9'"), "hammunition/9"),
    ],
)
def test_a_fatal_engine_error_replaces_everything_with_one_screen(
    exc: Exception, needle: str
) -> None:
    sh = make()
    sh.open_screen("home")
    sh.open_screen("install")
    sh.fatal(exc)
    assert len(sh.stack) == 1 and needle in render(sh.root, 100, 24)
    assert "q to quit" in render(sh.root, 100, 24)


def test_a_pane_is_pushed_and_hangup_notifies_every_screen() -> None:
    sh = make()
    sh.open_screen("home")
    called: list[str] = []
    for s in sh.stack:
        s.on_hangup = lambda: called.append("h")  # type: ignore[attr-defined]
    sh.run_pane(["hammunition", "install", "station"], "install station", lambda code: None)
    assert sh.stack[-1].name == "pane"
    with pytest.raises(urwid.ExitMainLoop):
        sh.hangup()
    assert called == ["h"]


def test_palettes_cover_every_attribute_the_screens_use() -> None:
    needed = {"header", "footer", "title", "focus", "key", "warn", "fail", "ok", "dim"}
    for theme in ("dark", "light"):
        assert needed <= {entry[0] for entry in palette(theme)}


def test_crash_log_has_the_exception_type_and_frames_but_no_message(tmp_path: Path) -> None:
    sentinel = "ZZ9SENTINEL"

    def inner() -> None:
        raise RuntimeError(f"callsign {sentinel}")

    try:
        inner()
    except RuntimeError as exc:
        path = write_crash_log(exc, tmp_path / "cfg")
    assert path is not None
    content = path.read_text()
    assert "RuntimeError" in content and "inner" in content and engine_version() in content
    assert sentinel not in content
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_a_too_small_terminal_blocks_every_key_but_q() -> None:
    sh = make()
    sh.open_screen("home")
    sh.open_screen("install")
    top: Stub = sh.stack[-1]  # type: ignore[assignment]
    render(sh.root, 79, 24)
    for key in ("R", "b", "esc", "?", "r"):
        sh.handle_key(key)
    assert [s.name for s in sh.stack] == ["home", "install"]
    assert top.keys == [] and top.hidden == 0 and top.shown == 1
    with pytest.raises(urwid.ExitMainLoop):
        sh.handle_key("q")
    render(sh.root, 80, 24)
    sh.handle_key("R")
    assert top.keys == ["R"]
    sh.handle_key("b")
    assert [s.name for s in sh.stack] == ["home"]


def test_a_startup_crash_writes_the_crash_log_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(ctx: Any, **kw: Any) -> Screen:
        raise RuntimeError("callsign ZZ9SENTINEL")

    sh = make()
    sh.registry["home"] = boom
    code = run_guarded(lambda: sh.open_screen("home"), {"XDG_CONFIG_HOME": str(tmp_path)}, sh)
    assert code == 1
    log = (tmp_path / "hammunition-console" / "crash.log").read_text()
    assert "RuntimeError" in log and "ZZ9SENTINEL" not in log
    assert "ZZ9SENTINEL" not in capsys.readouterr().err


def test_q_on_a_too_small_terminal_does_not_end_a_running_pane() -> None:
    sh = make()
    sh.open_screen("home")
    sh.run_pane(["hammunition", "install", "station"], "install station", lambda code: None)
    pane: Any = sh.stack[-1]
    render(sh.root, 79, 24)
    sh.handle_key("q")  # no ExitMainLoop: the child would be killed mid-transaction
    assert sh.stack[-1] is pane and pane.name == "pane"
    pane.finished = True  # type: ignore[attr-defined]
    with pytest.raises(urwid.ExitMainLoop):
        sh.handle_key("q")


def test_q_with_an_unfinished_pane_under_another_screen_is_ignored_when_too_small() -> None:
    sh = make()
    sh.open_screen("home")
    sh.run_pane(["hammunition", "install", "station"], "install station", lambda code: None)
    sh.open_screen("help")
    render(sh.root, 60, 20)
    sh.handle_key("q")
