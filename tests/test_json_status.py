# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``status --json``: the machine, the catalog, and what the log records.  D-059."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from hammunition.distro import Target
from hammunition.state import TransactionLog, log_path
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

BEGIN: dict[str, Any] = {
    "event": "transaction_begin",
    "version": 2,
    "timestamp": "2026-09-28T12:00:00+00:00",
    "packages": ["fixture-apt", "fixture-source", "gone-unit"],
    "apt_packages": ["fixture-apt", "build-essential"],
    "deferred": [
        {
            "kind": "config",
            "subject": "fixture-source",
            "what": "/etc/fixture.conf not written",
            "why": "no callsign set",
        }
    ],
}
UNINSTALL_BEGIN: dict[str, Any] = {
    "event": "uninstall_begin",
    "version": 1,
    "timestamp": "2026-09-28T13:00:00+00:00",
    "packages": ["fixture-apt"],
    "apt_packages": ["fixture-apt"],
}
SCENARIOS: dict[str, list[dict[str, Any]]] = {
    "empty": [],
    "unverified": [
        BEGIN,
        {
            "event": "transaction_end",
            "version": 2,
            "completed": 4,
            "verified": False,
            "checks": [
                {"subject": "fixture-apt: installed", "confirmed": True},
                {
                    "subject": "fixture-source: /usr/local/bin/fixture",
                    "detail": "not on disk",
                    "confirmed": False,
                },
            ],
        },
    ],
    "failed": [BEGIN, {"event": "transaction_failed", "version": 1, "completed": 2}],
    "interrupted": [BEGIN, {"event": "command_begin", "version": 1, "argv": ["apt-get"]}],
    "uninstalled": [
        BEGIN,
        {"event": "transaction_end", "version": 1, "completed": 4},
        UNINSTALL_BEGIN,
        {"event": "uninstall_end", "version": 1, "completed": 1, "verified": True, "checks": []},
    ],
    "reinstalled": [
        BEGIN,
        {"event": "transaction_end", "version": 1, "completed": 4},
        UNINSTALL_BEGIN,
        {"event": "uninstall_end", "version": 1, "completed": 1, "verified": True, "checks": []},
        {**BEGIN, "timestamp": "2026-09-28T14:00:00+00:00", "packages": ["fixture-apt"]},
        {"event": "transaction_end", "version": 1, "completed": 1},
    ],
}


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    entries: list[dict[str, Any]],
    *flags: str,
) -> tuple[int, str]:
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "root")
    log = TransactionLog(log_path())
    for entry in entries:
        log.append(entry)
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), "status", *flags])
    out = capsys.readouterr().out
    return rc, out.replace(str(tmp_path), "<state>").replace(str(FIXTURE_CATALOG), "<catalog>")


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_text_is_unchanged(
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc, out = _run(monkeypatch, tmp_path, capsys, SCENARIOS[scenario])
    assert rc == 0
    assert_golden_text(f"status-{scenario}", out)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_document_matches_its_golden_and_its_schema(
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc, out = _run(monkeypatch, tmp_path, capsys, SCENARIOS[scenario], "--json")
    assert rc == 0
    doc = parse_one(out)
    assert doc["kind"] == "status"
    validate(doc)
    assert_golden(f"status-{scenario}", doc)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_every_value_the_text_shows_is_in_the_json(
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hammunition.interface.status import render_status

    _rc, text = _run(monkeypatch, tmp_path, capsys, SCENARIOS[scenario])
    _rc, out = _run(monkeypatch, tmp_path / "again", capsys, SCENARIOS[scenario], "--json")
    assert_text_values_in_json(text, parse_one(out), render_status)


def test_recorded_units_say_how_the_last_transaction_naming_them_ended(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not a claim the unit is installed now -- `update --json` asks the
    machine -- but what the log recorded, with the catalog's method and pin."""
    _rc, out = _run(monkeypatch, tmp_path, capsys, SCENARIOS["failed"], "--json")
    units = {u["name"]: u for u in parse_one(out)["recorded_units"]}
    assert units["fixture-apt"]["last_outcome"] == "failed"
    assert units["fixture-apt"]["method"] == "apt" and units["fixture-apt"]["pin"] is None
    assert units["fixture-source"]["pin"].startswith("sha256 30cf6db1a2b4")
    assert units["gone-unit"]["method"] is None, "a unit the catalog no longer has is not guessed"


def test_completed_units_remain_visible_when_a_later_install_step_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [
        BEGIN,
        {
            "event": "unit_end",
            "version": 1,
            "unit": "fixture-apt",
            "ok": True,
        },
        {"event": "transaction_failed", "version": 1, "completed": 2},
    ]
    rc, out = _run(monkeypatch, tmp_path, capsys, entries, "--json")
    assert rc == 0
    units = {u["name"]: u for u in parse_one(out)["recorded_units"]}
    assert units["fixture-apt"]["last_outcome"] == "completed"
    assert units["fixture-apt"]["completed_in_failed_run"] == BEGIN["timestamp"]
    assert units["fixture-source"]["last_outcome"] == "failed"
    validate(parse_one(out))

    _rc, text = _run(monkeypatch, tmp_path / "text", capsys, entries)
    assert "finished before it stopped, so a rerun verifies them (1):" in text
    assert "    fixture-apt" in text


@pytest.mark.parametrize(
    ("scenario", "outcome", "when"),
    [
        ("uninstalled", "removed", "2026-09-28T13:00:00+00:00"),
        ("reinstalled", "completed", "2026-09-28T14:00:00+00:00"),
    ],
)
def test_an_uninstall_is_folded_into_the_recorded_units(
    scenario: str,
    outcome: str,
    when: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Final review I1: an uninstalled unit read `completed`. Removal is the
    latest word on it until a later install names it again."""
    _rc, out = _run(monkeypatch, tmp_path, capsys, SCENARIOS[scenario], "--json")
    units = {u["name"]: u for u in parse_one(out)["recorded_units"]}
    assert units["fixture-apt"]["last_outcome"] == outcome
    assert units["fixture-apt"]["last_named"] == when
    assert units["fixture-source"]["last_outcome"] == "completed", "not named by the uninstall"


@pytest.mark.parametrize(
    ("end", "outcome"),
    [
        ({"event": "uninstall_failed", "version": 1, "completed": 0}, "removal failed"),
        (None, "removal interrupted"),
    ],
)
def test_a_removal_that_did_not_finish_says_so(
    end: dict[str, Any] | None,
    outcome: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    entries = [BEGIN, {"event": "transaction_end", "version": 1, "completed": 4}, UNINSTALL_BEGIN]
    if end is not None:
        entries.append(end)
    _rc, out = _run(monkeypatch, tmp_path, capsys, entries, "--json")
    units = {u["name"]: u for u in parse_one(out)["recorded_units"]}
    assert units["fixture-apt"]["last_outcome"] == outcome


def test_an_unreadable_target_is_an_error_document_with_exit_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.distro import DetectionError

    def refuse(cls: type) -> Target:
        raise DetectionError("/etc/os-release declares no ID")

    monkeypatch.setattr(Target, "detect", classmethod(refuse))
    assert cli.main(["--catalog", str(FIXTURE_CATALOG), "status", "--json"]) == 1
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error" and "declares no ID" in doc["message"]
