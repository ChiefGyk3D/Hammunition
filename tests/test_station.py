# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Station-local values, and the deferral that replaced a blocker.

The behaviour under test is D-035's: **a missing station value stops one file
from being written, not the whole transaction.** Before this, any manifest with
a `config_files` block failed resolution outright, so the `packet` profile --
nineteen packages, and the reason the 73Linux delta was acquired at all --
could not be installed by anyone at all.

Two properties matter more than the plumbing and are asserted directly:

* **Nothing is invented.** No default callsign, no placeholder, no CHANGEME. A
  file written with a made-up callsign would transmit it.
* **A partial file is never written.** A config missing one of three values is
  deferred whole, because a file with `{station.callsign}` still in it looks
  configured and is not.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.execute import write_config  # noqa: E402
from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.plan import _plan_config  # noqa: E402
from hammunition.station import (  # noqa: E402
    STATION_FIELDS,
    Station,
    StationError,
    load_station,
    save_station,
)

CATALOG = REPO_ROOT / "catalog" / "packages"


# ---------------------------------------------------------------------------
# The values themselves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "callsign",
    ["M0ABC", "W1AW", "VK2XYZ", "2E0ABC", "W1AW/4", "G0ABC/P", "9A1CMS"],
)
def test_real_callsign_shapes_are_accepted(callsign: str) -> None:
    """Callsign formats vary by country far more than the common regexes
    admit. Rejecting a real callsign is a worse failure than accepting an
    implausible one, because the operator cannot work around it."""
    assert Station(callsign=callsign).callsign == callsign


@pytest.mark.parametrize("bad", ["not a call", "M0 ABC", "", "ABCDEFGHIJK", "M0ABC;rm -rf /"])
def test_unusable_callsigns_are_refused(bad: str) -> None:
    with pytest.raises(StationError, match="callsign"):
        Station(callsign=bad)


def test_callsign_and_locator_are_normalised() -> None:
    station = Station(callsign="m0abc", grid_square="io91WM")
    assert station.callsign == "M0ABC"
    assert station.grid_square == "IO91wm", "Maidenhead convention: upper, digits, lower"


@pytest.mark.parametrize("bad", ["ZZ99", "IO", "IO9", "hello"])
def test_non_locators_are_refused(bad: str) -> None:
    with pytest.raises(StationError, match="grid square"):
        Station(grid_square=bad)


def test_an_empty_station_invents_nothing() -> None:
    """The property that matters most. A default callsign would be transmitted."""
    station = Station()
    assert station.as_dict() == {}
    for field in STATION_FIELDS:
        assert station.get(field) is None, f"{field} was invented"


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def test_an_absent_file_is_not_an_error(tmp_path: Path) -> None:
    """An operator who has never set a callsign is the starting state."""
    assert load_station(tmp_path / "nothing.yml") == Station()


def test_saving_and_loading_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "station.yml"
    save_station(Station(callsign="M0ABC", grid_square="IO91wm"), path)
    assert load_station(path) == Station(callsign="M0ABC", grid_square="IO91wm")


def test_the_file_is_not_world_readable(tmp_path: Path) -> None:
    path = tmp_path / "station.yml"
    save_station(Station(callsign="M0ABC"), path)
    assert path.stat().st_mode & 0o077 == 0, "station values are not for other users"


def test_a_file_naming_unknown_values_is_refused(tmp_path: Path) -> None:
    """Silently ignoring a key is how a typo becomes an unwritten config file
    with no explanation."""
    path = tmp_path / "station.yml"
    path.write_text("callsign: M0ABC\ncallsgin: M0XYZ\n")
    with pytest.raises(StationError, match="callsgin"):
        load_station(path)


# ---------------------------------------------------------------------------
# Deferral rather than blocking — D-035
# ---------------------------------------------------------------------------


def test_a_config_missing_one_value_is_deferred_whole() -> None:
    """Never a partial file: one with `{station.callsign}` still in it looks
    configured and is not."""
    catalog = load_catalog(CATALOG)
    linbpq = catalog["linbpq"]
    assert linbpq.config_files, "this test needs a manifest that templates config"

    writable, deferred = _plan_config(linbpq, Station(callsign="M0ABC"))
    assert not writable, "a file was rendered with values it did not have"
    assert len(deferred) == 1
    assert "grid_square" in deferred[0].why
    assert "callsign" not in deferred[0].why, "the value we DO have should not be listed"


def test_a_complete_station_renders_the_file() -> None:
    catalog = load_catalog(CATALOG)
    station = Station(callsign="M0ABC", grid_square="IO91wm", node_alias="TESTND")
    writable, deferred = _plan_config(catalog["linbpq"], station)
    assert not deferred
    assert len(writable) == 1
    _package, _config, body = writable[0]
    assert "M0ABC" in body and "IO91wm" in body and "TESTND" in body
    assert "{station." not in body, "an unsubstituted reference survived"


def test_a_package_with_no_config_defers_nothing() -> None:
    catalog = load_catalog(CATALOG)
    writable, deferred = _plan_config(catalog["fldigi"], Station())
    assert not writable and not deferred


# ---------------------------------------------------------------------------
# Writing it
# ---------------------------------------------------------------------------


def test_writing_backs_up_what_was_there(tmp_path: Path) -> None:
    """These paths belong to the distribution's packages as often as to us.
    Overwriting a hand-tuned /etc/ax25/axports without a copy is damage no
    transaction log can undo."""
    path = tmp_path / "axports"
    path.write_text("original\n")
    outcome = write_config(path, "replaced", 0o644, append=False, backup=True)

    assert path.read_text() == "replaced\n"
    backup = path.with_suffix(path.suffix + ".hammunition-backup")
    assert backup.read_text() == "original\n"
    assert "saved to" in outcome


def test_a_second_run_does_not_overwrite_the_first_backup(tmp_path: Path) -> None:
    """Idempotent (CLAUDE.md). Re-running must not replace the operator's
    original with our own previous output -- that would destroy the only copy
    on the second run rather than the first."""
    path = tmp_path / "axports"
    path.write_text("original\n")
    write_config(path, "first", 0o644, append=False, backup=True)
    write_config(path, "second", 0o644, append=False, backup=True)

    backup = path.with_suffix(path.suffix + ".hammunition-backup")
    assert backup.read_text() == "original\n"
    assert path.read_text() == "second\n"


def test_appending_adds_rather_than_replaces(tmp_path: Path) -> None:
    """AX.25 appends a port line; replacing the file would drop every other
    port the operator has configured."""
    path = tmp_path / "axports"
    path.write_text("existing port\n")
    write_config(path, "wl2k M0ABC 1200", 0o644, append=True, backup=False)
    assert path.read_text() == "existing port\nwl2k M0ABC 1200\n"


def test_the_written_mode_is_the_declared_mode(tmp_path: Path) -> None:
    path = tmp_path / "conf"
    write_config(path, "x", 0o600, append=False, backup=False)
    assert path.stat().st_mode & 0o777 == 0o600


# ---------------------------------------------------------------------------
# The wiring: a planned config file is actually written by execute()
# ---------------------------------------------------------------------------


def test_a_planned_config_file_is_written_by_a_real_run(tmp_path: Path) -> None:
    """The unit tests above prove `write_config` works. This proves the plan
    reaches it — a plan that promises a file and an executor that never writes
    one would pass every test above and lie to the operator.
    """
    from hammunition.backends import AptBackend, RecordingRunner, SubprocessRunner
    from hammunition.distro import Target
    from hammunition.execute import commands_for, execute
    from hammunition.manifest.schema import PackageManifest
    from hammunition.plan import InstallPlan, PlannedPackage
    from hammunition.state import TransactionLog

    target = tmp_path / "etc" / "node.cfg"
    manifest = PackageManifest.model_validate(
        {
            "name": "configured",
            "version": "1.0",
            "summary": "A package that writes templated configuration",
            "categories": ["packet"],
            "install": [{"install": {"method": "apt", "packages": ["configured"]}}],
            "config_files": [
                {"path": str(target), "template": "CALL={station.callsign}\n", "mode": "0640"}
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for linbpq, which templates a node callsign.",
                "why_you_want_it": "To prove a planned config file is actually written.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )
    writable, deferred = _plan_config(manifest, Station(callsign="M0ABC"))
    assert not deferred and len(writable) == 1

    plan = InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        packages=(
            PlannedPackage(
                manifest=manifest,
                block=manifest.install[0],
                apt_packages=(),
                already_installed=("configured",),
            ),
        ),
        config_files=tuple(writable),
    )
    apt = AptBackend(RecordingRunner())
    steps = [s for s in commands_for(plan, apt) if getattr(s, "kind", None) == "config"]
    assert len(steps) == 1, "the plan's config file produced no step"

    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute(steps, SubprocessRunner(), log=log, plan=plan)

    assert report.ok, report.stderr
    assert target.read_text() == "CALL=M0ABC\n"
    assert target.stat().st_mode & 0o777 == 0o640
    assert any(e["event"] == "action_end" for e in log.read()), "the write was not logged"


def test_a_root_owned_config_becomes_staged_commands_not_an_in_process_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unprivileged engine cannot write /etc in-process — the first Parrot
    VM run proved it with a PermissionError traceback. A root-owned target
    must plan as: stage unprivileged, then `install -m` under sudo, with a
    `cp -a` backup first only when there is something to back up."""
    import os as os_module

    from hammunition.backends import Action, Command
    from hammunition.execute import config_steps
    from hammunition.manifest.schema import ConfigFile

    monkeypatch.setattr(os_module, "access", lambda *_a, **_k: False)

    config = ConfigFile.model_validate(
        {"path": "/etc/hammunition-test.cfg", "template": "CALL={station.callsign}\n", "mode": "0644"}
    )

    class PlanStub:
        config_files: ClassVar[list[tuple[str, ConfigFile, str]]] = [
            ("linbpq", config, "CALL=M0ABC\n")
        ]

    steps = config_steps(PlanStub(), staging_root=tmp_path)  # type: ignore[arg-type]
    kinds = [type(s).__name__ for s in steps]
    assert kinds == ["Action", "Command"], kinds
    action, install = steps
    assert isinstance(action, Action) and action.kind == "config"
    assert isinstance(install, Command)
    assert install.argv[:3] == ("install", "-m", "0644")
    assert install.requires_root

    # Perform the staging half for real: the staged file carries the final
    # contents and never touches the root-owned target.
    outcome = action.perform()
    staged = Path(install.argv[3])
    assert staged.read_text() == "CALL=M0ABC\n"
    assert "staged" in outcome
