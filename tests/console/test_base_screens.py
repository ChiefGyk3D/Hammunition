# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import urwid

from hammunition.console.context import Shared
from hammunition.console.engine import EngineMissing, EngineRefused, UnknownSchema
from hammunition.console.screens.base import (
    ConfirmScreen,
    MessageScreen,
    PromptScreen,
    Row,
    Screen,
    describe_error,
    text,
)

from .helpers import FakeContext, render


def test_shared_header_text_says_unknown_until_known_and_never_a_value() -> None:
    s = Shared()
    assert s.header_text() == "hammunition ? | ? | doctor ? | station ?"
    s.engine_version, s.target, s.doctor, s.station_set = "0.20.0", "Debian 13", (1, 2, 20), True
    assert s.header_text() == "hammunition 0.20.0 | Debian 13 | doctor 1F 2W | station set"
    s.station_set = False
    assert s.header_text().endswith("station not set")


def test_row_cleans_its_text_and_activates_on_enter() -> None:
    row = Row("a\x1b[2Jb", value=7)
    seen: list[object] = []
    urwid.connect_signal(row, "activate", lambda r: seen.append(r.value))
    assert row.keypress((20,), "enter") is None and seen == [7]
    assert row.keypress((20,), "x") == "x"
    assert "\x1b" not in render(urwid.Filler(row, "top"), 20, 3)


def test_a_non_selectable_row_ignores_enter() -> None:
    assert Row("x", selectable=False).keypress((5,), "enter") == "enter"


def test_describe_error() -> None:
    assert "exit 2" in describe_error(EngineRefused(2, "nope\nmore")) and "nope" in describe_error(
        EngineRefused(2, "nope\nmore")
    )
    assert "\x1b" not in describe_error(EngineRefused(2, "\x1b[2Jbad"))
    assert describe_error(ValueError("v")) == "ValueError: v"


class Demo(Screen):
    name = "demo"
    title = "Demo"

    def __init__(self, ctx: FakeContext) -> None:
        super().__init__(ctx)
        self.values: list[int] = []

    def redraw(self) -> None:
        self.set_rows([text(f"values: {self.values} state: {self.status.get('n')}")])


def test_load_runs_the_call_and_redraws() -> None:
    ctx = FakeContext()
    demo = Demo(ctx)
    demo.load("n", lambda: 5, lambda v: demo.values.append(v))
    assert demo.values == [5] and demo.status["n"] == "ok"
    assert "values: [5]" in render(demo.widget())


def test_load_records_an_error_and_never_retries() -> None:
    ctx = FakeContext()
    demo = Demo(ctx)
    calls: list[int] = []

    def boom() -> int:
        calls.append(1)
        raise EngineRefused(2, "refused here")

    demo.load("n", boom, lambda v: None)
    assert demo.status["n"] == "error" and "refused here" in demo.errors["n"] and calls == [1]


def test_a_fatal_engine_error_goes_to_the_context_not_the_screen() -> None:
    ctx = FakeContext()
    demo = Demo(ctx)
    demo.load("n", lambda: (_ for _ in ()).throw(EngineMissing("no engine")), lambda v: None)
    assert [type(e) for e in ctx.fatals] == [EngineMissing]
    ctx2 = FakeContext()
    Demo(ctx2).load("n", lambda: (_ for _ in ()).throw(UnknownSchema("schema")), lambda v: None)
    assert [type(e) for e in ctx2.fatals] == [UnknownSchema]


def test_prompt_submits_the_trimmed_text_and_pops_first() -> None:
    ctx = FakeContext()
    got: list[str] = []
    prompt = PromptScreen(ctx, "Set", "value: ", got.append)
    edit = prompt._edit
    edit.set_edit_text("  hello  ")
    assert prompt.keypress("enter") is None
    assert got == ["hello"] and ctx.popped == 1


def test_confirm_runs_only_on_capital_r() -> None:
    ctx = FakeContext()
    ran: list[int] = []
    screen = ConfirmScreen(ctx, "Run?", ["this runs a command"], lambda: ran.append(1))
    assert screen.keypress("r") == "r" and ran == []
    assert screen.keypress("R") is None and ran == [1] and ctx.popped == 1
    assert "changes nothing" in render(screen.widget())


def test_message_screen_shows_its_lines() -> None:
    assert "line two" in render(
        MessageScreen(FakeContext(), "Title", ["line one", "line two"]).widget()
    )
