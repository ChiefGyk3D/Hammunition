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
from hammunition.manifest.schema import PackageManifest  # noqa: E402
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


def test_documented_placeholder_callsign_is_accepted() -> None:
    assert Station(callsign="N0CALL").callsign == "N0CALL"


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
# Map regions and freshness — offline map data, not a template variable
# ---------------------------------------------------------------------------


def test_map_regions_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "station.yaml"
    save_station(
        Station(
            map_regions=("north-america/us/vermont", "north-america/us/new-hampshire"),
            map_freshness="monthly",
        ),
        path,
    )
    loaded = load_station(path)
    assert loaded.map_regions == ("north-america/us/vermont", "north-america/us/new-hampshire")
    assert loaded.freshness == "monthly"


def test_freshness_defaults_to_yearly() -> None:
    assert Station().freshness == "yearly"


@pytest.mark.parametrize(
    "bad", ["North-America/us", "north-america/../etc", "us vermont", "a//b", ""]
)
def test_a_region_that_is_not_a_geofabrik_path_is_refused(bad: str) -> None:
    with pytest.raises(StationError):
        Station(map_regions=(bad,))


def test_an_unknown_freshness_is_refused() -> None:
    with pytest.raises(StationError):
        Station(map_freshness="daily")


def test_template_variables_are_unchanged_by_map_fields() -> None:
    # M0ABC exercises this map-field property; the documented placeholder is
    # checked separately by test_documented_placeholder_callsign_is_accepted.
    s = Station(callsign="M0ABC", map_regions=("north-america/us/vermont",))
    assert s.get("callsign") == "M0ABC"
    assert "map_regions" not in s.as_dict() or isinstance(s.as_dict()["map_regions"], list)


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


# ---------------------------------------------------------------------------
# Derived variables: computed from a stored value, never stored or invented
# ---------------------------------------------------------------------------


def test_a_position_is_derived_from_the_grid_square() -> None:
    station = Station(grid_square="FN31pr")
    assert station.get("latitude") == "41.7292"
    assert station.get("longitude") == "-72.7083"


def test_a_derived_variable_asks_for_the_value_it_comes_from() -> None:
    """`station set --latitude` does not exist; the prompt and the deferral's
    remedy must name what the operator can actually set."""
    assert Station().missing({"latitude", "longitude"}) == ("grid_square",)
    assert Station().missing({"ax25_callsign"}) == ("callsign",)
    assert Station(grid_square="FN31pr").missing({"latitude", "callsign"}) == ("callsign",)


@pytest.mark.parametrize("callsign", ["N0TST", "M0ABC", "2E0ABC", "9A1CMS"])
def test_an_ax25_callsign_is_the_callsign_when_ax25_can_carry_it(callsign: str) -> None:
    station = Station(callsign=callsign)
    assert station.get("ax25_callsign") == callsign
    assert station.unusable({"ax25_callsign"}) == ()


@pytest.mark.parametrize("callsign", ["W1AW/4", "G0ABC/P", "3DA0ABC"])
def test_a_callsign_ax25_cannot_carry_is_unusable_not_trimmed(callsign: str) -> None:
    """Trimming `/P` or a seventh character would be inventing a station
    identity (D-035). The value is set, so it is not *missing*; it is unusable,
    and says why."""
    station = Station(callsign=callsign)
    assert station.get("ax25_callsign") is None
    assert station.missing({"ax25_callsign"}) == ()
    (reason,) = station.unusable({"ax25_callsign"})
    assert callsign in reason and "AX.25" in reason


def _templating(template: str, path: str = "/etc/fixture.conf") -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "fixture",
            "version": "1.0",
            "summary": "A package that templates station values",
            "categories": ["packet"],
            "install": [{"install": {"method": "apt", "packages": ["fixture"]}}],
            "config_files": [{"path": path, "template": template}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for a unit that templates station values.",
                "why_you_want_it": "To exercise the planner's deferral.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def test_an_unusable_value_defers_the_file_with_the_reason() -> None:
    manifest = _templating("MYCALL {station.ax25_callsign}\n")
    writable, deferred = _plan_config(manifest, Station(callsign="W1AW/4"))
    assert not writable
    (deferral,) = deferred
    assert "W1AW/4" in deferral.why and "AX.25" in deferral.why
    assert "station set" not in deferral.remedy, "setting the value again cannot help"


def test_every_template_names_a_known_variable() -> None:
    """A typo in `{station.calsign}` would otherwise defer the file forever
    with a remedy nobody can follow."""
    from hammunition.station import TEMPLATE_VARIABLES

    catalog = load_catalog(CATALOG)
    for name, manifest in catalog.items():
        unknown = manifest.station_variables - TEMPLATE_VARIABLES
        assert not unknown, f"{name} templates unknown station values: {sorted(unknown)}"


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
        {
            "path": "/etc/hammunition-test.cfg",
            "template": "CALL={station.callsign}\n",
            "mode": "0644",
        }
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


def test_a_root_owned_config_in_a_missing_directory_makes_the_directory_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`install -m` writes a file, never its directory. A systemd drop-in
    (`/etc/systemd/system/gpsd.service.d/...`, the chrony unit's) lands in a
    directory nothing has created, so the plan makes it first -- a printed,
    root step, and only when the directory is missing at plan time."""
    import os as os_module

    from hammunition.backends import Command
    from hammunition.execute import config_steps
    from hammunition.manifest.schema import ConfigFile

    monkeypatch.setattr(os_module, "access", lambda *_a, **_k: False)
    missing = tmp_path / "etc" / "systemd" / "system" / "gpsd.service.d"
    present = tmp_path / "etc-present"
    present.mkdir()

    def commands_for_path(path: Path) -> list[Command]:
        config = ConfigFile.model_validate(
            {"path": str(path), "template": "[Service]\n", "mode": "0644"}
        )

        class PlanStub:
            config_files: ClassVar[list[tuple[str, ConfigFile, str]]] = [
                ("chrony", config, "[Service]\n")
            ]

        steps = config_steps(PlanStub(), staging_root=tmp_path)  # type: ignore[arg-type]
        return [s for s in steps if isinstance(s, Command)]

    commands = commands_for_path(missing / "hammunition-gps.conf")
    assert [c.argv[0] for c in commands] == ["mkdir", "install"], commands
    assert commands[0].argv == ("mkdir", "-p", "-m", "0755", str(missing))
    assert commands[0].requires_root

    commands = commands_for_path(present / "x.conf")
    assert [c.argv[0] for c in commands] == ["install"], "an existing directory is not made again"


# ---------------------------------------------------------------------------
# The rig station values.  D-073 §4
# ---------------------------------------------------------------------------

_BY_ID = "/dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0"


def test_rig_values_round_trip(tmp_path: Path) -> None:
    from hammunition.station import Station, load_station, save_station

    path = tmp_path / "station.yml"
    save_station(
        Station(rig="yaesu-ft-991a", rig_device=_BY_ID, rig_baud=38400, rig_owner="rigctld"),
        path=path,
    )
    back = load_station(path=path)
    assert back.rig == "yaesu-ft-991a"
    assert back.rig_device == _BY_ID
    assert back.rig_baud == 38400
    assert back.rig_owner == "rigctld"


def test_rig_device_rejects_dot_dot() -> None:
    from hammunition.station import Station, StationError

    with pytest.raises(StationError):
        Station(rig_device="/dev/../etc/passwd")


def test_rig_device_rejects_shell_metacharacters() -> None:
    from hammunition.station import Station, StationError

    for bad in ("/dev/tty;reboot", "/dev/tty USB0", "/dev/$(tty)", "/dev/tty%s"):
        with pytest.raises(StationError):
            Station(rig_device=bad)


def test_rig_device_must_be_under_dev() -> None:
    from hammunition.station import Station, StationError

    with pytest.raises(StationError):
        Station(rig_device="/home/op/ttyUSB0")


def test_rig_ptt_line_is_an_enum() -> None:
    from hammunition.station import Station, StationError

    assert Station(rig_ptt_line="rts").rig_ptt_line == "rts"
    assert Station(rig_ptt_line="vox").rig_ptt_line == "vox"
    with pytest.raises(StationError):
        Station(rig_ptt_line="cat")


def test_rig_owner_is_an_enum() -> None:
    from hammunition.station import Station, StationError

    assert Station(rig_owner="flrig").rig_owner == "flrig"
    with pytest.raises(StationError):
        Station(rig_owner="hamlib")


def test_rig_accepts_a_hamlib_model_value() -> None:
    from hammunition.station import Station

    assert Station(rig="hamlib:3073").rig == "hamlib:3073"


def test_rig_fields_are_template_variables() -> None:
    from hammunition.station import STATION_FIELDS

    assert {"rig", "rig_device", "rig_baud", "rig_ptt_line", "rig_owner"} <= STATION_FIELDS
