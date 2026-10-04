# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Any

import pytest

from hammunition.console.engine import EngineRefused
from hammunition.console.screens.base import ConfirmScreen
from hammunition.console.screens.plan import PlanScreen
from hammunition.console.screens.update import UpdateScreen, counts_text, rebuild_names

from .helpers import FakeContext, FakeEngine, document, load, render


def shown(ctx: FakeContext | None = None, **kw: Any) -> tuple[UpdateScreen, FakeContext, str]:
    ctx = ctx or FakeContext()
    screen = UpdateScreen(ctx, **kw)
    screen.on_show()
    return screen, ctx, render(screen.widget(), 110, 30)


def test_the_report_lists_each_unit_with_its_state_and_the_lists_age() -> None:
    _, _, out = shown()
    doc = load("update-all")
    for row in doc["rows"]:
        assert row["unit"] in out and row["state"] in out
    assert doc["lists_note"] in out
    assert counts_text(doc["counts"]) in out and "None" not in out


def test_an_unknown_state_word_is_shown_verbatim() -> None:
    engine = FakeEngine()
    doc = load("update-all")
    doc["rows"][0]["state"] = "quarantined"
    engine.set(("update",), document("update", doc))
    assert "quarantined" in shown(FakeContext(engine=engine))[2]


def test_counts_text_tolerates_missing_keys() -> None:
    assert counts_text({}) == "counts unknown"
    assert "1 up to date" in counts_text({"up_to_date": 1})


def test_capital_a_confirms_then_runs_apt_in_a_pane_without_the_assume_yes() -> None:
    screen, ctx, _ = shown()
    assert screen.keypress("A") is None
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    assert "sudo apt-get install --only-upgrade --no-remove -- fixture-apt" in render(
        confirm.widget(), 110, 10
    )
    assert ctx.panes == [], "nothing runs until the person presses R on the confirm screen"
    confirm.keypress("R")
    assert ctx.panes[0].argv == [
        "sudo",
        "apt-get",
        "install",
        "--only-upgrade",
        "--no-remove",
        "--",
        "fixture-apt",
    ]


def test_a_missing_or_unexpected_apt_command_is_shown_as_text_and_never_run() -> None:
    engine = FakeEngine()
    doc = load("update-all")
    doc["upgrade_command"] = None
    engine.set(("update",), document("update", doc))
    screen, ctx, _ = shown(FakeContext(engine=engine))
    screen.keypress("A")
    assert ctx.pushed == [] and "No apt upgrade is offered" in screen.note
    doc["upgrade_command"] = "sudo rm -rf / --yes"
    engine.set(("update",), document("update", doc))
    screen.on_show()
    screen.keypress("A")
    assert (
        ctx.pushed == []
        and ctx.panes == []
        and "run it yourself" in screen.note
        and "sudo rm -rf" in screen.note
    )


def test_capital_b_goes_through_the_plan_for_the_units_behind_the_pin() -> None:
    screen, ctx, _ = shown()
    assert screen.keypress("B") is None
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and (plan.action, plan.names) == ("install", ["acarsdec"])
    assert ctx.panes == []


@pytest.mark.parametrize(
    "command,expected",
    [
        ("hammunition install a b", ["a", "b"]),
        ("hammunition install osm-regions osm-navit", ["osm-regions", "osm-navit"]),
        (None, None),
        ("", None),
        ("hammunition install", None),
        ("hammunition install a; rm x", None),
        ("hammunition install $(id)", None),
        ("sudo hammunition install a", None),
        ("hammunition uninstall a", None),
        ("hammunition install -y a", None),
        ("hammunition install 'a b'", None),
        ("hammunition install a 'b", None),
    ],
)
def test_rebuild_names_accepts_only_the_exact_shape(
    command: str | None, expected: list[str] | None
) -> None:
    assert rebuild_names(command) == expected


def test_an_unexpected_rebuild_command_is_not_planned() -> None:
    engine = FakeEngine()
    doc = load("update-all")
    doc["rebuild_command"] = "hammunition install a; echo pwned"
    engine.set(("update",), document("update", doc))
    screen, ctx, _ = shown(FakeContext(engine=engine))
    screen.keypress("B")
    assert ctx.pushed == [] and "run it yourself" in screen.note


def test_lowercase_u_adds_upstream_and_asks_again() -> None:
    screen, ctx, _ = shown()
    assert screen.keypress("u") is None and screen.upstream is True
    assert ctx.engine.calls[-1] == ("update", "--upstream")
    assert "asks GitHub" in render(screen.widget(), 110, 30)
    screen.keypress("u")
    assert ctx.engine.calls[-1] == ("update",)


def test_upstream_rows_are_shown_when_the_report_has_them() -> None:
    engine = FakeEngine()
    doc = load("update-all")
    doc["upstream"] = [
        {
            "unit": "linbpq",
            "method": "git_tags",
            "catalog": "25.39",
            "upstream": None,
            "state": "unanswered",
            "detail": None,
        }
    ]
    engine.set(("update", "--upstream"), document("update", doc))
    screen, _, _ = shown(FakeContext(engine=engine))
    screen.keypress("u")
    out = render(screen.widget(), 110, 30)
    assert "linbpq" in out and "unanswered" in out and "None" not in out


def test_without_e2_the_engines_refusal_is_shown_and_a_per_profile_list_is_offered() -> None:
    screen, ctx, out = shown(FakeContext(engine=FakeEngine(suffix="-without")))
    assert "retired" in out and "the engine refused (exit 2)" in out and "Update by profile" in out
    profile = load("list-all-without")["profiles"][0]["name"]
    assert profile in out
    next(r for r in screen._walker if getattr(r, "value", None) == profile).keypress(
        (100,), "enter"
    )
    nested = ctx.pushed[-1]
    assert isinstance(nested, UpdateScreen) and nested.names == [profile]
    assert ctx.engine.calls[-1] == ("update", profile)


def test_a_profile_report_reads_update_with_the_names() -> None:
    _, ctx, out = shown(names=["station"])
    assert ctx.engine.calls[0] == ("update", "station")
    assert load("update-profile")["rows"][0]["unit"] in out


def test_engine_text_is_cleaned() -> None:
    engine = FakeEngine()
    engine.set(("update",), EngineRefused(2, "\x1b[2Jbroken"))
    assert "\x1b" not in shown(FakeContext(engine=engine))[2]
