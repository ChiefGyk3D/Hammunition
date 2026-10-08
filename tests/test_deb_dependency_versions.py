# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A vendor .deb's dependencies are checked by version, not only by name.  #381, Task 13.

Offline, apt cannot fetch what a .deb depends on, so each dependency group must
already be met by an installed package whose version is in the stated range. The
expected orderings below were measured against ``dpkg --compare-versions``
(and 1,500 random pairs agreed with it); the tests do not need dpkg.
"""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from typing import Any

import pytest

from bunker_fixtures import make_context
from hammunition.backends.apt import AptBackend, AptPackageState
from hammunition.backends.base import Action, BackendError, Command, CommandResult
from hammunition.backends.binary import BinaryBackend
from hammunition.fetch import Fetcher, mirror_url
from hammunition.manifest.schema import PackageManifest, RemoteArtifact
from hammunition.payloads import payload_path
from hammunition.plan import (
    DebDependency,
    compare_deb_versions,
    deb_dependency_met,
    parse_deb_dependencies,
    parse_deb_depends,
)
from test_fetch_mirror import Routes

cli = importlib.import_module("hammunition.cli.main")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("1.0", "1.0-1"),
        ("1.0~rc1", "1.0"),
        ("1.0~~", "1.0~"),
        ("1.0-1~bpo12+1", "1.0-1"),
        ("1.0-1", "1.0-2"),
        ("2.0", "1:0.5"),
        ("1.9", "1.10"),
        ("1.0", "1.0+b1"),
        ("1.0", "1.0a"),
        ("1.0", "1.0.1"),
        ("1.2.3-4-4", "1.2.3-4-5"),
        ("1", "a"),
    ],
)
def test_the_first_version_is_older(a: str, b: str) -> None:
    assert compare_deb_versions(a, b) < 0 < compare_deb_versions(b, a)


@pytest.mark.parametrize(
    ("a", "b"),
    [("1.0", "1.00"), ("0:1.0", "1.0"), ("1.0-0", "1.0"), ("2.34-0ubuntu3", "2.34-0ubuntu3")],
)
def test_these_versions_are_equal(a: str, b: str) -> None:
    assert compare_deb_versions(a, b) == 0 == compare_deb_versions(b, a)


@pytest.mark.parametrize(
    ("relation", "installed", "met"),
    [
        (">=", "1.2", True),
        (">=", "1.3", True),
        (">=", "1.1", False),
        (">>", "1.2", False),
        (">>", "1.2.1", True),
        ("<=", "1.2", True),
        ("<=", "1.3", False),
        ("<<", "1.2", False),
        ("<<", "1.1", True),
        ("=", "1.2", True),
        ("=", "1.2-1", False),
        (">=", "1:0.1", True),
    ],
)
def test_each_relation_at_its_boundary(relation: str, installed: str, met: bool) -> None:
    assert deb_dependency_met(DebDependency("libfoo", relation, "1.2"), installed) is met


def test_no_relation_needs_only_the_package_and_not_installed_is_never_met() -> None:
    assert deb_dependency_met(DebDependency("libfoo"), "0.1")
    assert not deb_dependency_met(DebDependency("libfoo"), None)
    assert not deb_dependency_met(DebDependency("libfoo", ">=", "1"), None)


def test_the_parser_keeps_versions_alternatives_and_the_deprecated_spellings() -> None:
    groups = parse_deb_dependencies(
        "libc6 (>= 2.34), libfoo:amd64, a [amd64] | b (<< 2)\n , c (>1), d (<3), e (=1:2.0-1)(,"
    )
    flat = [[d.text() for d in group] for group in groups]
    assert flat[:3] == [["libc6 (>= 2.34)"], ["libfoo"], ["a", "b (<< 2)"]]
    assert flat[3:] == [["c (>> 1)"], ["d (<< 3)"], ["e (= 1:2.0-1)"]]
    assert parse_deb_depends("libc6 (>= 2.34), a | b") == [["libc6"], ["a", "b"]]
    assert parse_deb_dependencies("") == []


# -- the CLI's check over a real .deb field ------------------------------------


class StubApt(AptBackend):
    def __init__(self, installed: dict[str, str]) -> None:
        self.installed = installed

    def probe(self, packages: Any) -> dict[str, AptPackageState]:
        return {
            p: AptPackageState(name=p, installed=self.installed.get(p), candidate="9.0")
            for p in packages
        }


def test_unmet_names_the_group_with_its_version_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli, "_dpkg_depends", lambda path: ", libfoo (>= 1.2), libbar | libbaz (>= 2)"
    )
    old = cli._deb_unmet_file(StubApt({"libfoo": "1.1", "libbaz": "2.0"}), tmp_path / "x.deb")
    assert old == ["libfoo (>= 1.2)"]
    assert cli._deb_unmet_file(StubApt({"libfoo": "1.2", "libbaz": "1.9"}), tmp_path / "x.deb") == [
        "libbar | libbaz (>= 2)"
    ]
    assert (
        cli._deb_unmet_file(StubApt({"libfoo": "1.2", "libbar": "0.1"}), tmp_path / "x.deb") == []
    )


def test_unreadable_dependencies_are_reported_not_assumed_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: Path) -> str:
        raise OSError("not a deb")

    monkeypatch.setattr(cli, "_dpkg_depends", broken)
    got = cli._deb_unmet_file(StubApt({}), tmp_path / "x.deb")
    assert got and "could not be read" in got[0]


# -- the install's own check, after the fetch -----------------------------------

BODY = b"deb bytes"
BUNKER = "http://bunker.invalid"


def perform(step: Action | Command) -> str:
    assert isinstance(step, Action)
    return step.perform()


class NeverRuns:
    def run(self, command: Command) -> CommandResult:
        raise AssertionError(f"ran {command.argv}")


PIN = RemoteArtifact(
    url="https://example.invalid/tool_1.0_amd64.deb", sha256=hashlib.sha256(BODY).hexdigest()
)


def _manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "debunit",
            "version": "1.0",
            "summary": "Fixture for the deb dependency check",
            "categories": ["packet"],
            "install": [
                {
                    "install": {
                        "method": "binary",
                        "artifact": PIN.model_dump(exclude_none=True),
                        "format": "deb",
                        "deb_package": "xunit",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Exists so the deb path has a unit to plan.",
                "why_you_want_it": "You do not; the suite does.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def _deb_steps(
    tmp_path: Path, routes: Routes, *, offline: bool, check: Any, with_context: bool = True
) -> tuple[list[Action | Command], Fetcher]:
    pin = PIN
    manifest = _manifest()
    fetcher = Fetcher(
        tmp_path / "cache",
        transport=routes,
        mirror_transport=routes,
        mirror=BUNKER,
        offline=offline,
    )
    context = make_context(tmp_path / "ctx", [], offline=offline) if with_context else None
    if context is not None and offline:
        # Cached bytes need no Bunker row; the dependency check is what is tested.
        fetcher.path_for(pin).parent.mkdir(parents=True)
        fetcher.path_for(pin).write_bytes(BODY)
    backend = BinaryBackend(
        fetcher=fetcher,
        runner=NeverRuns(),
        build_root=tmp_path / "build",
        prefix=tmp_path / "prefix",
        context=context,
        dependency_check=check,
    )
    return backend.steps(manifest, manifest.install[0]), fetcher


def test_offline_the_install_stops_before_apt_when_a_dependency_is_missing(tmp_path: Path) -> None:
    seen: list[Path] = []

    def check(path: Path) -> list[str]:
        seen.append(path)
        return ["libfoo (>= 1.2)"]

    steps, _ = _deb_steps(tmp_path, Routes({}), offline=True, check=check)
    assert [s.kind for s in steps if isinstance(s, Action)] == [
        "fetch",
        "check-deb-depends",
        "install-deb",
    ]
    perform(steps[0])
    with pytest.raises(BackendError, match=r"lacks: libfoo \(>= 1.2\)\. Nothing was installed"):
        perform(steps[1])
    assert seen and seen[0].read_bytes() == BODY


def test_offline_the_install_goes_on_when_every_dependency_is_met(tmp_path: Path) -> None:
    steps, _ = _deb_steps(tmp_path, Routes({}), offline=True, check=lambda path: [])
    perform(steps[0])
    assert "every dependency is met" in perform(steps[1])


def test_online_apt_resolves_its_own_dependencies_so_there_is_no_check_step(
    tmp_path: Path,
) -> None:
    def check(path: Path) -> list[str]:
        raise AssertionError("an online install was checked for dependencies")

    steps, _ = _deb_steps(tmp_path, Routes({}), offline=False, check=check, with_context=False)
    assert [s.kind for s in steps if isinstance(s, Action)] == ["fetch", "install-deb"]
    online, _ = _deb_steps(tmp_path / "o", Routes({}), offline=False, check=check)
    assert [s.kind for s in online if isinstance(s, Action)] == ["fetch", "install-deb"]


def test_the_check_reads_the_file_the_fetch_wrote_from_the_bunker(tmp_path: Path) -> None:
    from bunker_fixtures import artifact
    from hammunition.payloads import payload_name

    at = mirror_url(BUNKER, payload_path("debunit", PIN))
    seen: list[bytes] = []

    def check(path: Path) -> list[str]:
        seen.append(path.read_bytes())
        return []

    # Not cached: the Bunker must hold it, and the check sees what was fetched.
    context = make_context(tmp_path / "ctx", [artifact("debunit", payload_name(PIN), BODY)])
    routes = Routes({at: BODY})
    fetcher = Fetcher(
        tmp_path / "cache",
        transport=routes,
        mirror_transport=routes,
        mirror=BUNKER,
        offline=True,
    )
    backend = BinaryBackend(
        fetcher=fetcher,
        runner=NeverRuns(),
        build_root=tmp_path / "build",
        prefix=tmp_path / "prefix",
        context=context,
        dependency_check=check,
    )
    manifest = _manifest()
    steps = backend.steps(manifest, manifest.install[0])
    for step in steps[:2]:
        perform(step)
    assert seen == [BODY] and routes.requested == [at]
