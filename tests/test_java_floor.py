# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A unit that needs a Java floor says so, and the plan reads `java -version`.

`default-jre-headless` is a metapackage whose version says nothing about the
Java major: Ubuntu 22.04 and Pop!_OS 22.04 resolve it to Java 11 while
GraphHopper's classes are major 61 (Java 17). The floor is therefore measured
from the `java` the machine has (D-037, amended 2026-10-02), never fetched.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.java import JavaProbe, parse_java_major
from hammunition.plan import PlanError
from test_plan import _manifest, _profile, _resolve

# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "major"),
    [
        ('openjdk version "17.0.12" 2024-07-16\nOpenJDK Runtime Environment', 17),
        ('openjdk version "21" 2023-09-19', 21),
        ('java version "1.8.0_392"', 8),
        ('openjdk version "25-ea" 2025-09-16', 25),
        ('openjdk version "11.0.24" 2024-07-16', 11),
    ],
)
def test_the_parser_reads_the_three_version_line_shapes(line: str, major: int) -> None:
    assert parse_java_major(line) == major


def test_the_parser_skips_a_picked_up_preamble() -> None:
    """With JAVA_TOOL_OPTIONS set, java prints a `Picked up` line first."""
    text = 'Picked up JAVA_TOOL_OPTIONS: -Xmx2g\nopenjdk version "21.0.4" 2024-07-16'
    assert parse_java_major(text) == 21


def test_the_probe_reports_the_version_line_not_the_preamble() -> None:
    out = 'Picked up _JAVA_OPTIONS: -Xmx2g\nopenjdk version "17.0.12" 2024-07-16'
    probe = JavaProbe(path_lookup=lambda _n: "/usr/bin/java", run=lambda _a: out)
    assert probe.major == 17
    assert probe.version_line.startswith("openjdk version")


@pytest.mark.parametrize("text", ["", "command not found", 'version "abc"'])
def test_the_parser_never_guesses(text: str) -> None:
    assert parse_java_major(text) is None


# ---------------------------------------------------------------------------
# The probe: a fake `java` on a fake PATH
# ---------------------------------------------------------------------------


def _fake_java(directory: Path, version_line: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / "java"
    # `java -version` prints on stderr; the fake does too.
    exe.write_text(f"#!/bin/sh\necho '{version_line}' >&2\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def _probe_on(directory: Path) -> JavaProbe:
    def lookup(name: str) -> str | None:
        candidate = directory / name
        return str(candidate) if candidate.exists() and os.access(candidate, os.X_OK) else None

    return JavaProbe(path_lookup=lookup, default_path=str(directory / "nowhere" / "java"))


def test_the_probe_runs_a_real_executable_and_reads_stderr(tmp_path: Path) -> None:
    _fake_java(tmp_path / "bin", 'openjdk version "17.0.12" 2024-07-16')
    probe = _probe_on(tmp_path / "bin")
    assert probe.major == 17
    assert probe.version_line.startswith("openjdk version")


def test_the_probe_runs_java_once(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str]) -> str:
        calls.append(argv)
        return 'openjdk version "21" 2023-09-19'

    probe = JavaProbe(path_lookup=lambda _n: "/usr/bin/java", run=run)
    assert (probe.major, probe.major, probe.version_line) == (
        21,
        21,
        'openjdk version "21" 2023-09-19',
    )
    assert len(calls) == 1


def test_the_probe_falls_back_to_the_default_java_when_path_has_none(tmp_path: Path) -> None:
    exe = _fake_java(tmp_path / "jvm", 'openjdk version "17.0.1" 2021-10-19')
    probe = JavaProbe(path_lookup=lambda _n: None, default_path=str(exe))
    assert probe.major == 17


def test_no_java_anywhere_is_none_with_a_reason(tmp_path: Path) -> None:
    probe = JavaProbe(path_lookup=lambda _n: None, default_path=str(tmp_path / "absent"))
    assert probe.major is None
    assert "no java was found" in probe.reason


# ---------------------------------------------------------------------------
# The schema field
# ---------------------------------------------------------------------------


def test_requires_java_is_a_positive_integer() -> None:
    assert _manifest(requires_java=17).requires_java == 17
    assert _manifest().requires_java is None
    for bad in (0, -1, "17", 17.5):
        with pytest.raises(ValidationError):
            _manifest(requires_java=bad)


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


def _unit(name: str, **overrides: Any) -> Any:
    return _manifest(
        name=name, install=[{"install": {"method": "apt", "packages": [name]}}], **overrides
    )


def _java(tmp_path: Path, version_line: str | None) -> JavaProbe:
    if version_line is None:
        return JavaProbe(path_lookup=lambda _n: None, default_path=str(tmp_path / "absent"))
    _fake_java(tmp_path / "bin", version_line)
    return _probe_on(tmp_path / "bin")


def test_java_11_defers_a_profile_member_with_the_measure_and_the_floor(tmp_path: Path) -> None:
    catalog = {u.name: u for u in (_unit("direwolf"), _unit("graphhopper", requires_java=17))}
    plan = _resolve(
        tmp_path,
        ["nav"],
        catalog=catalog,
        profiles={"nav": _profile(name="nav", packages=["direwolf", "graphhopper"])},
        known={"direwolf": None, "graphhopper": None, "openjdk-21-jre-headless": None},
        java=_java(tmp_path, 'openjdk version "11.0.24" 2024-07-16'),
    )
    assert plan.apt_to_install == ("direwolf",)
    (deferral,) = [d for d in plan.deferrals if d.kind == "package"]
    assert deferral.subject == "graphhopper"
    assert "Java 17 or newer" in deferral.why
    assert "11.0.24" in deferral.why
    # The archive package that would meet it, named from the plan's own sweep.
    assert "openjdk-21-jre-headless" in deferral.remedy
    assert "nothing is fetched" in deferral.remedy


def test_java_21_plans_the_unit(tmp_path: Path) -> None:
    plan = _resolve(
        tmp_path,
        ["graphhopper"],
        catalog={"graphhopper": _unit("graphhopper", requires_java=17)},
        known={"graphhopper": None},
        java=_java(tmp_path, 'openjdk version "21" 2023-09-19'),
    )
    assert plan.apt_to_install == ("graphhopper",)
    assert not plan.deferrals
    assert any("Java 17 or newer" in n for n in plan.notes)


def test_no_java_defers_a_member_whose_depends_installs_none(tmp_path: Path) -> None:
    catalog = {u.name: u for u in (_unit("direwolf"), _unit("graphhopper", requires_java=17))}
    plan = _resolve(
        tmp_path,
        ["nav"],
        catalog=catalog,
        profiles={"nav": _profile(name="nav", packages=["direwolf", "graphhopper"])},
        known={"direwolf": None, "graphhopper": None},
        java=_java(tmp_path, None),
    )
    (deferral,) = [d for d in plan.deferrals if d.kind == "package"]
    assert deferral.subject == "graphhopper"
    assert "no java was found" in deferral.why
    assert "nothing is fetched" in deferral.remedy


def test_a_typed_unit_is_refused_with_the_same_text(tmp_path: Path) -> None:
    with pytest.raises(PlanError) as excinfo:
        _resolve(
            tmp_path,
            ["graphhopper"],
            catalog={"graphhopper": _unit("graphhopper", requires_java=17)},
            known={"graphhopper": None, "openjdk-17-jre-headless": None},
            java=_java(tmp_path, 'openjdk version "11.0.24" 2024-07-16'),
        )
    text = str(excinfo.value)
    assert "graphhopper" in text
    assert "Java 17 or newer" in text and "11.0.24" in text
    assert "openjdk-17-jre-headless" in text


def test_a_concrete_jre_in_depends_meets_the_floor_in_this_transaction(tmp_path: Path) -> None:
    """Java 11 is installed, but the unit's own `depends` installs 21: not
    deferred, and the plan says so."""
    plan = _resolve(
        tmp_path,
        ["graphhopper"],
        catalog={
            "graphhopper": _unit(
                "graphhopper", requires_java=17, depends=["openjdk-21-jre-headless"]
            )
        },
        known={"graphhopper": None, "openjdk-21-jre-headless": None},
        java=_java(tmp_path, 'openjdk version "11.0.24" 2024-07-16'),
    )
    assert not plan.deferrals
    assert "openjdk-21-jre-headless" in plan.apt_to_install
    assert any("installs openjdk-21-jre-headless" in n for n in plan.notes)


def test_a_concrete_jre_below_the_floor_does_not_count(tmp_path: Path) -> None:
    with pytest.raises(PlanError):
        _resolve(
            tmp_path,
            ["graphhopper"],
            catalog={
                "graphhopper": _unit(
                    "graphhopper", requires_java=17, depends=["openjdk-11-jre-headless"]
                )
            },
            known={"graphhopper": None, "openjdk-11-jre-headless": None},
            java=_java(tmp_path, 'openjdk version "11.0.24" 2024-07-16'),
        )


def test_no_java_with_only_a_metapackage_is_disclosed_not_refused(tmp_path: Path) -> None:
    """On a clean machine `default-jre-headless` is how Java arrives, and its
    major is unknowable until it does. Refusing would defer GraphHopper on
    every fresh Debian 13; the plan says what to check instead."""
    plan = _resolve(
        tmp_path,
        ["graphhopper"],
        catalog={
            "graphhopper": _unit("graphhopper", requires_java=17, depends=["default-jre-headless"])
        },
        known={"graphhopper": None, "default-jre-headless": None},
        java=_java(tmp_path, None),
    )
    assert not plan.deferrals
    assert any("java -version" in n for n in plan.notes)


def test_java_11_with_a_metapackage_still_defers(tmp_path: Path) -> None:
    """The reported case: Ubuntu 22.04's default JRE is 11 and is installed."""
    with pytest.raises(PlanError, match="Java 17 or newer"):
        _resolve(
            tmp_path,
            ["graphhopper"],
            catalog={
                "graphhopper": _unit(
                    "graphhopper", requires_java=17, depends=["default-jre-headless"]
                )
            },
            known={"graphhopper": None, "default-jre-headless": None},
            java=_java(tmp_path, 'openjdk version "11.0.24" 2024-07-16'),
        )


def test_a_unit_without_the_field_never_runs_java(tmp_path: Path) -> None:
    class Untouchable(JavaProbe):
        @property
        def major(self) -> int | None:
            raise AssertionError("java consulted for a unit that declares no floor")

    plan = _resolve(tmp_path, ["example"], java=Untouchable())
    assert plan.apt_to_install == ("example",)


def test_an_unread_java_is_disclosed_as_unchecked(tmp_path: Path) -> None:
    plan = _resolve(
        tmp_path,
        ["graphhopper"],
        catalog={"graphhopper": _unit("graphhopper", requires_java=17)},
        known={"graphhopper": None},
        java=None,
    )
    assert plan.apt_to_install == ("graphhopper",)
    assert any("was not read" in n for n in plan.notes)


def test_the_json_plan_carries_the_deferral_in_the_existing_shape(tmp_path: Path) -> None:
    from hammunition.interface.plan import build_install_view

    catalog = {u.name: u for u in (_unit("direwolf"), _unit("graphhopper", requires_java=17))}
    plan = _resolve(
        tmp_path,
        ["nav"],
        catalog=catalog,
        profiles={"nav": _profile(name="nav", packages=["direwolf", "graphhopper"])},
        known={"direwolf": None, "graphhopper": None},
        java=_java(tmp_path, 'openjdk version "11.0.24" 2024-07-16'),
    )
    view = build_install_view(plan, [], euid=1000)
    (entry,) = [d for d in view.deferrals if d.subject == "graphhopper"]
    assert "Java 17" in entry.why and "11.0.24" in entry.why
    assert entry.remedy and entry.what


def test_a_dependent_of_a_java_deferred_unit_carries_the_java_cause(tmp_path: Path) -> None:
    catalog = {
        u.name: u
        for u in (
            _unit("graphhopper", requires_java=17),
            _unit("graphhopper-graph", depends=["graphhopper"]),
            _unit("direwolf"),
        )
    }
    plan = _resolve(
        tmp_path,
        ["nav"],
        catalog=catalog,
        profiles={
            "nav": _profile(name="nav", packages=["graphhopper", "graphhopper-graph", "direwolf"])
        },
        known={
            "direwolf": None,
            "graphhopper": None,
            "graphhopper-graph": None,
            "openjdk-17-jre-headless": None,
        },
        java=_java(tmp_path, 'openjdk version "11.0.24" 2024-07-16'),
    )
    by_name = {d.subject: d for d in plan.deferrals if d.kind == "package"}
    assert set(by_name) == {"graphhopper", "graphhopper-graph"}
    dependent = by_name["graphhopper-graph"]
    assert "Java 17" in dependent.why
    assert "openjdk-17-jre-headless" in dependent.remedy
