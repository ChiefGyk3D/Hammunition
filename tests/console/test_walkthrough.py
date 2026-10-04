# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Any

from hammunition.console.config import Config
from hammunition.console.screens.base import ConfirmScreen
from hammunition.console.screens.home import HomeScreen
from hammunition.console.screens.plan import PlanScreen
from hammunition.console.walkthrough import STARTER, show_checklist, steps

from .helpers import FakeContext, FakeEngine, document, load, render

SET = {"callsign": "N0CALL", "grid_square": "FN31pr"}
NONE: dict[str, Any] = {"callsign": None, "grid_square": None}


def catalog(installed: Any, members: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": STARTER, "packages": ["a", "b"]}
    if installed is not None:
        entry.update(installed=installed, members=members)
    return {"profiles": [entry]}


def state(items: list[Any], key: str) -> str:
    return str(next(s.state for s in items if s.key == key))


def test_station_is_done_only_when_both_values_are_present() -> None:
    assert state(steps(SET, catalog(0, 2), set()), "station") == "done"
    assert state(steps(NONE, catalog(0, 2), set()), "station") == "todo"
    assert (
        state(steps({"callsign": "N0CALL", "grid_square": None}, catalog(0, 2), set()), "station")
        == "todo"
    )
    assert state(steps(None, None, set()), "station") == "unknown"


def test_hardware_is_never_done() -> None:
    for station in (SET, NONE, None):
        assert state(steps(station, catalog(2, 2), set()), "hardware") == "unknown"
    assert state(steps(SET, catalog(2, 2), {"hardware"}), "hardware") == "skipped"


def test_pick_and_install_follow_the_starter_profiles_installed_state() -> None:
    nothing = steps(SET, catalog(0, 2), set())
    assert (state(nothing, "pick"), state(nothing, "install")) == ("todo", "todo")
    part = steps(SET, catalog(1, 2), set())
    assert (state(part, "pick"), state(part, "install")) == ("done", "todo")
    whole = steps(SET, catalog(2, 2), set())
    assert (state(whole, "pick"), state(whole, "install")) == ("done", "done")


def test_without_e1_those_two_are_unknown_never_done() -> None:
    items = steps(SET, catalog(None, None), set())
    assert (state(items, "pick"), state(items, "install")) == ("unknown", "unknown")
    assert state(steps(SET, None, set()), "pick") == "unknown"
    assert state(steps(SET, {"profiles": []}, set()), "install") == "unknown"
    assert state(steps(SET, catalog("x", None), set()), "install") == "unknown"


def test_skipping_never_hides_a_done_step_and_the_checklist_shows_until_all_are_settled() -> None:
    items = steps(SET, catalog(2, 2), {"station", "pick", "hardware"})
    assert (
        state(items, "station") == "done"
        and state(items, "pick") == "done"
        and state(items, "hardware") == "skipped"
    )
    assert show_checklist(items) is False
    assert show_checklist(steps(SET, catalog(2, 2), set())) is True, (
        "hardware stays unknown, so the list stays"
    )


def home(ctx: FakeContext | None = None) -> tuple[HomeScreen, FakeContext]:
    ctx = ctx or FakeContext()
    screen = HomeScreen(ctx)
    screen.on_show()
    return screen, ctx


def step_row(screen: HomeScreen, key: str) -> Any:
    return next(r for r in screen._walker if getattr(getattr(r, "value", None), "key", None) == key)


def test_home_shows_the_checklist_and_never_a_station_value() -> None:
    screen, _ = home()
    out = render(screen.widget(), 110, 40)
    assert "First run" in out and "Set your station" in out and "hardware" in out.lower()
    assert "N0CALL" not in out and "FN31pr" not in out
    assert "[?]" in out, "the hardware step is shown as unknown"


class NeverBackground:
    """A background that never finishes: the documents have not arrived yet."""

    def submit(self, call: Any, done: Any) -> None:
        return None


def test_the_checklist_waits_for_the_documents_instead_of_flickering() -> None:
    ctx = FakeContext()
    ctx.bg = NeverBackground()  # type: ignore[assignment]
    screen = HomeScreen(ctx)
    screen.on_show()
    assert "First run" not in render(screen.widget(), 110, 40)


def test_dismiss_saves_only_the_flag_and_hides_the_list() -> None:
    screen, ctx = home()
    assert screen.keypress("D") is None
    assert ctx.config.walkthrough_dismissed is True and ctx.saved == 1
    assert "First run" not in render(screen.widget(), 110, 40)
    assert ctx.config == Config(walkthrough_dismissed=True)


def test_a_dismissed_checklist_stays_hidden() -> None:
    ctx = FakeContext(config=Config(walkthrough_dismissed=True))
    screen, _ = home(ctx)
    assert "First run" not in render(screen.widget(), 110, 40)


def test_skip_marks_the_focused_step_for_this_session_only() -> None:
    screen, ctx = home()
    screen._walker.set_focus(screen._walker.index(step_row(screen, "hardware")))
    assert screen.keypress("s") is None
    assert "[-]" in render(screen.widget(), 110, 40) and ctx.saved == 0


def test_the_station_step_opens_the_station_screen() -> None:
    screen, ctx = home()
    step_row(screen, "station").keypress((100,), "enter")
    assert ctx.opened[-1] == ("station", {})


def test_the_pick_step_opens_install_with_the_starter_highlighted() -> None:
    screen, ctx = home()
    step_row(screen, "pick").keypress((100,), "enter")
    assert ctx.opened[-1] == ("install", {"highlight": STARTER})


def test_the_install_step_goes_through_the_plan() -> None:
    screen, ctx = home()
    step_row(screen, "install").keypress((100,), "enter")
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and (plan.action, plan.names) == ("install", [STARTER])
    assert ctx.panes == []


def test_the_hardware_step_names_the_command_and_runs_it_only_on_capital_r() -> None:
    screen, ctx = home()
    step_row(screen, "hardware").keypress((100,), "enter")
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    out = render(confirm.widget(), 100, 12)
    assert "hammunition hardware apply" in out and "its own plan" in out and "confirmation" in out
    assert ctx.panes == []
    confirm.keypress("R")
    assert ctx.panes[0].argv == ["hammunition", "hardware", "apply"]


def test_a_failed_step_leaves_the_list_and_says_why() -> None:
    screen, ctx = home()
    step_row(screen, "hardware").keypress((100,), "enter")
    ctx.pushed[-1].keypress("R")
    ctx.panes[0].on_exit(1)
    assert "hardware apply exited 1" in screen.note and "First run" in render(
        screen.widget(), 110, 40
    )


def test_a_finished_install_hides_the_install_steps() -> None:
    engine = FakeEngine()
    cat = load("list-all")
    for profile in cat["profiles"]:
        if profile["name"] == STARTER:
            profile["members"], profile["installed"] = 3, 3
    engine.set(("list",), document("catalog", cat))
    screen, _ = home(FakeContext(engine=engine))
    out = render(screen.widget(), 110, 40)
    assert "[x] 3" in out and "[x] 4" in out
