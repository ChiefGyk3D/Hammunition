# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``update --json``.  D-059, D-053."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from hammunition.backends.apt import AptBackend, AptPackageState, AptSimulation
from hammunition.distro import Target
from hammunition.station import Station, save_station
from hammunition.upstream import UpstreamRow
from json_support import (
    FIXTURE_CATALOG,
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13")
LISTS = "last refreshed 2026-09-28 08:00 EDT (`sudo apt-get update` refreshes them; this report does not)"


def _machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A target, apt lists and a probe that need no real machine: fixture-apt
    is installed at 1.0 with 1.1 as the candidate; nothing is built."""
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("SUDO_USER", raising=False)
    # Running as yourself, $XDG_STATE_HOME is yours and is honoured
    # (tests/test_cli.py's test_the_log_ignores_the_operator_when_not_root).
    # Without this, a test run under `unshare -r` (real euid 0) makes
    # `paths.owner_aware_dir` treat the operator as a sudo handoff and read
    # this machine's real transaction log instead of the one under tmp_path.
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(AptBackend, "lists_populated", lambda self: True)
    monkeypatch.setattr(
        AptBackend,
        "probe",
        lambda self, pkgs: {
            p: AptPackageState(name=p, installed="1.0", candidate="1.1") for p in pkgs
        },
    )
    monkeypatch.setattr(
        AptBackend,
        "simulate",
        lambda self, pkgs, *, release=None, no_recommends=False: AptSimulation(
            ok=True, installs={p: frozenset({"stable"}) for p in pkgs}, release=release
        ),
    )
    monkeypatch.setattr(cli, "_apt_lists_note", lambda apt: LISTS)


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), "update", *argv])
    return rc, capsys.readouterr().out


def test_the_text_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "fixture-apt", "fixture-source")
    assert rc == 0
    assert_golden_text("update", out)


def test_the_document_matches_its_golden_and_its_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.update import render

    _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "fixture-apt", "fixture-source", "--json")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "update"
    validate(doc)
    assert_golden("update", doc)
    assert doc["upgrade_command"].endswith("-- fixture-apt")
    _rc, text = _run(capsys, "fixture-apt", "fixture-source")
    assert_text_values_in_json(text, doc, render, cli.cmd_update)


def test_nothing_to_compare_is_still_a_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "--json")
    doc = parse_one(out)
    assert rc == 0 and doc["rows"] == [] and doc["from_log"] is True
    validate(doc)


def test_upstream_rows_are_carried_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _machine(monkeypatch, tmp_path)
    row = UpstreamRow(
        unit="fixture-source",
        method="github_tags",
        catalog="2.1",
        upstream="2.2",
        state="behind upstream",
        detail="2.2 tagged upstream",
    )
    monkeypatch.setattr(cli, "probe_upstream", lambda manifest, **kwargs: row)
    _rc, out = _run(capsys, "fixture-source", "--upstream", "--json")
    doc = parse_one(out)
    validate(doc)
    assert doc["upstream"][0]["upstream"] == "2.2"


def test_the_station_values_never_reach_the_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """update output is pasteable; it keeps the text's rule of saying nothing
    about where the operator is."""
    _machine(monkeypatch, tmp_path)
    save_station(
        Station(callsign="N0TST", grid_square="FN31pr"),
        path=tmp_path / "config" / "hammunition" / "station.yml",
    )
    _rc, out = _run(capsys, "fixture-apt", "fixture-source", "--json")
    assert "N0TST" not in out and "FN31pr" not in out


def test_no_region_name_appears_in_the_document_even_when_regions_are_installed() -> None:
    """#121: the text reports installed map regions by count only, never by
    name (D-057's privacy rule, count-only). The JSON document is built from
    the same rows and must keep it too, with no special case."""
    import json
    from dataclasses import asdict

    from hammunition.interface.update import build_update
    from hammunition.manifest.schema import PackageManifest
    from hammunition.plan import InstallPlan, PlannedPackage
    from hammunition.update import region_snapshots, report

    manifest = PackageManifest.model_validate(
        {
            "name": "osm-regions",
            "version": "1.0",
            "summary": "Fixture",
            "categories": ["navigation"],
            "install": [
                {
                    "install": {
                        "method": "osm-regions",
                        "provider": "geofabrik",
                        "licence": "ODbL-1.0",
                        "licence_url": "https://www.openstreetmap.org/copyright",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}, "strategy": "reinstall"},
            "documentation": {
                "what_it_does": "Stands in for a map-region unit.",
                "why_you_want_it": "To measure the report.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )
    plan = InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )
    snapshots = region_snapshots({"secret-region-name": "260101"}, {})
    rep = report(plan, apt_states={}, present={}, built=(), regions={"osm-regions": snapshots})

    doc = build_update(TARGET, rep, lists_note="x", from_log=False, upstream=None)
    dumped = json.dumps(asdict(doc))
    assert "secret-region-name" not in dumped
    assert "1 region" in dumped
