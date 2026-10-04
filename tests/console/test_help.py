# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path

from hammunition.console.engine import EngineRefused
from hammunition.console.helptext import KEYS, NEVER, SCREEN_HELP
from hammunition.console.screens.help import HelpScreen, ProfileDocsScreen, profile_lines
from hammunition.console.screens.install import InstallScreen

from .helpers import FakeContext, FakeEngine, document, load, render


def help_out(
    about: str = "", ctx: FakeContext | None = None
) -> tuple[HelpScreen, FakeContext, str]:
    ctx = ctx or FakeContext()
    screen = HelpScreen(ctx, about=about)
    screen.on_show()
    return screen, ctx, render(screen.widget(), 110, 60)


def test_help_lists_every_key_and_what_the_console_never_does() -> None:
    _, _, out = help_out()
    for keys, meaning in KEYS:
        assert keys in out and meaning[:30] in out
    for line in NEVER:
        assert line[:40] in out


def test_help_opens_with_the_page_you_came_from() -> None:
    _, _, out = help_out("install")
    assert SCREEN_HELP["install"][0] in out and out.index(SCREEN_HELP["install"][0]) < out.index(
        "Keys"
    )


def test_an_unknown_origin_shows_just_the_general_help() -> None:
    _, _, out = help_out("pane")
    assert "Keys" in out


def test_every_screen_has_help_text() -> None:
    assert set(SCREEN_HELP) >= {"home", "install", "plan", "station", "logs", "update", "help"}
    assert all(lines for lines in SCREEN_HELP.values())


def test_profiles_are_listed_and_enter_opens_their_documentation() -> None:
    screen, ctx, out = help_out()
    first = load("list-all")["profiles"][0]["name"]
    assert first in out
    next(r for r in screen._walker if getattr(r, "value", None) == first).keypress((100,), "enter")
    docs = ctx.pushed[-1]
    assert isinstance(docs, ProfileDocsScreen) and docs.profile == first


def test_a_failed_profile_list_is_shown_and_the_rest_still_works() -> None:
    engine = FakeEngine()
    engine.set(("list",), EngineRefused(2, "no catalog"))
    _, _, out = help_out(ctx=FakeContext(engine=engine))
    assert "no catalog" in out and "Keys" in out


def test_profile_documentation_shows_the_five_fields_and_the_gate_text_without_the_variable_name() -> (
    None
):
    ctx = FakeContext()
    name = json.loads((Path(__file__).parent / "fixtures" / "manifest.json").read_text())["gated"]
    screen = ProfileDocsScreen(ctx, name)
    screen.on_show()
    out = render(screen.widget(), 110, 60)
    doc = load("show-gated")
    for key in (
        "what_it_installs",
        "why_together",
        "deliberately_excludes",
        "manual_configuration",
    ):
        assert doc["documentation"][key][:30] in out
    assert doc["consent"]["disclosure"].splitlines()[0][:40] in out and "type yes" in out
    assert doc["consent"]["env_var"] not in out and "HAMMUNITION_ACCEPT" not in out


def test_null_documentation_never_prints_none() -> None:
    lines = profile_lines(
        {
            "name": "p",
            "summary": None,
            "stage": None,
            "packages": None,
            "suggests_one_of": None,
            "consent": None,
            "documentation": {
                "what_it_installs": None,
                "why_together": None,
                "deliberately_excludes": None,
                "manual_configuration": None,
                "disk_footprint_hint": None,
            },
        }
    )
    assert "None" not in "\n".join(lines)


def test_suggestions_are_shown() -> None:
    lines = profile_lines(
        {
            "name": "p",
            "documentation": {},
            "suggests_one_of": [
                {
                    "name": "logger",
                    "reason": "pick one",
                    "options": ["a", "b"],
                    "recommended": "a",
                    "detect_commands": [],
                }
            ],
        }
    )
    assert any("logger" in x and "a, b" in x and "recommended a" in x for x in lines)


def test_install_i_opens_the_focused_profiles_documentation() -> None:
    ctx = FakeContext()
    install = InstallScreen(ctx)
    install.on_show()
    row = next(r for r in install._walker if getattr(r, "value", None) and r.value[0] == "profile")
    install._walker.set_focus(install._walker.index(row))
    assert install.keypress("i") is None
    assert (
        isinstance(ctx.pushed[-1], ProfileDocsScreen)
        and ctx.pushed[-1].profile == row.value[1]["name"]
    )


def test_profile_docs_error_is_shown() -> None:
    engine = FakeEngine()
    engine.set(("show", "x"), EngineRefused(2, "no such profile"))
    screen = ProfileDocsScreen(FakeContext(engine=engine), "x")
    screen.on_show()
    assert "no such profile" in render(screen.widget(), 100, 10)


def test_engine_text_is_cleaned() -> None:
    engine = FakeEngine()
    engine.set(
        ("show", "x"),
        document(
            "profile",
            {
                "name": "x",
                "summary": "s\x1b[2J",
                "stage": "1.0",
                "packages": [],
                "documentation": {},
                "consent": None,
                "suggests_one_of": [],
            },
        ),
    )
    screen = ProfileDocsScreen(FakeContext(engine=engine), "x")
    screen.on_show()
    assert "\x1b" not in render(screen.widget(), 100, 10)


def test_help_fits_an_80x24_terminal() -> None:
    ctx = FakeContext()
    screen = HelpScreen(ctx, about="install")
    screen.on_show()
    out = render(screen.widget(), 80, 24)
    assert "This screen (install)" in out and SCREEN_HELP["install"][0] in out and "Keys" in out
