# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition secrets status`` (issue #321, D-081, D-059): where each secret
would come from, and never what it is."""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from hammunition import secrets
from hammunition.cli.main import main
from hammunition.interface.secrets import build_secrets, render_secrets
from hammunition.station import Station

# Synthetic. Its absence from every output is the test.
FAKE = "rbuapp_test_not_real"
NAMED = Station(secrets_doppler_project="proj", secrets_doppler_config="dev")


def _which(found: bool) -> Callable[[str], str | None]:
    return lambda name: "/usr/bin/doppler" if found and name == "doppler" else None


def test_environment_variable_wins() -> None:
    doc = build_secrets(env={"REPEATERBOOK": FAKE}, station=NAMED, which=_which(True))
    row = doc.secrets[0]
    assert (row.name, row.available, row.source) == ("REPEATERBOOK", True, "environment")


def test_doppler_named_and_cli_present() -> None:
    doc = build_secrets(env={}, station=NAMED, which=_which(True))
    assert doc.secrets[0].source == "doppler" and doc.secrets[0].available
    assert doc.doppler.configured and doc.doppler.cli_on_path
    assert (doc.doppler.project, doc.doppler.config) == ("proj", "dev")
    assert "not asked" in doc.secrets[0].detail  # status never runs doppler


def test_doppler_named_but_no_cli_is_not_available() -> None:
    doc = build_secrets(env={}, station=NAMED, which=_which(False))
    assert doc.secrets[0].source == "none" and not doc.secrets[0].available
    assert "not on PATH" in doc.secrets[0].detail


def test_nothing_configured() -> None:
    doc = build_secrets(env={"REPEATERBOOK": ""}, station=None, which=_which(True))
    row = doc.secrets[0]
    assert (row.source, row.available) == ("none", False)
    assert not doc.doppler.configured
    ways = " ".join(row.ways)
    assert "export REPEATERBOOK=..." in ways
    assert "station set --doppler-project" in ways and "--doppler-config" in ways


def test_the_row_names_its_unit_command_and_url() -> None:
    row = build_secrets(env={}, station=None, which=_which(False)).secrets[0]
    assert row.unit == "repeaterbook-client"
    assert row.command == "hammunition maps repeaters fetch-repeaterbook --state XX"
    assert row.get_url.startswith("https://www.repeaterbook.com/")


def test_the_value_is_in_no_rendering_even_when_set() -> None:
    doc = build_secrets(env={"REPEATERBOOK": FAKE}, station=NAMED, which=_which(True))
    blob = json.dumps(doc, default=lambda o: o.__dict__) + "\n".join(render_secrets(doc))
    assert FAKE not in blob
    for cut in (FAKE[:4], FAKE[-4:], str(len(FAKE))):
        # a prefix, a suffix or the length would each leak something
        assert cut not in "\n".join(render_secrets(doc)).replace("REPEATERBOOK", "")


def test_the_cli_prints_one_document_and_never_the_value(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPEATERBOOK", FAKE)
    assert main(["secrets", "status", "--json"]) == 0
    out = capsys.readouterr()
    doc = json.loads(out.out)
    assert doc["kind"] == "secrets" and doc["secrets"][0]["source"] == "environment"
    assert FAKE not in out.out + out.err
    assert main(["secrets", "status"]) == 0
    text = capsys.readouterr()
    assert FAKE not in text.out + text.err and "REPEATERBOOK" in text.out


def test_status_writes_nothing_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = Path.home()
    before = sorted(p for p in home.rglob("*") if p.is_file())
    monkeypatch.setenv("REPEATERBOOK", FAKE)
    main(["secrets", "status", "--json"])
    capsys.readouterr()
    assert sorted(p for p in home.rglob("*") if p.is_file()) == before


def _resolve_calls() -> list[ast.Call]:
    root = Path(secrets.__file__).parent
    calls: list[ast.Call] = []
    for path in root.rglob("*.py"):
        if path == Path(secrets.__file__):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and (
                    getattr(node.func, "id", None) == "resolve_secret"
                    or getattr(node.func, "attr", None) == "resolve_secret"
                )
                and node.args
            ):
                calls.append(node)
    return calls


def test_the_registry_names_every_secret_the_engine_resolves() -> None:
    from hammunition import repeaterbook

    calls = _resolve_calls()
    assert calls, "the grep found no resolve_secret( call: the test would pass on nothing"
    names = set()
    for call in calls:
        arg = call.args[0]
        if isinstance(arg, ast.Constant):
            names.add(str(arg.value))
        elif isinstance(arg, ast.Attribute) and hasattr(repeaterbook, arg.attr):
            names.add(getattr(repeaterbook, arg.attr))
        else:
            pytest.fail(f"cannot read the secret name at line {call.lineno}: use a constant")
    missing = names - {s.name for s in secrets.REGISTRY}
    assert not missing, f"add {sorted(missing)} to hammunition.secrets.REGISTRY"


def test_registry_entries_are_complete_and_unique() -> None:
    names = [s.name for s in secrets.REGISTRY]
    assert len(names) == len(set(names))
    for s in secrets.REGISTRY:
        assert s.purpose and s.get_url.startswith("https://") and s.command and s.doc
        assert (Path(secrets.__file__).parents[2] / s.doc).exists(), s.doc


def test_golden_documents_and_text_agree() -> None:
    from hammunition.interface import envelope
    from json_support import (
        assert_golden,
        assert_golden_text,
        assert_text_values_in_json,
        parse_one,
        validate,
    )

    doc = build_secrets(env={}, station=NAMED, which=_which(True))
    out = parse_one(envelope.dumps(doc))
    validate(out)
    assert_golden("secrets-doppler", out)
    text = "\n".join(render_secrets(doc)) + "\n"
    assert_golden_text("secrets-doppler", text)
    assert_text_values_in_json(text, out, render_secrets)
