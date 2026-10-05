# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Secrets screen and the session-only secret (issue #321, D-081)."""

import json
import os
from pathlib import Path

import pytest

from hammunition.console.engine import Engine
from hammunition.console.guard import checked_argv
from hammunition.console.pane import build_pane_spec
from hammunition.console.screens.base import ConfirmScreen, MessageScreen, PromptScreen
from hammunition.console.screens.secrets import SecretsScreen
from hammunition.console.session import SessionRefused, SessionSecrets

from .helpers import FAKE, FakeContext, FakeEngine, make_shim, render

FAKE_TOKEN = "rbuapp_test_not_real"


def shown(ctx: FakeContext) -> tuple[SecretsScreen, str]:
    screen = SecretsScreen(ctx)
    screen.on_show()
    return screen, render(screen.widget(), 110, 30)


def ctx_for(state: str) -> FakeContext:
    return FakeContext(engine=FakeEngine(secrets=state))


def text_of(screen: object) -> str:
    return "\n".join(
        str(getattr(w, "original_widget", w).text)  # type: ignore[attr-defined]
        for w in screen._walker  # type: ignore[attr-defined]
        if hasattr(getattr(w, "original_widget", w), "text")
    )


def test_not_available_shows_the_two_ways_and_the_command() -> None:
    _screen, out = shown(ctx_for("none"))
    assert "REPEATERBOOK  not available" in out
    assert "hammunition install repeaterbook-client" in out
    assert "hammunition maps repeaters fetch-repeaterbook --state XX" in out
    assert "g get one" in out and "e enter for this session" in out
    assert "Doppler: not configured" in out and "not on PATH" in out


def test_environment_and_doppler_states() -> None:
    assert "available (source: environment)" in shown(ctx_for("environment"))[1]
    out = shown(ctx_for("doppler"))[1]
    assert "available (source: doppler)" in out and "project proj, config dev" in out


def test_get_one_prints_the_url_and_opens_nothing() -> None:
    ctx = ctx_for("none")
    screen, _ = shown(ctx)
    assert screen.keypress("g") is None
    msg = ctx.pushed[-1]
    assert isinstance(msg, MessageScreen)
    body = text_of(msg)
    assert "https://www.repeaterbook.com/user/api_apps.php" in body and "App #114" in body
    assert ctx.panes == []


def test_the_session_prompt_is_masked_and_the_value_never_drawn() -> None:
    ctx = ctx_for("none")
    screen, _ = shown(ctx)
    screen.keypress("e")
    prompt = ctx.pushed[-1]
    assert isinstance(prompt, PromptScreen)
    prompt._edit.set_edit_text(FAKE_TOKEN)
    drawn = render(prompt.widget(), 100, 10)
    assert FAKE_TOKEN not in drawn and "*" * len(FAKE_TOKEN) in drawn  # the box shows only masks
    assert prompt.keypress("enter") is None
    assert ctx.session.names() == {"REPEATERBOOK"}
    assert prompt._edit.edit_text == ""  # not kept in the widget after submission
    assert "set for this session" in text_of(screen)
    for shown_text in (text_of(screen), render(screen.widget(), 110, 30)):
        assert FAKE_TOKEN not in shown_text
    assert "entered for this session" in render(screen.widget(), 110, 30)
    assert ctx.panes == []  # entering runs nothing


def test_forget_clears_the_session_value() -> None:
    ctx = ctx_for("none")
    ctx.session.set("REPEATERBOOK", FAKE_TOKEN)
    screen, _ = shown(ctx)
    screen.keypress("x")
    assert ctx.session.names() == frozenset()


def test_doppler_form_runs_station_set_with_names_only() -> None:
    ctx = ctx_for("none")
    screen, _ = shown(ctx)
    screen.keypress("d")
    project = ctx.pushed[-1]
    project._edit.set_edit_text("hammunition")
    project.keypress("enter")
    config = ctx.pushed[-1]
    assert isinstance(config, PromptScreen)
    config._edit.set_edit_text("dev")
    config.keypress("enter")
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    confirm.keypress("R")
    pane = ctx.panes[-1]
    assert pane.argv == [
        "hammunition",
        "station",
        "set",
        "--doppler-project=hammunition",
        "--doppler-config=dev",
    ]
    pane.on_exit(0)
    assert "Saved" in text_of(screen)


def test_a_doppler_name_that_could_be_an_option_runs_nothing() -> None:
    ctx = ctx_for("none")
    screen, _ = shown(ctx)
    screen.keypress("d")
    ctx.pushed[-1]._edit.set_edit_text("--yes")
    ctx.pushed[-1].keypress("enter")
    assert ctx.panes == [] and len(ctx.pushed) == 1
    assert "Nothing was run" in text_of(screen)


def test_the_command_key_refuses_while_nothing_answers() -> None:
    ctx = ctx_for("none")
    screen, _ = shown(ctx)
    screen.keypress("f")
    assert ctx.panes == [] and ctx.pushed == []
    assert "No source answers" in text_of(screen)


def test_the_command_key_runs_the_fetch_in_a_pane_when_available() -> None:
    ctx = ctx_for("environment")
    screen, _ = shown(ctx)
    screen.keypress("f")
    ask = ctx.pushed[-1]
    ask._edit.set_edit_text("VT")
    ask.keypress("enter")
    ctx.pushed[-1].keypress("R")
    assert ctx.panes[-1].argv == [
        "hammunition",
        "maps",
        "repeaters",
        "fetch-repeaterbook",
        "--state",
        "VT",
    ]
    assert FAKE_TOKEN not in " ".join(ctx.panes[-1].argv)


def test_the_command_key_runs_after_a_session_entry_even_if_the_document_was_stale() -> None:
    ctx = ctx_for("none")
    ctx.session.set("REPEATERBOOK", FAKE_TOKEN)
    screen, _ = shown(ctx)
    screen.keypress("f")
    assert isinstance(ctx.pushed[-1], PromptScreen)


def test_a_bad_state_runs_nothing() -> None:
    ctx = ctx_for("environment")
    screen, _ = shown(ctx)
    screen.keypress("f")
    ctx.pushed[-1]._edit.set_edit_text("--state=x")
    ctx.pushed[-1].keypress("enter")
    assert ctx.panes == [] and len(ctx.pushed) == 1


def test_the_fetch_verb_is_a_pane_verb_and_the_assume_yes_flag_still_is_not() -> None:
    assert checked_argv(["hammunition", "maps", "repeaters", "fetch-repeaterbook", "--state", "VT"])
    from hammunition.console.guard import Refused

    with pytest.raises(Refused):
        checked_argv(["hammunition", "maps", "repeaters", "fetch-repeaterbook", "--yes"])


# -- the session value -------------------------------------------------------


def test_session_secrets_refuse_bad_names_and_values_without_echoing_them() -> None:
    s = SessionSecrets()
    for name in ("", "1X", "A B", "HAMMUNITION_ACCEPT_X", "ANY_CONSENT"):
        with pytest.raises(SessionRefused):
            s.set(name, FAKE_TOKEN)
    for value in ("", "a\nb", "a\x00b"):
        with pytest.raises(SessionRefused) as info:
            s.set("REPEATERBOOK", value)
        assert FAKE_TOKEN not in str(info.value)
    s.set("REPEATERBOOK", FAKE_TOKEN)
    assert FAKE_TOKEN not in repr(s)


def _log(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_the_engine_children_see_the_variable_only_after_it_is_entered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPEATERBOOK", raising=False)
    log = tmp_path / "fake.log"
    shim = make_shim(tmp_path)
    base = {
        "PATH": f"{shim}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_HAMMUNITION_LOG": str(log),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
    }
    session = SessionSecrets()
    engine = Engine(argv0=[str(shim / "hammunition")], environ=base, session=session)
    before = {p for p in Path(tmp_path).rglob("*")}
    first = engine.read("secrets", "status")
    session.set("REPEATERBOOK", FAKE_TOKEN)
    second = engine.read("secrets", "status")
    session.clear()
    engine.read("secrets", "status")
    entries = _log(log)
    assert [e["secrets_present"] for e in entries] == [[], ["REPEATERBOOK"], []]
    assert first.body["secrets"][0]["source"] == "none"
    assert second.body["secrets"][0]["source"] == "environment"
    assert FAKE_TOKEN not in log.read_text()
    assert "REPEATERBOOK" not in os.environ  # this process's own environment never held it
    new = {p for p in Path(tmp_path).rglob("*")} - before
    assert {p.name for p in new} <= {"fake.log"}, new
    for p in new:
        assert FAKE_TOKEN not in p.read_text()
    assert FAKE.exists()


def test_a_pane_child_gets_the_session_variable_and_a_later_one_does_not(
    tmp_path: Path,
) -> None:
    session = SessionSecrets()
    environ = {"PATH": os.environ["PATH"]}
    session.set("REPEATERBOOK", FAKE_TOKEN)
    spec = build_pane_spec(
        ["hammunition", "maps", "repeaters", "fetch-repeaterbook", "--state", "VT"],
        str(tmp_path / "s"),
        session.overlay(environ),
    )
    assert spec.env["REPEATERBOOK"] == FAKE_TOKEN
    assert FAKE_TOKEN not in " ".join(spec.command)  # never argv
    session.clear()
    later = build_pane_spec(
        ["hammunition", "station", "set"], str(tmp_path / "s"), session.overlay(environ)
    )
    assert "REPEATERBOOK" not in later.env


def test_the_scripted_consent_variables_are_still_stripped_with_a_session() -> None:
    s = SessionSecrets()
    s.set("REPEATERBOOK", FAKE_TOKEN)
    spec = build_pane_spec(
        ["hammunition", "station", "set"],
        "/tmp/x",
        s.overlay({"HAMMUNITION_ACCEPT_RF_RESEARCH": "1"}),
    )
    assert "HAMMUNITION_ACCEPT_RF_RESEARCH" not in spec.env
