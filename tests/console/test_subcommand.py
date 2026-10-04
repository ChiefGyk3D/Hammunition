# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""`hammunition console` as the engine's CLI sees it: help and version, the refusals, the
missing-urwid line, and the fact that the verb has no --json form."""

import io
import json
import os
import subprocess
import sys

import pytest

from hammunition.cli.main import main
from hammunition.console.__main__ import missing_urwid_line
from hammunition.interface.envelope import engine_version


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def at_a_terminal(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """A terminal-looking stdin and stdout, an ordinary user and a drawable TERM; returns the
    captured stderr. Called from the test body: pytest's own capture re-patches sys.stdout
    between fixture setup and the call, and capsys would replace the stdout that must look
    like a tty."""
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("TERM", "xterm-256color")
    return err


def test_help_is_the_consoles_own_and_lists_the_keys(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["console", "--help"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: hammunition console") and "Keys:" in out and "Exit codes:" in out


def test_version_is_the_engines_and_there_is_no_second_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["console", "--version"]) == 0
    assert capsys.readouterr().out.strip() == f"hammunition {engine_version()}"


def test_the_verb_is_in_the_engines_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0 and "console" in capsys.readouterr().out


def test_an_unknown_argument_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["console", "--bogus"]) == 2
    assert "--bogus" in capsys.readouterr().err


def test_no_terminal_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    # pytest's stdin and stdout are not terminals
    assert main(["console"]) == 2
    assert "terminal" in capsys.readouterr().err


def test_a_dumb_terminal_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = at_a_terminal(monkeypatch)
    monkeypatch.setenv("TERM", "dumb")
    assert main(["console"]) == 2
    assert "TERM" in terminal.getvalue()


def test_root_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = at_a_terminal(monkeypatch)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert main(["console"]) == 2
    assert "root" in terminal.getvalue()


def test_missing_urwid_is_one_line_and_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = at_a_terminal(monkeypatch)
    monkeypatch.setitem(sys.modules, "urwid", None)  # `import urwid` now raises ImportError
    assert main(["console"]) == 2
    err = terminal.getvalue()
    assert len(err.strip().splitlines()) == 1
    assert "urwid" in err and (
        "apt install python3-urwid" in err or "pip install 'hammunition[console]'" in err
    )


@pytest.mark.parametrize(
    ("in_venv", "debian", "expected"),
    [
        (False, True, "sudo apt install python3-urwid"),
        (
            True,
            True,
            "pip install 'hammunition[console]'",
        ),  # a venv does not see the archive's module
        (False, False, "pip install 'hammunition[console]'"),
    ],
)
def test_the_missing_urwid_line_names_the_route_that_works_here(
    in_venv: bool, debian: bool, expected: str
) -> None:
    line = missing_urwid_line(in_venv=in_venv, debian=debian)
    assert expected in line and "\n" not in line


def test_the_help_and_version_never_need_urwid(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "urwid", None)
    assert main(["console", "--help"]) == 0 and main(["console", "--version"]) == 0


def test_the_console_has_no_json_form(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["console", "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert code != 0 and doc["kind"] == "error" and doc["command"] == "console"
    assert "no --json form" in doc["message"]


def test_the_engine_itself_never_imports_urwid() -> None:
    """`hammunition` without the extra must work: importing the CLI pulls in no urwid."""
    code = (
        "import sys; sys.modules['urwid'] = None\n"
        "from hammunition.cli.main import main\n"
        "raise SystemExit(main(['list', '--json']))"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
