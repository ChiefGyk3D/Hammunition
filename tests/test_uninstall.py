# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Uninstall: attribution from the log, honest partition, verified removal.

D-004's promise is narrow and this suite holds it to exactly that narrowness:
remove what Hammunition itself added, leave what it did not, and confirm the
removal happened rather than trusting apt's exit code (D-031).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import BackendError, Command
from hammunition.backends.apt import AptPackageState
from hammunition.distro import Target
from hammunition.execute import run_removal
from hammunition.manifest.schema import PackageManifest, ProfileManifest
from hammunition.state import (
    RemovalError,
    TransactionLog,
    installed_by_hammunition,
    plan_removal,
)

TARGET = Target(distro="parrot", version="7.3", arch="x86_64")


def write_log(tmp_path: Path, entries: list[dict[str, Any]]) -> TransactionLog:
    path = tmp_path / "transactions.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return TransactionLog(path=path)


def command_end(argv: list[str], returncode: int = 0) -> dict[str, Any]:
    return {"event": "command_end", "version": 1, "argv": argv, "returncode": returncode}


def manifest(name: str, packages: list[str] | None = None, method: str = "apt") -> PackageManifest:
    if method == "apt":
        install: dict[str, Any] = {"method": "apt", "packages": packages or [name]}
    else:
        install = {
            "method": "source",
            "source": {"url": "https://example.org/x-1.0.tar.gz", "sha256": "0" * 64},
            "build_system": "make",
        }
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "1.0",
            "summary": "Test unit for the uninstall suite",
            "categories": ["sdr"],
            "install": [{"install": install}],
            "update": {"probe": {"method": "apt_policy"}, "strategy": "apt_upgrade"},
            "documentation": {
                "what_it_does": "Exists so the uninstall suite has a unit to plan against.",
                "why_you_want_it": "You do not; the test does, to hold the partition honest.",
                "prerequisites": "Nothing needs configuring before this test fixture.",
                "known_problems": "None. It never installs anything anywhere.",
                "upstream_url": "https://example.org",
                "upstream_support": "There is no upstream; this is a test fixture.",
            },
        }
    )


# ---------------------------------------------------------------------------
# Attribution: what the log says Hammunition installed
# ---------------------------------------------------------------------------


def test_successful_install_commands_attribute_their_packages(tmp_path: Path) -> None:
    log = write_log(
        tmp_path,
        [
            {"event": "transaction_begin", "version": 1},
            command_end(["apt-get", "install", "--yes", "--", "flrig", "gpsd"]),
        ],
    )
    assert installed_by_hammunition(log) == {"flrig", "gpsd"}


def test_a_failed_apt_command_attributes_nothing(tmp_path: Path) -> None:
    log = write_log(
        tmp_path,
        [command_end(["apt-get", "install", "--yes", "--", "flrig"], returncode=100)],
    )
    assert installed_by_hammunition(log) == frozenset()


def test_a_successful_remove_takes_attribution_away(tmp_path: Path) -> None:
    """Install, remove, reinstall replays to attributed — order matters."""
    log = write_log(
        tmp_path,
        [
            command_end(["apt-get", "install", "--yes", "--", "flrig", "gpsd"]),
            command_end(["apt-get", "remove", "--yes", "--", "flrig"]),
            command_end(["apt-get", "install", "--yes", "--", "flrig"]),
        ],
    )
    assert installed_by_hammunition(log) == {"flrig", "gpsd"}
    log2 = write_log(
        tmp_path,
        [
            command_end(["apt-get", "install", "--yes", "--", "flrig"]),
            command_end(["apt-get", "remove", "--yes", "--", "flrig"]),
        ],
    )
    assert installed_by_hammunition(log2) == frozenset()


def test_non_apt_commands_and_other_events_are_ignored(tmp_path: Path) -> None:
    log = write_log(
        tmp_path,
        [
            command_end(["apt-get", "update"]),
            command_end(["gpasswd", "--add", "user", "dialout"]),
            {"event": "command_begin", "version": 1, "argv": ["apt-get", "install", "--yes", "--", "x"]},
            {"event": "some_future_event", "version": 9},
        ],
    )
    assert installed_by_hammunition(log) == frozenset()


def test_attribution_survives_a_transaction_that_failed_later(tmp_path: Path) -> None:
    """A run that died on command 3 still installed what command 2 installed."""
    log = write_log(
        tmp_path,
        [
            {"event": "transaction_begin", "version": 1},
            command_end(["apt-get", "install", "--yes", "--", "direwolf"]),
            {"event": "transaction_failed", "version": 1, "completed": 1},
        ],
    )
    assert installed_by_hammunition(log) == {"direwolf"}


# ---------------------------------------------------------------------------
# Planning: the partition and the refusals
# ---------------------------------------------------------------------------


def states_for(installed: list[str], absent: list[str]) -> dict[str, AptPackageState]:
    result = {p: AptPackageState(name=p, installed="1.0", candidate="1.0") for p in installed}
    result |= {p: AptPackageState(name=p, installed=None, candidate="1.0") for p in absent}
    return result


def test_the_partition_is_exactly_the_promise() -> None:
    catalog = {
        "ours": manifest("ours"),
        "theirs": manifest("theirs"),
        "gone": manifest("gone"),
    }
    plan = plan_removal(
        ["ours", "theirs", "gone"],
        catalog=catalog,
        profiles={},
        target=TARGET,
        attributed=frozenset({"ours", "gone"}),
        states=states_for(installed=["ours", "theirs"], absent=["gone"]),
    )
    assert plan.to_remove == {"ours": ["ours"]}
    assert plan.left_foreign == {"theirs": ["theirs"]}
    assert plan.already_absent == {"gone": ["gone"]}
    assert plan.apt_packages == ("ours",)


def test_an_unknown_name_is_a_planning_error() -> None:
    with pytest.raises(RemovalError, match="not a package or profile"):
        plan_removal(
            ["nonesuch"],
            catalog={},
            profiles={},
            target=TARGET,
            attributed=frozenset(),
            states={},
        )


def test_a_non_apt_unit_is_refused_with_the_backend_named() -> None:
    catalog = {"built": manifest("built", method="source")}
    with pytest.raises(RemovalError, match="source backend"):
        plan_removal(
            ["built"],
            catalog=catalog,
            profiles={},
            target=TARGET,
            attributed=frozenset(),
            states={},
        )


def test_profiles_expand_to_their_packages() -> None:
    catalog = {"aunit": manifest("aunit"), "bunit": manifest("bunit")}
    profile = ProfileManifest.model_validate(
        {
            "name": "bundle",
            "summary": "Two units, for the profile-expansion test",
            "packages": ["aunit", "bunit"],
            "documentation": {
                "what_it_installs": "Two fixture units, so profile expansion is exercised.",
                "why_together": "They exist only to be uninstalled together in this test.",
                "deliberately_excludes": "Everything real.",
                "manual_configuration": "Nothing at all.",
            },
        }
    )
    plan = plan_removal(
        ["bundle"],
        catalog=catalog,
        profiles={"bundle": profile},
        target=TARGET,
        attributed=frozenset({"aunit", "bunit"}),
        states=states_for(installed=["aunit", "bunit"], absent=[]),
    )
    assert plan.apt_packages == ("aunit", "bunit")


# ---------------------------------------------------------------------------
# Running: logging contract and the D-031 ending
# ---------------------------------------------------------------------------


class FakeRunner:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.ran: list[tuple[str, ...]] = []

    def run(self, command: Command) -> Any:
        self.ran.append(command.argv)

        class Result:
            returncode = self.returncode
            ok = self.returncode == 0
            stderr = "" if self.returncode == 0 else "apt said no"

        return Result()


class FakeProber:
    def __init__(self, still_installed: set[str]) -> None:
        self.still_installed = still_installed

    def probe(self, packages: Any) -> dict[str, AptPackageState]:
        return {
            p: AptPackageState(
                name=p,
                installed="1.0" if p in self.still_installed else None,
                candidate="1.0",
            )
            for p in packages
        }


def removal_plan_for(*packages: str) -> Any:
    from hammunition.state.uninstall import RemovalPlan

    return RemovalPlan(
        to_remove={p: [p] for p in packages}, left_foreign={}, already_absent={}
    )


def remove_command(*packages: str) -> Command:
    return Command(
        argv=("apt-get", "remove", "--yes", "--", *packages),
        description="Remove for test",
        requires_root=True,
    )


def events(log: TransactionLog) -> list[str]:
    return [str(e.get("event")) for e in log.read()]


def test_a_verified_removal_logs_begin_commands_and_a_confirmed_end(tmp_path: Path) -> None:
    log = TransactionLog(path=tmp_path / "t.jsonl")
    report = run_removal(
        [remove_command("flrig")],
        FakeRunner(),
        log=log,
        plan=removal_plan_for("flrig"),
        target=TARGET,
        prober=FakeProber(still_installed=set()),
    )
    assert report.ok and report.verified
    assert events(log) == ["uninstall_begin", "command_begin", "command_end", "uninstall_end"]
    end = list(log.read())[-1]
    assert end["verified"] is True
    assert end["checks"][0]["kind"] == "package_removed"


def test_a_package_apt_kept_makes_the_removal_unverified(tmp_path: Path) -> None:
    """apt-get remove exited 0 but the package is still there: verified false,
    with the still-installed version in the check detail."""
    log = TransactionLog(path=tmp_path / "t.jsonl")
    report = run_removal(
        [remove_command("flrig")],
        FakeRunner(),
        log=log,
        plan=removal_plan_for("flrig"),
        target=TARGET,
        prober=FakeProber(still_installed={"flrig"}),
    )
    assert report.ok and not report.verified
    end = list(log.read())[-1]
    assert end["verified"] is False
    assert "still installed" in end["checks"][0]["detail"]


def test_a_failing_command_writes_uninstall_failed_and_stops(tmp_path: Path) -> None:
    log = TransactionLog(path=tmp_path / "t.jsonl")
    report = run_removal(
        [remove_command("flrig")],
        FakeRunner(returncode=100),
        log=log,
        plan=removal_plan_for("flrig"),
        target=TARGET,
        prober=FakeProber(still_installed={"flrig"}),
    )
    assert not report.ok
    assert events(log)[-1] == "uninstall_failed"


def test_a_missing_binary_is_a_failure_not_a_crash(tmp_path: Path) -> None:
    class NoSudoRunner:
        def run(self, command: Command) -> Any:
            raise BackendError("sudo: not found")

    log = TransactionLog(path=tmp_path / "t.jsonl")
    report = run_removal(
        [remove_command("flrig")],
        NoSudoRunner(),
        log=log,
        plan=removal_plan_for("flrig"),
        target=TARGET,
    )
    assert not report.ok
    assert events(log)[-1] == "uninstall_failed"


# ---------------------------------------------------------------------------
# The loop closes: an uninstall's own log entry feeds the next attribution
# ---------------------------------------------------------------------------


def test_uninstall_then_attribution_reports_the_package_gone(tmp_path: Path) -> None:
    log = TransactionLog(path=tmp_path / "t.jsonl")
    log.append({"event": "command_end", "argv": ["apt-get", "install", "--yes", "--", "flrig"], "returncode": 0})
    assert installed_by_hammunition(log) == {"flrig"}
    run_removal(
        [remove_command("flrig")],
        FakeRunner(),
        log=log,
        plan=removal_plan_for("flrig"),
        target=TARGET,
        prober=FakeProber(still_installed=set()),
    )
    assert installed_by_hammunition(log) == frozenset()
