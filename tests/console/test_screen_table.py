# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The spec: a command with no JSON form returns an error document, ran nothing, and is a bug in the
screen table. Two checks: statically, every literal verb in the package is a JSON verb; dynamically,
driving every screen reads exactly the verbs below, so a new read cannot slip in unseen."""

import re
from collections.abc import Callable
from typing import Any

from hammunition.console.screens.help import HelpScreen, ProfileDocsScreen
from hammunition.console.screens.home import HomeScreen
from hammunition.console.screens.install import InstallScreen
from hammunition.console.screens.logs import LogsScreen
from hammunition.console.screens.plan import PlanScreen
from hammunition.console.screens.repeaters import LookupScreen, RepeatersScreen
from hammunition.console.screens.station import StationScreen
from hammunition.console.screens.update import UpdateScreen
from hammunition.console.verbs import JSON_VERBS, verb_of

from .helpers import PACKAGE_DIR, FakeContext, FakeEngine

PACKAGE = PACKAGE_DIR
READ = re.compile(
    r"engine\.read\(\s*\"([a-z-]+)\"(?:\s*,\s*\"([a-z-]+)\")?(?:\s*,\s*\"([a-z-]+)\")?"
)
EXPECTED = {
    ("status",),
    ("doctor",),
    ("list",),
    ("show",),
    ("logs",),
    ("update",),
    ("station", "show"),
    ("install",),
    ("uninstall",),
    ("maps", "regions"),
    ("maps", "areas"),
    ("maps", "repeaters", "list"),
    ("reference", "books"),
}

PER_SCREEN: dict[str, set[tuple[str, ...]]] = {
    "home": {("doctor",), ("list",), ("logs",), ("station", "show"), ("status",), ("update",)},
    "install": {("list",)},
    "station": {("station", "show")},
    "logs": {("logs",)},
    "repeaters": {("maps", "areas"), ("maps", "repeaters", "list")},
    "lookup": {("maps", "repeaters", "list")},
    "update": {("update",)},
    "update-names": {("update",)},
    "help": {("list",)},
    "profile-docs": {("show",)},
    "plan-install": {("install",)},
    "plan-uninstall": {("uninstall",)},
}


def test_every_literal_read_in_the_package_is_a_json_verb() -> None:
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for m in READ.finditer(path.read_text()):
            words = tuple(w for w in m.groups() if w)
            found.append((path.name, words))
            assert verb_of(words) in JSON_VERBS, f"{path.name}: {words} has no --json form"
    assert len(found) >= 8, "the scan found too few reads to mean anything"


# Reads built from a variable. The static scan cannot see them; the dynamic test below drives each one
# (home, update and plan) and pins its verbs. A new entry here needs the same.
NON_LITERAL = {"home.py": 1, "update.py": 1, "plan.py": 1, "repeaters.py": 1}


def test_every_engine_read_is_a_literal_the_scan_can_see() -> None:
    for path in sorted(PACKAGE.rglob("*.py")):
        text = path.read_text()
        invisible = text.count("engine.read(") - len(READ.findall(text))
        assert invisible == NON_LITERAL.get(path.name, 0), (
            f"{path.name}: {invisible} engine.read( call(s) not written as literal verb strings; the static check cannot "
            "see them. Write the verbs as literals, or list the file in NON_LITERAL and pin its verbs in PER_SCREEN"
        )


def driven() -> list[tuple[str, FakeContext, object]]:
    def ctx_screen(
        name: str, make: Callable[[FakeContext], Any]
    ) -> tuple[str, FakeContext, object]:
        ctx = FakeContext()
        return name, ctx, make(ctx)

    return [
        ctx_screen("home", HomeScreen),
        ctx_screen("install", InstallScreen),
        ctx_screen("station", StationScreen),
        ctx_screen("logs", LogsScreen),
        ctx_screen("repeaters", RepeatersScreen),
        ctx_screen("lookup", lambda c: LookupScreen(c, ["maps", "repeaters", "list"])),
        ctx_screen("update", UpdateScreen),
        ctx_screen("update-names", lambda c: UpdateScreen(c, names=["station"])),
        ctx_screen("help", HelpScreen),
        ctx_screen("profile-docs", lambda c: ProfileDocsScreen(c, "station")),
        ctx_screen("plan-install", lambda c: PlanScreen(c, "install", ["station"])),
        ctx_screen("plan-uninstall", lambda c: PlanScreen(c, "uninstall", ["station"])),
    ]


def test_driving_every_screen_reads_exactly_its_own_verbs_and_none_fail() -> None:
    seen: set[tuple[str, ...]] = set()
    for name, ctx, screen in driven():
        screen.on_show()  # type: ignore[attr-defined]
        engine: FakeEngine = ctx.engine
        assert engine.refused == [], f"{name} read a verb with no --json form: {engine.refused}"
        assert screen.errors == {}, f"{name} ended with errors: {screen.errors}"  # type: ignore[attr-defined]
        assert {verb_of(c) for c in engine.calls} == PER_SCREEN[name], f"{name} read {engine.calls}"
        seen |= {verb_of(c) for c in engine.calls}
    ctx = FakeContext()
    station = StationScreen(ctx)
    station.on_show()
    station._choose_books()
    ctx.pushed[-1].on_show()
    station._search_regions("vermont")
    ctx.pushed[-1].on_show()
    engine = ctx.engine
    assert engine.refused == []
    seen |= {verb_of(call) for call in engine.calls}
    assert seen == EXPECTED
    assert EXPECTED <= JSON_VERBS
