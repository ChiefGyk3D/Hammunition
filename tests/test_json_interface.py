# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``--json`` plumbing every command shares.  D-059.

One document on stdout and nothing else there, diagnostics on stderr, the
exit code the text run would return -- on every path, including a refusal
before anything was resolved. The per-command documents are tested beside
their commands; this file tests the envelope, the flag, and the helpers
those tests lean on.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from hammunition.interface import envelope
from hammunition.interface.envelope import SCHEMA, ErrorDocument, Strict, described
from json_support import assert_text_values_in_json, parse_one, validate

# The module, not the `main` function `hammunition.cli` re-exports.
cli = importlib.import_module("hammunition.cli.main")


@dataclass(frozen=True)
class _Probe(Strict):
    """A document only this test emits."""

    KIND: ClassVar[str] = "probe"
    value: str = described("what the probe command was given")


def _install_probe(monkeypatch: pytest.MonkeyPatch, body: Any) -> None:
    """Make `status` a JSON-capable probe running *body*, for plumbing tests
    that must not depend on any real command's document."""

    @envelope.json_capable()
    def probe(args: argparse.Namespace) -> int:
        result: int = body(args)
        return result

    monkeypatch.setattr(cli, "cmd_status", probe)


def test_the_flag_works_on_either_side_of_the_verb(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def body(args: argparse.Namespace) -> int:
        envelope.emit(_Probe(value="N0TST"))
        return 0

    _install_probe(monkeypatch, body)
    for argv in (["--json", "status"], ["status", "--json"]):
        assert cli.main(argv) == 0
        doc = parse_one(capsys.readouterr().out)
        assert doc == {"schema": SCHEMA, "kind": "probe", "engine": doc["engine"], "value": "N0TST"}


def test_without_the_flag_nothing_changes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[bool] = []

    def body(args: argparse.Namespace) -> int:
        seen.append(envelope.wanted(args))
        print("text as before")
        return 0

    _install_probe(monkeypatch, body)
    assert cli.main(["status"]) == 0
    assert seen == [False]
    assert capsys.readouterr().out == "text as before\n"


def test_anything_a_command_prints_goes_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def body(args: argparse.Namespace) -> int:
        print("note: a stray line of text")
        envelope.emit(_Probe(value="x"))
        return 0

    _install_probe(monkeypatch, body)
    assert cli.main(["status", "--json"]) == 0
    captured = capsys.readouterr()
    parse_one(captured.out)
    assert "note: a stray line of text" in captured.err


def test_a_json_run_never_asks_a_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review focus: on a real terminal a prompt under --json would put a
    question in front of a front end that cannot answer it."""
    from hammunition import station

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    answers: list[bool] = []

    def body(args: argparse.Namespace) -> int:
        answers.append(station.is_interactive())
        envelope.emit(_Probe(value="x"))
        return 0

    _install_probe(monkeypatch, body)
    assert cli.main(["status", "--json"]) == 0
    assert answers == [False]
    parse_one(capsys.readouterr().out)


def test_a_command_that_ends_without_a_document_gets_an_error_document(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def body(args: argparse.Namespace) -> int:
        print("error: the target could not be read", file=sys.stderr)
        return 1

    _install_probe(monkeypatch, body)
    assert cli.main(["status", "--json"]) == 1
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error"
    assert doc["exit_code"] == 1
    assert doc["command"] == "status"
    assert "the target could not be read" in doc["message"]
    validate(doc)


def test_a_catalog_that_cannot_be_found_is_a_document_with_exit_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """find_catalog raises SystemExit(str); the interpreter would print it and
    exit 1, and under --json that becomes the document's message."""

    def body(args: argparse.Namespace) -> int:
        raise SystemExit("could not find the catalog")

    _install_probe(monkeypatch, body)
    assert cli.main(["status", "--json"]) == 1
    captured = capsys.readouterr()
    doc = parse_one(captured.out)
    assert doc["kind"] == "error" and doc["exit_code"] == 1
    assert "could not find the catalog" in doc["message"]
    assert "could not find the catalog" in captured.err


def test_arguments_that_do_not_parse_are_a_document_with_argparses_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--json", "list", "nonsense"]) == 2
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error" and doc["exit_code"] == 2 and doc["command"] == ""
    assert "invalid choice" in doc["message"]


def test_a_command_with_no_json_form_is_refused_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """`station set` writes a file; under --json it must refuse before that."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    rc = cli.main(["station", "set", "--callsign", "N0TST", "--json"])
    assert rc == cli.EXIT_UNPLANNABLE
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error" and doc["command"] == "station set"
    assert "no --json form" in doc["message"]
    assert not any(tmp_path.rglob("station.yml")), "a refused --json run wrote the station file"


def test_help_under_json_prints_no_document(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--json", "--help"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err


def test_every_subcommand_accepts_the_flag() -> None:
    """Walked, not listed: a verb added later must carry --json without
    anyone remembering to add it."""
    parser = cli.build_parser()

    def leaves(p: argparse.ArgumentParser, path: list[str]) -> list[tuple[list[str], Any]]:
        subs = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            return [(path, p)]
        return [
            leaf for name, child in subs[0].choices.items() for leaf in leaves(child, [*path, name])
        ]

    for path, leaf in leaves(parser, []):
        options = {o for a in leaf._actions for o in a.option_strings}
        assert "--json" in options, f"`hammunition {' '.join(path)}` does not accept --json"


def test_a_second_document_is_a_bug_not_a_second_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def body(args: argparse.Namespace) -> int:
        envelope.emit(_Probe(value="one"))
        envelope.emit(_Probe(value="two"))
        return 0

    _install_probe(monkeypatch, body)
    with pytest.raises(RuntimeError, match="exactly one document"):
        cli.main(["status", "--json"])


def test_non_ascii_is_written_as_utf8_not_escaped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The text is full of em dashes and arrows; a front end reads them as-is."""

    def body(args: argparse.Namespace) -> int:
        envelope.emit(_Probe(value="not parkable right now — unplugged → wake"))
        return 0

    _install_probe(monkeypatch, body)
    cli.main(["status", "--json"])
    out = capsys.readouterr().out
    assert "—" in out and "\\u2014" not in out
    assert parse_one(out)["value"] == "not parkable right now — unplugged → wake"


def test_every_kind_has_a_docstring_and_every_field_a_description() -> None:
    kinds = envelope.kinds()
    assert "error" in kinds, "kind discovery found nothing; the checks below would pass empty"
    for kind, cls in kinds.items():
        for c in (cls, *_nested(cls)):
            assert c.__doc__ and not c.__doc__.startswith(f"{c.__name__}("), (
                f"{c.__name__} ({kind}) has no docstring; the reference page prints it"
            )
            for f in dataclasses.fields(c):
                assert f.metadata.get("doc"), f"{c.__name__}.{f.name} has no described() text"


def _nested(cls: type) -> list[type]:
    import typing

    found: list[type] = []

    def walk(tp: object) -> None:
        for arg in typing.get_args(tp):
            walk(arg)
        if isinstance(tp, type) and dataclasses.is_dataclass(tp) and tp not in found:
            found.append(tp)
            for hint in typing.get_type_hints(tp).values():
                walk(hint)

    for hint in typing.get_type_hints(cls).values():
        walk(hint)
    return found


def test_the_error_document_validates_and_rejects_an_unknown_field() -> None:
    body = dataclasses.asdict(ErrorDocument(command="status", exit_code=1, message="m"))
    validate({"schema": SCHEMA, "kind": "error", "engine": "x", **body})
    with pytest.raises(ValidationError, match="surprise"):
        validate({"schema": SCHEMA, "kind": "error", "engine": "x", **body, "surprise": 1})


def _chrome() -> None:
    print("Target:")


def test_the_parity_check_goes_red_when_the_json_drops_a_value() -> None:
    """Falsified first (CLAUDE.md): a value in the text and not in the JSON fails."""
    text = "Target: Parrot-7.3 N0TST"
    assert_text_values_in_json(text, {"target": "Parrot-7.3", "call": "N0TST"}, _chrome)
    with pytest.raises(AssertionError, match="N0TST"):
        assert_text_values_in_json(text, {"target": "Parrot-7.3"}, _chrome)


def test_document_refuses_a_class_without_a_kind() -> None:
    @dataclass(frozen=True)
    class NoKind:
        value: int

    with pytest.raises(TypeError, match="not a document kind"):
        envelope.document(NoKind(1))
    assert json.loads(envelope.dumps(_Probe(value="v")))["kind"] == "probe"
