# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offering `repeaterbook-client` when the RepeaterBook fetch is chosen (issue #344): present,
absent and accepted, absent and declined, from both screens that can start the fetch."""

from collections.abc import Callable
from typing import Any

import pytest

from hammunition.console import repeaterbook
from hammunition.console.engine import EngineRefused
from hammunition.console.screens.base import ConfirmScreen, PromptScreen
from hammunition.console.screens.plan import PlanScreen
from hammunition.console.screens.repeaters import RepeatersScreen
from hammunition.console.screens.secrets import SecretsScreen

from .helpers import FakeContext, FakeEngine, document, load, render

FETCH = ["hammunition", "maps", "repeaters", "fetch-repeaterbook", "--state", "OH"]
INSTALL = ["hammunition", "install", "repeaterbook-client"]


def start_from_function(ctx: FakeContext) -> list[int | None]:
    codes: list[int | None] = []
    repeaterbook.run_fetch(ctx, FETCH[1:], codes.append)
    return codes


def start_from_secrets(ctx: FakeContext) -> list[int | None]:
    screen = SecretsScreen(ctx)
    screen.on_show()
    render(screen.widget(), 110, 30)  # drawing moves the focus onto the secret
    screen.keypress("f")
    prompt = ctx.pushed[-1]
    assert isinstance(prompt, PromptScreen)
    prompt._edit.set_edit_text("OH")
    prompt.keypress("enter")
    return []


def start_from_repeaters(ctx: FakeContext) -> list[int | None]:
    screen = RepeatersScreen(ctx)
    screen.on_show()
    screen.keypress("f")
    for answer in ("OH", ""):
        prompt = ctx.pushed[-1]
        assert isinstance(prompt, PromptScreen)
        prompt._edit.set_edit_text(answer)
        prompt.keypress("enter")
    return []


STARTS: list[Callable[[FakeContext], Any]] = [
    start_from_function,
    start_from_secrets,
    start_from_repeaters,
]
IDS = ["function", "secrets-screen", "repeaters-screen"]


def ctx_with(unit: str) -> FakeContext:
    return FakeContext(engine=FakeEngine(secrets="environment", rbclient=unit))


@pytest.mark.parametrize("start", STARTS, ids=IDS)
def test_unit_present_the_fetch_is_confirmed_and_runs_with_no_install(
    start: Callable[[FakeContext], Any],
) -> None:
    ctx = ctx_with("present")
    start(ctx)
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen) and not any(
        isinstance(s, PlanScreen) for s in ctx.pushed
    )
    assert ctx.panes == []
    confirm.keypress("R")
    assert [p.argv for p in ctx.panes] == [FETCH]
    assert ("update", "repeaterbook-client") in ctx.engine.calls


@pytest.mark.parametrize("start", STARTS, ids=IDS)
def test_unit_absent_and_accepted_installs_then_the_fetch_runs(
    start: Callable[[FakeContext], Any],
) -> None:
    ctx = ctx_with("absent")
    start(ctx)
    offer = ctx.pushed[-1]
    assert isinstance(offer, ConfirmScreen) and "Install repeaterbook-client first" in offer.title
    assert ctx.panes == []  # nothing runs on the offer
    offer.keypress("R")
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and plan.names == ["repeaterbook-client"] and plan.runnable
    assert ctx.panes == []  # the plan is a dry run
    plan.keypress("R")
    assert [p.argv for p in ctx.panes] == [INSTALL]
    ctx.panes[-1].on_exit(0)
    assert [p.argv for p in ctx.panes] == [INSTALL, FETCH]
    assert ctx.popped >= 2  # the install pane and its plan were left behind


@pytest.mark.parametrize("start", STARTS, ids=IDS)
def test_unit_absent_and_declined_runs_nothing(start: Callable[[FakeContext], Any]) -> None:
    ctx = ctx_with("absent")
    start(ctx)
    assert isinstance(ctx.pushed[-1], ConfirmScreen)
    # Back (b) on the offer pops it: no R was pressed, so no plan, no install, no fetch.
    assert ctx.panes == [] and not any(isinstance(s, PlanScreen) for s in ctx.pushed)


@pytest.mark.parametrize("start", STARTS, ids=IDS)
def test_unit_absent_declined_at_the_plan_runs_nothing(start: Callable[[FakeContext], Any]) -> None:
    ctx = ctx_with("absent")
    start(ctx)
    ctx.pushed[-1].keypress("R")
    assert isinstance(ctx.pushed[-1], PlanScreen)
    assert ctx.panes == []  # backing out of the plan runs nothing


@pytest.mark.parametrize("code", [1, 3, None])
def test_a_failed_or_cut_off_install_never_runs_the_fetch(code: int | None) -> None:
    ctx = ctx_with("absent")
    start_from_function(ctx)
    ctx.pushed[-1].keypress("R")
    ctx.pushed[-1].keypress("R")
    ctx.panes[-1].on_exit(code)
    assert [p.argv for p in ctx.panes] == [INSTALL]
    assert ctx.replaced and type(ctx.replaced[-1]).__name__ == "ResultScreen"


def test_the_fetch_exit_code_reaches_the_caller_after_an_install() -> None:
    ctx = ctx_with("absent")
    codes = start_from_function(ctx)
    ctx.pushed[-1].keypress("R")
    ctx.pushed[-1].keypress("R")
    ctx.panes[-1].on_exit(0)
    ctx.panes[-1].on_exit(0)
    assert codes == [0]


def test_a_failed_check_does_not_block_the_fetch_and_says_it_could_not_check() -> None:
    ctx = ctx_with("present")
    ctx.engine.set(("update", "repeaterbook-client"), EngineRefused(2, "lists unreadable"))
    start_from_function(ctx)
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    assert "could not tell whether" in render(confirm.widget(), 120, 20)


def test_a_document_with_no_row_for_the_unit_is_unknown_not_absent() -> None:
    doc = document("update", {"rows": []})
    assert repeaterbook.unit_installed(doc) is None
    assert repeaterbook.unit_installed(document("update", {})) is None


def test_the_installed_state_reads_the_engines_state_word() -> None:
    present = load("update-repeaterbook-client-present")
    absent = load("update-repeaterbook-client-absent")
    assert repeaterbook.unit_installed(document("update", {"rows": present["rows"]})) is True
    assert repeaterbook.unit_installed(document("update", {"rows": absent["rows"]})) is False
    assert absent["rows"][0]["state"] == "not installed"
