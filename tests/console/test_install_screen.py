# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Any

import pytest

from hammunition.console.engine import EngineRefused
from hammunition.console.screens.install import (
    InstallScreen,
    profile_state,
    profile_text,
    unit_text,
)
from hammunition.console.screens.plan import PlanScreen

from .helpers import FakeContext, FakeEngine, document, load, render


def shown(ctx: FakeContext | None = None, **kw: object) -> tuple[InstallScreen, FakeContext, str]:
    ctx = ctx or FakeContext()
    screen = InstallScreen(ctx, **kw)  # type: ignore[arg-type]
    screen.on_show()
    return screen, ctx, render(screen.widget(), 110, 30)


def test_profile_rows_carry_name_stage_state_gate_and_summary_with_e1() -> None:
    _, _, out = shown()
    first = load("list-all")["profiles"][0]
    assert first["name"] in out and f"{first['installed']} of {first['members']} installed" in out
    assert first["summary"][:30] in out
    gated = next(p for p in load("list-all")["profiles"] if p["consent_gated"])
    line = next(ln for ln in out.splitlines() if ln.startswith(gated["name"]))
    assert " G " in line


def test_without_e1_the_state_is_unknown_and_nothing_crashes() -> None:
    _, _, out = shown(FakeContext(engine=FakeEngine(suffix="-without")))
    first = load("list-all-without")["profiles"][0]
    assert f"{len(first['packages'])} units, state unknown" in out and "None" not in out


@pytest.mark.parametrize(
    "entry,expected",
    [
        (
            {
                "packages": ["a", "b"],
                "members": 2,
                "installed": 1,
                "installed_size_bytes": 5 * 1024**2,
            },
            "1 of 2 installed, 5.0 MiB",
        ),
        (
            {"packages": ["a"], "members": 1, "installed": 0, "installed_size_bytes": None},
            "0 of 1 installed",
        ),
        ({"packages": ["a", "b", "c"]}, "3 units, state unknown"),
        ({"packages": None}, "0 units, state unknown"),
        ({"members": "2", "installed": None, "packages": ["a"]}, "1 units, state unknown"),
    ],
)
def test_profile_state_degrades_to_unknown(entry: dict[str, Any], expected: str) -> None:
    assert profile_state(entry) == expected


def test_null_summary_and_missing_fields_render_blank_not_none() -> None:
    entry: dict[str, Any] = {
        "name": "p",
        "stage": None,
        "summary": None,
        "packages": [],
        "consent_gated": None,
        "documentation": None,
    }
    assert "None" not in profile_text(entry) and profile_text(entry).startswith("p")
    assert "None" not in unit_text(
        {"name": "u", "status": None, "summary": None, "resolves_here": None}
    )
    assert "not here" in unit_text(
        {"name": "u", "status": "supported", "summary": "s", "resolves_here": None}
    )


def test_control_characters_in_a_summary_are_removed() -> None:
    engine = FakeEngine()
    cat = load("list-all")
    cat["profiles"][0]["summary"] = "evil\x1b[2Jsummary"
    engine.set(("list",), document("catalog", cat))
    _, _, out = shown(FakeContext(engine=engine))
    assert "\x1b" not in out and "evilsummary" in out.replace("[2J", "")


def test_a_failed_list_is_shown() -> None:
    engine = FakeEngine()
    engine.set(("list",), EngineRefused(2, "no catalog here"))
    assert "no catalog here" in shown(FakeContext(engine=engine))[2]


def test_tab_switches_between_profiles_and_units() -> None:
    screen, _, out = shown()
    assert "Profiles" in out and "Units" not in out.replace("units", "")
    assert screen.keypress("tab") is None and screen.mode == "units"
    out = render(screen.widget(), 110, 30)
    unit = load("list-all")["packages"][0]
    assert unit["name"] in out
    assert screen.keypress("tab") is None and screen.mode == "profiles"


def first_row(screen: InstallScreen, kind: str) -> object:
    return next(r for r in screen._walker if getattr(r, "value", None) and r.value[0] == kind)  # type: ignore[attr-defined]


def test_enter_on_a_profile_opens_its_plan_and_capital_u_plans_the_uninstall() -> None:
    screen, ctx, _ = shown()
    name = load("list-all")["profiles"][0]["name"]
    row = first_row(screen, "profile")
    row.keypress((100,), "enter")  # type: ignore[attr-defined]
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and (plan.action, plan.names) == ("install", [name])
    screen._walker.set_focus(screen._walker.index(row))  # type: ignore[attr-defined]
    assert screen.keypress("U") is None
    uninstall = ctx.pushed[-1]
    assert isinstance(uninstall, PlanScreen) and (uninstall.action, uninstall.names) == (
        "uninstall",
        [name],
    )


def test_enter_on_a_unit_plans_just_that_unit() -> None:
    screen, ctx, _ = shown()
    screen.keypress("tab")
    unit = load("list-all")["packages"][0]["name"]
    first_row(screen, "unit").keypress((100,), "enter")  # type: ignore[attr-defined]
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and plan.names == [unit]


def type_name(screen: InstallScreen, value: str) -> None:
    screen._name_edit.set_edit_text(value)
    screen._walker.set_focus(screen._walker.index(screen._name_edit))
    screen.keypress("enter")


def test_a_typed_name_goes_to_the_plan_as_separate_argv_elements() -> None:
    screen, ctx, _ = shown()
    type_name(screen, "station  hamlib")
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and plan.names == ["station", "hamlib"]


@pytest.mark.parametrize("typed", ["-y", "--yes", "station -y", "--dry-run", "-", "a --yes b"])
def test_a_typed_name_that_begins_with_a_dash_runs_nothing(typed: str) -> None:
    screen, ctx, _ = shown()
    type_name(screen, typed)
    assert ctx.pushed == [] and ctx.panes == []
    assert "does not start with '-'" in render(
        screen.widget(), 110, 30
    ) and "Nothing was run" in render(screen.widget(), 110, 30)


def test_an_empty_name_does_nothing() -> None:
    screen, ctx, _ = shown()
    type_name(screen, "   ")
    assert ctx.pushed == []


def test_highlight_puts_focus_on_that_profile_and_the_detail_shows_its_docs() -> None:
    profile = load("list-all")["profiles"][1]
    screen, _, out = shown(highlight=profile["name"])
    focused = screen._walker.get_focus()[0]
    assert focused.value[1]["name"] == profile["name"]  # type: ignore[union-attr]
    docs = profile["documentation"]
    if docs.get("why_together"):
        assert docs["why_together"][:30] in out
    if docs.get("manual_configuration"):
        assert docs["manual_configuration"][:30] in out


def test_the_detail_panel_tolerates_null_documentation_fields() -> None:
    engine = FakeEngine()
    cat = load("list-all")
    cat["profiles"][0]["documentation"] = {
        "what_it_installs": None,
        "why_together": None,
        "deliberately_excludes": None,
        "manual_configuration": None,
        "disk_footprint_hint": None,
    }
    engine.set(("list",), document("catalog", cat))
    assert "None" not in shown(FakeContext(engine=engine))[2]


def test_the_gate_marker_is_explained() -> None:
    assert "G = asks you to type yes" in shown()[2]
