# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``install``/``uninstall --dry-run --json`` through main().  D-059."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.apt import AptBackend, AptPackageState, AptSimulation
from hammunition.distro import Target
from hammunition.state import ArtifactRemoval, RemovalPlan
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


def _machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    """A target and an apt that need no real machine, as an unprivileged
    operator `op`; returns the placeholders for the machine paths."""
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    for var in ("XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "op")
    monkeypatch.setattr(AptBackend, "lists_populated", lambda self: True)
    monkeypatch.setattr(
        AptBackend,
        "probe",
        lambda self, pkgs: {
            p: AptPackageState(name=p, installed=None, candidate="1.0") for p in pkgs
        },
    )
    monkeypatch.setattr(
        AptBackend,
        "simulate",
        lambda self, pkgs, *, release=None, no_recommends=False: AptSimulation(
            ok=True, installs={p: frozenset({"stable"}) for p in pkgs}, release=release
        ),
    )
    return {str(tmp_path): "<tmp>", str(FIXTURE_CATALOG): "<catalog>"}


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), *argv])
    return rc, capsys.readouterr().out


def _placeholders(text: str, replacements: dict[str, str]) -> str:
    for real, placeholder in replacements.items():
        text = text.replace(real, placeholder)
    return text


def test_the_install_text_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "install", "--dry-run", "fixture-apt")
    assert rc == 0
    assert_golden_text("install-dry-run", _placeholders(out, paths))


def test_the_install_plan_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.plan import render_plan_view

    paths = _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "install", "--dry-run", "--json", "fixture-apt")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "plan" and doc["outcome"] == "planned"
    validate(doc)
    assert_golden("install-dry-run", doc, paths)
    _rc, text = _run(capsys, "install", "--dry-run", "fixture-apt")
    assert_text_values_in_json(text, doc, render_plan_view, cli.cmd_install)


def test_a_refused_plan_is_a_plan_document_with_every_blocker_and_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "install", "--dry-run", "--json", "no-such-unit")
    doc = parse_one(out)
    assert rc == cli.EXIT_UNPLANNABLE
    assert doc["kind"] == "plan" and doc["outcome"] == "refused"
    assert doc["install"] is None
    assert any(b["subject"] == "no-such-unit" for b in doc["blockers"])
    validate(doc)


def test_a_real_install_is_never_driven_through_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review focus: without --dry-run, --json is refused before resolution,
    so no consent gate, sudo prompt or command can be reached."""
    _machine(monkeypatch, tmp_path)

    def must_not_resolve(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a --json install without --dry-run reached resolution")

    monkeypatch.setattr(cli, "resolve", must_not_resolve)
    for verb in ("install", "uninstall"):
        rc, out = _run(capsys, verb, "--json", "--yes", "fixture-apt")
        doc = parse_one(out)
        assert rc == cli.EXIT_UNPLANNABLE and doc["kind"] == "error"
        assert "never driven through --json" in doc["message"]


def _removal(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = RemovalPlan(
        to_remove={"fixture-apt": ["fixture-apt"]},
        left_foreign={"fixture-station": ["libfixture1"]},
        already_absent={"fixture-source": []},
        artifacts={
            "fixture-source": [
                ArtifactRemoval(
                    kind="binary", path=Path("/usr/local/bin/fixture-source"), basis="log"
                )
            ]
        },
        left_unattributed={"fixture-source": ["/usr/local/share/fixture-source/extra"]},
    )
    monkeypatch.setattr(cli, "plan_removal", lambda *args, **kwargs: plan)


def test_the_uninstall_text_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _machine(monkeypatch, tmp_path)
    _removal(monkeypatch)
    rc, out = _run(capsys, "uninstall", "--dry-run", "fixture-apt")
    assert rc == 0
    assert_golden_text("uninstall-dry-run", _placeholders(out, paths))


def test_the_uninstall_plan_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.plan import render_removal_view

    paths = _machine(monkeypatch, tmp_path)
    _removal(monkeypatch)
    rc, out = _run(capsys, "uninstall", "--dry-run", "--json", "fixture-apt")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "plan" and doc["action"] == "uninstall"
    validate(doc)
    assert_golden("uninstall-dry-run", doc, paths)
    _rc, text = _run(capsys, "uninstall", "--dry-run", "fixture-apt")
    assert_text_values_in_json(text, doc, render_removal_view, cli.cmd_uninstall)


def test_a_refusal_after_resolution_is_a_refused_plan_with_its_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not only PlanError: every exit-2 refusal of `install` is a plan document."""
    _machine(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "navit_config_blocker", lambda plan: "the stock file is missing")
    rc, out = _run(capsys, "install", "--dry-run", "--json", "fixture-apt")
    doc = parse_one(out)
    validate(doc)
    assert rc == cli.EXIT_UNPLANNABLE
    assert doc["outcome"] == "refused" and doc["install"] is None
    assert doc["blockers"] == [
        {"subject": "navit configuration", "reason": "the stock file is missing", "remedy": None}
    ]
