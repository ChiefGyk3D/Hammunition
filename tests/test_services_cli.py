# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`hammunition services`: the helper's service list, and start/stop/enable/disable.
D-056 amended 2026-10-02, D-059.

The engine never runs systemctl: every test's fake runner is keyed by the
helper's argv, and one test fails if any other program is asked for.
"""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.base import Command, CommandResult
from hammunition.interface.services import (
    ServicesError,
    parse_helper_services,
    render_services,
)
from json_support import (
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

DOC: dict[str, Any] = {
    "kind": "services",
    "version": 1,
    "services": [
        {
            "name": "gps-tether",
            "unit": "hammunition-gps-tether.service",
            "scope": "user",
            "description": "GPS position for QMapShack and the browser map on 127.0.0.1",
            "active": "active",
            "enabled": "enabled",
            "root": False,
        },
        {
            "name": "gpsd",
            "unit": "gpsd.socket",
            "scope": "system",
            "description": "the GPS daemon (socket-activated)",
            "active": "active",
            "enabled": "enabled",
            "root": True,
        },
        {
            "name": "time",
            "unit": "ntpsec.service",
            "scope": "system",
            "description": "the clock",
            "active": "inactive",
            "enabled": "disabled",
            "root": True,
        },
        {
            "name": "gps-resume",
            "unit": "hammunition-gps-resume.service",
            "scope": "system",
            "description": "re-adds the receiver to gpsd after sleep",
            "active": "inactive",
            "enabled": "not-found",
            "root": True,
        },
    ],
    "linger": {"state": "off", "ours": False},
}


class _Helper:
    """A fake runner: answers the helper's argv, records everything asked."""

    def __init__(self, doc: dict[str, Any] | None = None, *, rc: int = 0, stderr: str = "") -> None:
        self.doc = copy.deepcopy(doc if doc is not None else DOC)
        self.rc = rc
        self.stderr = stderr
        self.ran: list[Command] = []
        self.act_rc = 0

    def run(self, command: Command) -> CommandResult:
        self.ran.append(command)
        argv = tuple(command.argv)
        if argv[0] == "pkexec":
            argv = argv[1:]
        assert argv[0].endswith("hammunition-devctl"), f"the engine ran {argv[0]!r}"
        if argv[1:] == ("services", "state"):
            if self.rc != 0:
                return CommandResult(
                    argv=command.argv, returncode=self.rc, stdout="", stderr=self.stderr
                )
            return CommandResult(
                argv=command.argv, returncode=0, stdout=json.dumps(self.doc), stderr=""
            )
        if argv[1] == "services" and argv[2] in ("start", "stop", "enable", "disable"):
            if self.act_rc == 0:
                row = next(r for r in self.doc["services"] if r["name"] == argv[3])
                if argv[2] == "start":
                    row["active"] = "active"
                elif argv[2] == "stop":
                    row["active"] = "inactive"
                elif argv[2] == "enable":
                    row["enabled"] = "enabled"
                else:
                    row["enabled"] = "disabled"
            return CommandResult(
                argv=command.argv, returncode=self.act_rc, stdout="", stderr="boom"
            )
        raise AssertionError(f"unexpected helper call: {argv}")


@pytest.fixture
def helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Helper:
    path = tmp_path / "hammunition-devctl"
    path.write_text("#!/bin/sh\n")
    monkeypatch.setattr(cli, "HELPER_PATH", str(path))
    monkeypatch.setattr(
        cli.shutil, "which", lambda name: "/usr/bin/pkexec" if name == "pkexec" else None
    )
    fake = _Helper()
    monkeypatch.setattr(cli, "SubprocessRunner", lambda *a, **k: fake)
    return fake


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    rc = cli.main(list(argv))
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


# -- the document ------------------------------------------------------------------


def test_the_helpers_document_is_parsed_whole() -> None:
    doc = parse_helper_services(json.dumps(DOC))
    assert doc.version == 1
    assert [s.name for s in doc.services] == ["gps-tether", "gpsd", "time", "gps-resume"]
    gpsd = doc.services[1]
    assert (gpsd.unit, gpsd.scope, gpsd.active, gpsd.enabled, gpsd.root) == (
        "gpsd.socket",
        "system",
        "active",
        "enabled",
        True,
    )
    assert doc.linger is not None and doc.linger.state == "off" and doc.linger.ours is False


def test_linger_is_optional_in_the_helpers_document() -> None:
    body = copy.deepcopy(DOC)
    del body["linger"]
    assert parse_helper_services(json.dumps(body)).linger is None


def test_a_field_the_helper_adds_later_is_ignored_not_fatal() -> None:
    body = copy.deepcopy(DOC)
    body["services"][0]["pid"] = 42
    body["extra"] = True
    assert len(parse_helper_services(json.dumps(body)).services) == 4


@pytest.mark.parametrize(
    "mutate, why",
    [
        (lambda d: d.update(kind="radios"), "kind"),
        (lambda d: d.update(version=2), "version"),
        (lambda d: d.update(version="1"), "version"),
        (lambda d: d.update(services="none"), "services"),
        (lambda d: d["services"][0].pop("unit"), "unit"),
        (lambda d: d["services"][0].update(root="yes"), "root"),
        (lambda d: d["services"].append(d["services"][0]), "twice"),
    ],
)
def test_a_malformed_document_is_refused_by_name(mutate: Any, why: str) -> None:
    body = copy.deepcopy(DOC)
    mutate(body)
    with pytest.raises(ServicesError, match=why):
        parse_helper_services(json.dumps(body))


def test_text_that_is_not_json_is_refused() -> None:
    with pytest.raises(ServicesError, match="not JSON"):
        parse_helper_services("Traceback (most recent call last)")
    with pytest.raises(ServicesError, match="object"):
        parse_helper_services("[]")


# -- hammunition services [--json] ----------------------------------------------------


def test_services_text_is_unchanged(helper: _Helper, capsys: pytest.CaptureFixture[str]) -> None:
    rc, out, _ = _run(capsys, "services")
    assert rc == 0
    assert_golden_text("services", out)


def test_services_json_matches_its_golden_and_its_schema(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, _ = _run(capsys, "services", "--json")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "services"
    validate(doc)
    assert_golden("services", doc)


def test_services_text_values_are_in_the_json(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    _rc, text, _ = _run(capsys, "services")
    _rc, out, _ = _run(capsys, "services", "--json")
    from hammunition.interface.services import _boot

    assert_text_values_in_json(text, parse_one(out), render_services, _boot)


def test_services_reads_with_the_helper_and_never_asks_for_a_password(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(capsys, "services")
    assert [c.argv[1:] for c in helper.ran] == [("services", "state")]
    assert helper.ran[0].argv[0] == cli.HELPER_PATH  # not pkexec


def test_a_not_installed_unit_reads_not_installed_in_the_text(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    _rc, out, _ = _run(capsys, "services")
    line = next(ln for ln in out.splitlines() if ln.startswith("gps-resume"))
    assert "not installed" in line


def test_without_the_helper_services_says_what_installs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "HELPER_PATH", str(tmp_path / "absent"))
    rc, _out, err = _run(capsys, "services")
    assert rc == cli.EXIT_UNPLANNABLE
    assert "not installed" in err and "hammunition-tray" in err


def test_a_helper_with_no_services_verb_says_to_update_the_tray(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    helper.rc, helper.stderr = 2, "hammunition-devctl: error: invalid choice: 'services'"
    rc, _out, err = _run(capsys, "services")
    assert rc == cli.EXIT_UNPLANNABLE
    assert "no `services` verb" in err and "update hammunition-tray" in err


def test_a_helper_that_prints_rubbish_is_an_error_document_under_json(
    helper: _Helper, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Garbage(_Helper):
        def run(self, command: Command) -> CommandResult:
            return CommandResult(argv=command.argv, returncode=0, stdout="oops", stderr="")

    monkeypatch.setattr(cli, "SubprocessRunner", lambda *a, **k: Garbage())
    rc, out, _ = _run(capsys, "services", "--json")
    doc = parse_one(out)
    assert rc == cli.EXIT_FAILED and doc["kind"] == "error"


# -- start | stop | enable | disable -----------------------------------------------------


def test_a_system_service_goes_through_pkexec(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, _ = _run(capsys, "services", "start", "time")
    assert rc == 0
    call = helper.ran[1]
    assert call.argv == ("pkexec", cli.HELPER_PATH, "services", "start", "time")
    assert "ntpsec.service" in out and "verified" in out.lower()


def test_a_user_service_never_asks_for_a_password(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    helper.doc["services"][0]["active"] = "inactive"
    rc, _out, _ = _run(capsys, "services", "start", "gps-tether")
    assert rc == 0
    assert helper.ran[1].argv == (cli.HELPER_PATH, "services", "start", "gps-tether")


@pytest.mark.parametrize(
    "verb, name, field, before, after",
    [
        ("start", "time", "active", "inactive", "active"),
        ("stop", "gpsd", "active", "active", "inactive"),
        ("enable", "time", "enabled", "disabled", "enabled"),
        ("disable", "gpsd", "enabled", "enabled", "disabled"),
    ],
)
def test_each_verb_runs_once_and_reads_the_effect_back(
    helper: _Helper,
    capsys: pytest.CaptureFixture[str],
    verb: str,
    name: str,
    field: str,
    before: str,
    after: str,
) -> None:
    row = next(r for r in helper.doc["services"] if r["name"] == name)
    row[field] = before
    rc, _out, _ = _run(capsys, "services", verb, name)
    assert rc == 0
    acts = [c for c in helper.ran if verb in c.argv]
    assert len(acts) == 1
    assert [c.argv[-2:] for c in helper.ran if c.argv[-2:] == ("services", "state")]  # read after


def test_a_service_already_where_asked_is_left_alone(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, _ = _run(capsys, "services", "start", "gpsd")
    assert rc == 0
    assert "already" in out.lower()
    assert all("start" not in c.argv for c in helper.ran)


def test_an_unknown_name_is_refused_by_name_before_any_prompt(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, _out, err = _run(capsys, "services", "start", "sshd")
    assert rc == cli.EXIT_UNPLANNABLE
    assert "'sshd'" in err and "gpsd" in err and "gps-tether" in err
    assert all("start" not in c.argv for c in helper.ran)


def test_a_not_installed_unit_is_refused_not_started(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, _out, err = _run(capsys, "services", "start", "gps-resume")
    assert rc == cli.EXIT_UNPLANNABLE
    assert "not installed" in err
    assert all("start" not in c.argv for c in helper.ran)


def test_dry_run_prints_the_call_and_runs_nothing(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, _ = _run(capsys, "services", "start", "time", "--dry-run")
    assert rc == 0
    assert "Dry run" in out and "pkexec" in out
    assert all("start" not in c.argv for c in helper.ran)


def test_a_dismissed_prompt_changes_nothing(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    helper.act_rc = 126
    rc, _out, err = _run(capsys, "services", "start", "time")
    assert rc == cli.EXIT_CONSENT
    assert "nothing was changed" in err.lower()


def test_a_start_that_ends_failed_is_reported_unverified(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    real = helper.run

    def failing(command: Command) -> CommandResult:
        result = real(command)
        if "start" in command.argv:
            next(r for r in helper.doc["services"] if r["name"] == "time")["active"] = "failed"
        return result

    helper.run = failing  # type: ignore[method-assign]
    rc, _out, err = _run(capsys, "services", "start", "time")
    assert rc == cli.EXIT_FAILED
    assert "failed" in err and "journalctl" in err


def test_a_start_that_ends_inactive_is_a_note_for_a_one_shot_unit(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    helper.doc["services"][3]["enabled"] = "enabled"
    real = helper.run

    def oneshot(command: Command) -> CommandResult:
        result = real(command)
        if "start" in command.argv:
            next(r for r in helper.doc["services"] if r["name"] == "gps-resume")["active"] = (
                "inactive"
            )
        return result

    helper.run = oneshot  # type: ignore[method-assign]
    rc, out, _ = _run(capsys, "services", "start", "gps-resume")
    assert rc == 0
    assert "inactive" in out and "one-shot" in out


def test_a_helper_failure_is_reported_with_its_message(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    helper.act_rc = 1
    rc, _out, err = _run(capsys, "services", "start", "time")
    assert rc == cli.EXIT_FAILED and "boom" in err


def test_the_action_verbs_have_no_json_form(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, _ = _run(capsys, "services", "start", "time", "--json")
    assert parse_one(out)["kind"] == "error" and rc != 0
    assert all("start" not in c.argv for c in helper.ran)


def test_the_engine_never_runs_systemctl(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    for argv in (
        ("services",),
        ("services", "start", "time"),
        ("services", "stop", "gpsd"),
        ("services", "enable", "time"),
        ("services", "disable", "gpsd"),
    ):
        _run(capsys, *argv)
    for command in helper.ran:
        assert "systemctl" not in command.argv
    source = Path(str(cli.__file__)).read_text()
    start = source.index("def cmd_services(")
    end = source.index("\n# ----", start)
    # prose may say the engine never runs it; an argv or a call may not name it
    assert '"systemctl"' not in source[start:end]
    assert "'systemctl'" not in source[start:end]


def test_a_user_service_exit_127_is_not_called_a_dismissed_prompt(
    helper: _Helper, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review M5: 126/127 mean a dismissed pkexec prompt only through pkexec; a
    user-scope call has no prompt, and 127 there is a missing interpreter."""
    helper.doc["services"][0]["active"] = "inactive"
    helper.act_rc = 127
    rc, _out, err = _run(capsys, "services", "start", "gps-tether")
    assert rc == cli.EXIT_FAILED
    assert "dismissed" not in err and "boom" in err
