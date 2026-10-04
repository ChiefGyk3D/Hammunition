# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Any

import pytest

from hammunition.console.config import Config
from hammunition.console.engine import EngineRefused
from hammunition.console.screens.base import ConfirmScreen, PromptScreen
from hammunition.console.screens.station import FIELDS, ChooserScreen, StationScreen, display_value

from .helpers import FakeContext, FakeEngine, document, load, render

SENTINELS = {
    "callsign": "ZZ9SENTINEL",
    "grid_square": "ZZ99zz",
    "node_alias": "SENTALIAS",
    "rig_device": "/dev/serial/by-id/usb-SENTINELSERIAL-if00",
    "map_regions": ["north-america/us/sentinelregion"],
}


def sentinel_ctx() -> FakeContext:
    body = {**load("station-set"), **SENTINELS}
    engine = FakeEngine()
    engine.set(("station", "show"), document("station", body))
    return FakeContext(engine=engine)


def shown(ctx: FakeContext) -> tuple[StationScreen, str]:
    screen = StationScreen(ctx)
    screen.on_show()
    return screen, render(screen.widget(), 100, 30)


def row_for(screen: StationScreen, key: str) -> Any:
    return next(
        r
        for r in screen._walker
        if getattr(r, "value", None) is not None and getattr(r.value, "key", None) == key
    )


def test_secret_values_are_hidden_until_revealed_and_hidden_again_on_leaving() -> None:
    screen, out = shown(sentinel_ctx())
    for secret in (*[v for v in SENTINELS.values() if isinstance(v, str)], "sentinelregion"):
        assert secret not in out, secret
    assert "1 set" in out  # the region count
    assert screen.keypress("v") is None and screen.revealed
    out = render(screen.widget(), 100, 30)
    assert "ZZ9SENTINEL" in out and "ZZ99zz" in out and "sentinelregion" in out
    screen.on_hide()
    assert vars(screen)["revealed"] is False  # read through vars: mypy narrowed it to True above
    assert "ZZ9SENTINEL" not in render(screen.widget(), 100, 30)


def test_nothing_is_set_says_so() -> None:
    _screen, out = shown(FakeContext(engine=FakeEngine(station="none")))
    assert out.count("not set") >= 4 and "Station values are saved by the engine" in out


def test_the_station_screen_stores_nothing_itself() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    screen.keypress("v")
    assert ctx.saved == 0 and ctx.config == Config()


@pytest.mark.parametrize(
    "field,value,shown_as",
    [
        ("callsign", "N0CALL", "********"),
        ("map_regions", ["a", "b"], "2 set"),
        ("node_alias", None, "not set"),
        ("rig_baud", 38400, "38400"),
        ("mirror", "http://lan/", "http://lan/"),
        ("reference_books", [], "not set"),
    ],
)
def test_display_value(field: str, value: Any, shown_as: str) -> None:
    f = next(x for x in FIELDS if x.key == field)
    assert display_value(f, value, revealed=False) == shown_as


def test_revealed_lists_are_joined() -> None:
    f = next(x for x in FIELDS if x.key == "map_regions")
    assert display_value(f, ["a", "b"], revealed=True) == "a, b"


def test_setting_a_value_runs_station_set_with_one_argv_element_and_the_value_is_not_in_the_title() -> (
    None
):
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "callsign").keypress((100,), "enter")
    prompt = ctx.pushed[-1]
    assert isinstance(prompt, PromptScreen)
    prompt._edit.set_edit_text("N0TST")
    prompt.keypress("enter")
    pane = ctx.panes[0]
    assert pane.argv == ["hammunition", "station", "set", "--callsign=N0TST"]
    assert "N0TST" not in pane.title and pane.title == "station set --callsign"


def test_a_value_that_looks_like_a_flag_stays_inside_one_argv_element() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "node_alias").keypress((100,), "enter")
    ctx.pushed[-1]._edit.set_edit_text("--clear-rig")
    ctx.pushed[-1].keypress("enter")
    assert ctx.panes[0].argv == ["hammunition", "station", "set", "--node-alias=--clear-rig"]


def test_an_empty_value_is_a_cancel() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "callsign").keypress((100,), "enter")
    ctx.pushed[-1].keypress("enter")
    assert ctx.panes == []


def test_after_the_pane_the_screen_reads_back_and_reports_the_engines_exit_code_not_its_own_opinion() -> (
    None
):
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "node_alias").keypress((100,), "enter")
    ctx.pushed[-1]._edit.set_edit_text("X")
    ctx.pushed[-1].keypress("enter")
    reads_before = len([c for c in ctx.engine.calls if c == ("station", "show")])
    ctx.panes[0].on_exit(2)
    assert (
        ctx.popped >= 1
        and "exit 2" in screen.note
        and "its own words were in the pane" in screen.note
    )
    ctx.panes[0].on_exit(0)
    assert "Saved" in screen.note and "were read back" not in screen.note, (
        "not claimed before the read-back"
    )
    screen.on_show()
    assert "The values below were read back from the engine." in screen.note
    assert len([c for c in ctx.engine.calls if c == ("station", "show")]) > reads_before


def test_clearing_a_value_the_engine_can_clear() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    screen._walker.set_focus(screen._walker.index(row_for(screen, "mirror")))
    assert screen.keypress("c") is None
    assert ctx.panes == [], "c alone runs nothing"
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    assert "hammunition station set --clear-mirror" in render(confirm.widget(), 100, 10)
    assert confirm.keypress("b") == "b" and ctx.panes == []
    assert confirm.keypress("R") is None
    assert ctx.panes[0].argv == ["hammunition", "station", "set", "--clear-mirror"]


def test_c_on_a_field_with_no_clear_flag_does_nothing() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    screen._walker.set_focus(screen._walker.index(row_for(screen, "callsign")))
    assert screen.keypress("c") == "c" and ctx.panes == []


def test_the_book_chooser_toggles_and_applies_one_comma_list() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "reference_books").keypress((100,), "enter")
    chooser = ctx.pushed[-1]
    assert isinstance(chooser, ChooserScreen)
    books = load("books")["books"]
    out = render(chooser.widget(), 110, 30)
    assert books[0]["id"] in out and books[0]["licence"][:10] in out
    assert chooser.keypress("A") is None and ctx.panes == [], "nothing selected: nothing runs"
    chooser._walker[
        chooser._walker.index(
            next(r for r in chooser._walker if getattr(r, "value", None) == books[0]["id"])
        )
    ].keypress((100,), "enter")
    chooser._walker.set_focus(0)
    chosen = [b["id"] for b in books if b["chosen"]]
    assert chooser.keypress("A") is None
    expected = ",".join([*chosen, books[0]["id"]] if books[0]["id"] not in chosen else chosen)
    assert ctx.panes[0].argv == ["hammunition", "station", "set", f"--reference-books={expected}"]


def test_the_region_search_reads_maps_regions_and_applies_the_selection() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "map_regions").keypress((100,), "enter")
    prompt = ctx.pushed[-1]
    assert isinstance(prompt, PromptScreen)
    prompt._edit.set_edit_text("vermont")
    prompt.keypress("enter")
    chooser = ctx.pushed[-1]
    assert ("maps", "regions", "vermont") in ctx.engine.calls and isinstance(chooser, ChooserScreen)
    region = load("regions")["regions"][0]
    next(r for r in chooser._walker if getattr(r, "value", None) == region).keypress(
        (100,), "enter"
    )
    chooser.keypress("A")
    arg = ctx.panes[0].argv[-1]
    assert (
        arg.startswith("--map-regions=") and region in arg and "sentinelregion" in arg
    )  # replaces the whole list: the old one is kept


def test_a_region_search_term_that_looks_like_a_flag_is_refused_before_any_read() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "map_regions").keypress((100,), "enter")
    ctx.pushed[-1]._edit.set_edit_text("--help")
    ctx.pushed[-1].keypress("enter")
    assert not any(c[:2] == ("maps", "regions") for c in ctx.engine.calls)
    assert "does not start with '-'" in screen.note


def test_set_argv_is_one_element() -> None:
    from hammunition.console.screens.station import set_argv

    f = next(x for x in FIELDS if x.key == "callsign")
    assert set_argv(lambda *w: ["hammunition", *w], f, "N0TST") == [
        "hammunition",
        "station",
        "set",
        "--callsign=N0TST",
    ]


def test_a_failed_read_is_shown_not_retried() -> None:
    engine = FakeEngine()
    engine.set(("station", "show"), EngineRefused(2, "no station file"))
    ctx = FakeContext(engine=engine)
    _, out = shown(ctx)
    assert "no station file" in out and engine.calls.count(("station", "show")) == 1


def test_engine_text_in_a_value_is_cleaned() -> None:
    ctx = sentinel_ctx()
    body = {**load("station-set"), "mirror": "http://lan/\x1b[2J"}
    ctx.engine.set(("station", "show"), document("station", body))
    assert "\x1b" not in shown(ctx)[1]


def test_the_region_chooser_hides_carried_regions_until_revealed_and_the_title_has_no_term() -> (
    None
):
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "map_regions").keypress((100,), "enter")
    ctx.pushed[-1]._edit.set_edit_text("vermont")
    ctx.pushed[-1].keypress("enter")
    chooser = ctx.pushed[-1]
    assert chooser.title == "Regions matching your search"
    out = render(chooser.widget(), 100, 30)
    assert "sentinelregion" not in out and "1 carried, hidden" in out
    assert chooser.keypress("v") is None
    assert "sentinelregion" in render(chooser.widget(), 100, 30)
    chooser.on_hide()
    assert "sentinelregion" not in render(chooser.widget(), 100, 30)


def test_a_failed_read_back_is_said_and_a_missing_exit_code_is_not_printed_as_none() -> None:
    engine = FakeEngine()
    ctx = FakeContext(engine=engine)
    screen, _ = shown(ctx)
    screen._after_set(None)
    assert "None" not in screen.note and "no exit code recorded" in screen.note
    engine.set(("station", "show"), EngineRefused(2, "gone"))
    screen._after_set(0)
    screen.on_show()
    assert "reading the values back failed" in screen.note and "were read back" not in screen.note
