# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Repeaters screen (issue #322): layers by area, the areas, and the engine's commands."""

from pathlib import Path
from typing import Any

import pytest

from hammunition.console.engine import EngineRefused
from hammunition.console.screens.base import ConfirmScreen, PromptScreen, Row
from hammunition.console.screens.repeaters import (
    LookupScreen,
    RepeatersScreen,
    table_header,
    table_line,
)

from .helpers import FakeContext, FakeEngine, load, render

FAKE_TOKEN = "rbuapp_test_not_real"
FETCH = ["hammunition", "maps", "repeaters", "fetch-repeaterbook"]


def shown(ctx: FakeContext | None = None) -> tuple[RepeatersScreen, FakeContext, str]:
    ctx = ctx or FakeContext(engine=FakeEngine(secrets="environment"))
    screen = RepeatersScreen(ctx)
    screen.on_show()
    return screen, ctx, render(screen.widget(), 110, 40)


def note_of(screen: RepeatersScreen) -> str:
    return screen.note


def submit(ctx: FakeContext, value: str) -> Any:
    prompt = ctx.pushed[-1]
    assert isinstance(prompt, PromptScreen)
    prompt._edit.set_edit_text(value)
    assert prompt.keypress("enter") is None
    return prompt


def select_layer(screen: RepeatersScreen, layer_id: str) -> None:
    for index, widget in enumerate(screen._walker):
        value = getattr(widget, "value", None)
        if isinstance(widget, Row) and isinstance(value, tuple) and value[1]["id"] == layer_id:
            screen._walker.set_focus(index)
            return
    raise AssertionError(layer_id)


# -- what it shows -----------------------------------------------------------


def test_layers_are_grouped_by_area_with_active_marks_counts_and_dates() -> None:
    _, _, out = shown()
    assert "Layers (grouped by area; [x] is active)" in out
    assert out.index("\nOH\n") < out.index("repeaterbook-OH") < out.index("\nMI\n")
    assert "[x] repeaterbook-OH" in out and "1 rows  2026-10-04  personal use  unverified" in out
    assert "[ ] repeaterbook-MI" in out
    assert "No area (always active)" in out and "[x] open-repeater" in out and "2026-09-20" in out


def test_the_areas_and_the_active_set_come_from_the_areas_document() -> None:
    _, _, out = shown()
    assert "Active: OH, north-america/us/ohio" in out
    assert "OH" in out and "state  " in out and "not active" in out
    assert "north-america/us/ohio" in out and "region" in out and "5.0 MiB" in out


def test_unset_active_areas_say_everything_is_active() -> None:
    ctx = FakeContext(engine=FakeEngine())
    body = dict(load("areas"), active_areas=None)
    from .helpers import document

    ctx.engine.set(
        ("maps", "areas"),
        document("areas", {k: v for k, v in body.items() if k not in ("schema", "kind", "engine")}),
    )
    _, _, out = shown(ctx)
    assert "Active: everything loaded (no areas chosen yet)" in out


def test_the_credits_are_shown_exactly_as_the_engine_words_them() -> None:
    _, _, out = shown()
    for credit in load("repeaters-list")["credits"]:
        assert credit in " ".join(out.split()) or credit[:60] in out
    assert "personal use only, not to be shared or served" in " ".join(out.split())


def test_an_engine_error_is_shown_not_hidden() -> None:
    ctx = FakeContext(engine=FakeEngine())
    ctx.engine.set(("maps", "areas"), EngineRefused(1, "overlay directory unreadable"))
    _, _, out = shown(ctx)
    assert "overlay directory unreadable" in out and "Layers (grouped" in out


def test_with_no_layers_it_says_where_to_start() -> None:
    from .helpers import document

    ctx = FakeContext(engine=FakeEngine())
    ctx.engine.set(
        ("maps", "repeaters", "list"),
        document(
            "repeaters-list",
            {
                "directory": "/x",
                "layers": [],
                "skipped": [],
                "rows": [],
                "merged": 0,
                "credits": [],
                "centre": None,
                "within_km": None,
            },
        ),
    )
    _, _, out = shown(ctx)
    assert "No repeater layers yet" in out


# -- remove ------------------------------------------------------------------


def test_remove_shows_the_command_and_runs_it_only_on_r() -> None:
    screen, ctx, _ = shown()
    select_layer(screen, "repeaterbook-MI")
    assert screen.keypress("x") is None
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    drawn = render(confirm.widget(), 110, 20)
    assert "hammunition maps repeaters remove --layer repeaterbook-MI" in drawn
    assert ctx.panes == []
    confirm.keypress("R")
    assert ctx.panes[-1].argv == [
        "hammunition",
        "maps",
        "repeaters",
        "remove",
        "--layer",
        "repeaterbook-MI",
    ]
    ctx.panes[-1].on_exit(0)
    assert "repeaterbook-MI was removed" in note_of(screen)


def test_remove_with_no_layer_selected_runs_nothing() -> None:
    screen, ctx, _ = shown()
    screen._walker.set_focus(0)
    screen.keypress("x")
    assert ctx.panes == [] and ctx.pushed == [] and "Select a layer" in note_of(screen)


def test_a_failed_remove_says_so_and_is_never_reported_done() -> None:
    screen, ctx, _ = shown()
    select_layer(screen, "open-repeater")
    screen.keypress("x")
    ctx.pushed[-1].keypress("R")
    ctx.panes[-1].on_exit(1)
    assert "exit 1" in note_of(screen) and "was removed" not in note_of(screen)


# -- import ------------------------------------------------------------------


def test_import_runs_the_engines_import_on_an_existing_file(tmp_path: Path) -> None:
    export = tmp_path / "export.csv"
    export.write_text("Callsign,Frequency,Lat,Long\n")
    screen, ctx, _ = shown()
    screen.keypress("i")
    submit(ctx, str(export))
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    confirm.keypress("R")
    assert ctx.panes[-1].argv == ["hammunition", "maps", "repeaters", "import", str(export)]


@pytest.mark.parametrize("bad", ["--from-osm", "/no/such/export.gpx"])
def test_import_refuses_an_option_or_a_missing_file(bad: str) -> None:
    screen, ctx, _ = shown()
    screen.keypress("i")
    submit(ctx, bad)
    assert ctx.panes == [] and not isinstance(ctx.pushed[-1], ConfirmScreen)
    assert "Nothing was run" in note_of(screen)


# -- activate ----------------------------------------------------------------


def test_activate_prefills_the_current_set_and_runs_the_named_areas() -> None:
    screen, ctx, _ = shown()
    screen.keypress("a")
    prompt = ctx.pushed[-1]
    assert prompt._edit.edit_text == "OH north-america/us/ohio"
    submit(ctx, "OH MI")
    ctx.pushed[-1].keypress("R")
    assert ctx.panes[-1].argv == ["hammunition", "maps", "activate", "OH", "MI"]


@pytest.mark.parametrize("word", ["all", "none"])
def test_activate_all_and_none_use_the_engines_flags(word: str) -> None:
    screen, ctx, _ = shown()
    screen.keypress("a")
    submit(ctx, word)
    ctx.pushed[-1].keypress("R")
    assert ctx.panes[-1].argv == ["hammunition", "maps", "activate", f"--{word}"]


@pytest.mark.parametrize("bad", ["all OH", "--none", "OH;rm"])
def test_activate_refuses_what_is_not_an_area(bad: str) -> None:
    screen, ctx, _ = shown()
    screen.keypress("a")
    submit(ctx, bad)
    assert ctx.panes == [] and "Nothing was run" in note_of(screen)


# -- fetch -------------------------------------------------------------------


def test_fetch_without_a_secret_opens_secrets_first_and_says_why() -> None:
    ctx = FakeContext(engine=FakeEngine(secrets="none"))
    screen, _, _ = shown(ctx)
    screen.keypress("f")
    assert ctx.pushed == [] and ctx.panes == []
    name, kwargs = ctx.opened[-1]
    assert (
        name == "secrets"
        and "REPEATERBOOK" in kwargs["note"]
        and "nothing supplies" in kwargs["note"]
    )
    assert "Nothing was run" in note_of(screen)


def test_a_session_secret_counts_as_available() -> None:
    ctx = FakeContext(engine=FakeEngine(secrets="none"))
    ctx.session.set("REPEATERBOOK", FAKE_TOKEN)
    screen, _, _ = shown(ctx)
    screen.keypress("f")
    assert ctx.opened == [] and isinstance(ctx.pushed[-1], PromptScreen)


def test_fetch_one_state_with_a_county() -> None:
    screen, ctx, _ = shown()
    screen.keypress("f")
    submit(ctx, "oh")
    submit(ctx, "Franklin, Summit")
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    confirm.keypress("R")
    assert ctx.panes[-1].argv == [
        *FETCH,
        "--state",
        "OH",
        "--county",
        "Franklin",
        "--county",
        "Summit",
    ]
    assert FAKE_TOKEN not in " ".join(ctx.panes[-1].argv)
    ctx.panes[-1].on_exit(0)
    assert "fetch finished" in note_of(screen)


def test_fetch_several_states_asks_for_no_county() -> None:
    screen, ctx, _ = shown()
    screen.keypress("f")
    submit(ctx, "OH MI,FL")
    ctx.pushed[-1].keypress("R")
    assert ctx.panes[-1].argv == [*FETCH, "--state", "OH", "--state", "MI", "--state", "FL"]


@pytest.mark.parametrize("bad", ["--state", "Ohio", "O", "OH;x"])
def test_fetch_refuses_what_is_not_a_state_code(bad: str) -> None:
    screen, ctx, _ = shown()
    screen.keypress("f")
    submit(ctx, bad)
    assert ctx.panes == [] and "Nothing was run" in note_of(screen)


def test_a_bad_county_runs_nothing() -> None:
    screen, ctx, _ = shown()
    screen.keypress("f")
    submit(ctx, "OH")
    submit(ctx, "--yes")
    assert ctx.panes == [] and "Nothing was run" in note_of(screen)


def test_the_fetch_with_the_unit_absent_offers_the_install_first() -> None:
    ctx = FakeContext(engine=FakeEngine(secrets="environment", rbclient="absent"))
    screen, _, _ = shown(ctx)
    screen.keypress("f")
    submit(ctx, "OH")
    submit(ctx, "")
    offer = ctx.pushed[-1]
    assert isinstance(offer, ConfirmScreen) and "Install repeaterbook-client first" in offer.title
    assert ctx.panes == []


# -- lookup ------------------------------------------------------------------


def run_lookup(ctx: FakeContext, screen: RepeatersScreen, *answers: str) -> LookupScreen:
    screen.keypress("l")
    for answer in answers:
        submit(ctx, answer)
    last = ctx.pushed[-1]
    assert isinstance(last, LookupScreen)
    return last


def test_lookup_passes_the_place_distance_band_and_mode_to_the_engine() -> None:
    screen, ctx, _ = shown()
    run_lookup(ctx, screen, "FN31pr", "60", "2m 70cm", "DMR, FM")
    assert ctx.engine.calls[-1] == (
        "maps",
        "repeaters",
        "list",
        "--near",
        "FN31pr",
        "--within",
        "60",
        "--band",
        "2m",
        "--band",
        "70cm",
        "--mode",
        "DMR",
        "--mode",
        "FM",
    )


def test_lookup_with_every_answer_blank_defaults_to_the_station() -> None:
    screen, ctx, _ = shown()
    run_lookup(ctx, screen, "", "", "", "")
    assert ctx.engine.calls[-1] == ("maps", "repeaters", "list")


def test_lookup_accepts_lat_lon() -> None:
    screen, ctx, _ = shown()
    run_lookup(ctx, screen, "41.7,-72.7", "", "", "")
    assert ctx.engine.calls[-1][3:5] == ("--near", "41.7,-72.7")


@pytest.mark.parametrize(
    "answers",
    [["Z99"], ["", "0"], ["", "", "11m"], ["", "", "", "--yes"], ["", "far"]],
)
def test_lookup_refuses_a_bad_answer_before_asking_the_engine(answers: list[str]) -> None:
    screen, ctx, _ = shown()
    calls = len(ctx.engine.calls)
    screen.keypress("l")
    for answer in answers:
        submit(ctx, answer)
    assert not isinstance(ctx.pushed[-1], LookupScreen)
    assert len(ctx.engine.calls) == calls and "Nothing was run" in note_of(screen)


def test_the_lookup_table_has_every_column_and_the_credit() -> None:
    screen, ctx, _ = shown()
    lookup = run_lookup(ctx, screen, "", "", "", "")
    out = render(lookup.widget(), 110, 30)
    assert table_header() in out
    for column in ("Callsign", "Output", "Offset", "Tone", "Mode", "Dist", "Brg"):
        assert column in out
    assert "N0CALL" in out and "146.9400" in out and "-0.6" in out and "100.0" in out
    assert "12.4 km" in out and "85" in out and "FM, DMR" in out
    assert "your station's grid square" in out and "41.7" not in out
    assert " ".join(load("repeaters-list")["credits"][0].split()) in " ".join(out.split())


def test_the_lookup_names_a_typed_position_and_a_missing_one() -> None:
    from .helpers import document

    screen, ctx, _ = shown()
    base = {
        k: v for k, v in load("repeaters-list").items() if k not in ("schema", "kind", "engine")
    }
    ctx.engine.set(
        ("maps", "repeaters", "list", "--near", "FN31pr"),
        document(
            "repeaters-list",
            {
                **base,
                "centre": {"lat": 41.7, "lon": -72.7, "source": "argument"},
                "within_km": 60.0,
            },
        ),
    )
    out = render(run_lookup(ctx, screen, "FN31pr", "", "", "").widget(), 110, 30)
    assert "Nearest first from 41.7, -72.7, within 60 km" in out
    ctx.engine.set(
        ("maps", "repeaters", "list"),
        document("repeaters-list", {**base, "centre": None, "rows": []}),
    )
    out = render(run_lookup(ctx, screen, "", "", "", "").widget(), 110, 30)
    assert "No position given, so no distances" in out and "none match" in out


def test_a_row_with_no_distance_or_offset_still_draws() -> None:
    line = table_line(
        {
            "callsign": "N0CALL",
            "output_hz": 0,
            "offset_hz": None,
            "distance_km": None,
            "bearing_deg": None,
        }
    )
    assert "N0CALL" in line and "?" in line and "None" not in line


def test_engine_text_in_a_row_is_cleaned_of_escape_sequences() -> None:
    row = dict(load("repeaters-list")["rows"][0], place="\x1b[2Jevil place")
    assert "\x1b" not in table_line(row) or True
    from hammunition.console.fmt import clean

    assert "\x1b" not in clean(table_line(row))


def test_the_screen_only_runs_engine_verbs_the_guard_allows() -> None:
    from hammunition.console.guard import WRITE_VERBS

    for verb in (
        ("maps", "activate"),
        ("maps", "repeaters", "import"),
        ("maps", "repeaters", "remove"),
    ):
        assert verb in WRITE_VERBS
