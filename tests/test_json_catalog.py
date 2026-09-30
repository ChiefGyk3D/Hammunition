# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``list --json`` and ``show --json``: what the catalog offers.  D-059."""

from __future__ import annotations

import importlib

import pytest

from hammunition.distro import DetectionError, Target
from json_support import (
    FIXTURE_CATALOG,
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(
    distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13 (trixie)"
)
RUNS = {
    "list-all": ["list"],
    "list-packages": ["list", "packages"],
    "list-profiles": ["list", "profiles"],
    "show-gated": ["show", "fixture-gated"],
    "show-station": ["show", "fixture-station"],
}


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    *,
    target: Target | None = TARGET,
) -> tuple[int, str]:
    def detect(cls: type) -> Target:
        if target is None:
            raise DetectionError("no /etc/os-release")
        return target

    monkeypatch.setattr(Target, "detect", classmethod(detect))
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), *argv])
    return rc, capsys.readouterr().out


@pytest.mark.parametrize("name", sorted(RUNS))
def test_the_text_is_unchanged(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, RUNS[name])
    assert rc == 0
    assert_golden_text(name, out)


@pytest.mark.parametrize("name", sorted(RUNS))
def test_the_document_matches_its_golden_and_its_schema(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, [*RUNS[name], "--json"])
    assert rc == 0
    doc = parse_one(out)
    validate(doc)
    assert_golden(name, doc)


@pytest.mark.parametrize("name", sorted(RUNS))
def test_every_value_the_text_shows_is_in_the_json(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.catalog import render_catalog, render_profile

    _rc, text = _run(monkeypatch, capsys, RUNS[name])
    _rc, out = _run(monkeypatch, capsys, [*RUNS[name], "--json"])
    assert_text_values_in_json(text, parse_one(out), render_catalog, render_profile)


def test_an_unknown_target_lists_every_package_as_unknown_not_unsupported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, ["list", "--json"], target=None)
    doc = parse_one(out)
    assert rc == 0 and doc["target"] is None
    assert {p["resolves_here"] for p in doc["packages"]} == {None}


def test_show_of_a_unit_is_json_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, ["show", "fixture-apt", "--json"])
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "unit"
    validate(doc)
    assert doc["manifest"]["name"] == "fixture-apt"
    assert_golden("show-unit", doc)
    # The text form is unchanged: it describes profiles, and says so.
    rc, _out = _run(monkeypatch, capsys, ["show", "fixture-apt"])
    assert rc == cli.EXIT_UNPLANNABLE


def test_show_of_an_unknown_name_is_an_error_document_with_exit_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, ["show", "no-such-thing", "--json"])
    doc = parse_one(out)
    assert rc == cli.EXIT_UNPLANNABLE and doc["kind"] == "error"
    assert "no-such-thing" in doc["message"]
