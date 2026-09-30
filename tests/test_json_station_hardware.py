# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``station show --json`` and ``hardware state --json``.  D-059.

`hardware state` carries real `kept` and `attached` rather than the
placeholders the original plan (Task 5) sketched before PR #119 (kept-off,
D-056) merged to `main`: that PR's `cmd_hardware_state` already reads
`read_kept()` and splits attached devices from kept-but-absent ones, so this
file builds the document from that split directly -- the work planned as a
follow-up task (Task 10) once #119 landed.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path

import pytest

from hammunition.hardware.power import KeptEntry, Parkable
from hammunition.interface.station import StationDocument
from hammunition.station import STATION_FIELDS, Station, save_station
from json_support import (
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

GPS = Parkable(
    name="gps-receiver",
    summary="USB GNSS receivers",
    method="usb_deauthorize",
    quiet=(),
    sysfs_path="/sys/bus/usb/devices/1-4",
    identifier="1234:5678",
    parked=True,
)


def _station(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    station: Station | None,
    *flags: str,
) -> tuple[int, str]:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "op")
    if station is not None:
        save_station(station, path=tmp_path / "hammunition" / "station.yml")
    rc = cli.main(["station", "show", *flags])
    return rc, capsys.readouterr().out.replace(str(tmp_path), "<config>")


STATIONS = {
    "station-none": None,
    "station-set": Station(callsign="N0TST", grid_square="FN31pr"),
    # Synthetic region paths -- shaped like a Geofabrik path (D-035 §"region")
    # but naming nowhere real -- so the golden can carry them safely. The
    # privacy split is that `station show` shows only a count and never a
    # name, while `--json` carries the names for a local front end (D-059
    # spec §6); `test_map_regions_are_in_the_json_but_never_named_in_the_text`
    # below asserts it directly.
    "station-regions": Station(
        map_regions=("atlantis/oceania", "narnia/cair-paravel"), map_freshness="monthly"
    ),
    # D-065: book ids are named in the text as well as the document.
    "station-books": Station(reference_books=("ham.stackexchange.com_en_all",)),
}


@pytest.mark.parametrize("name", sorted(STATIONS))
def test_station_text_is_unchanged(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _station(monkeypatch, tmp_path, capsys, STATIONS[name])
    assert rc == 0
    assert_golden_text(name, out)


@pytest.mark.parametrize("name", sorted(STATIONS))
def test_station_document_matches_its_golden_and_its_schema(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _station(monkeypatch, tmp_path, capsys, STATIONS[name], "--json")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "station"
    validate(doc)
    assert_golden(name, doc, {str(tmp_path): "<config>"})


@pytest.mark.parametrize("name", sorted(STATIONS))
def test_station_text_values_are_in_the_json(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.station import render_station

    _rc, text = _station(monkeypatch, tmp_path, capsys, STATIONS[name])
    _rc, out = _station(monkeypatch, tmp_path, capsys, STATIONS[name], "--json")
    assert_text_values_in_json(text, parse_one(out), render_station)


def test_every_station_field_is_in_the_document() -> None:
    """When a station field is added (map regions, D-057) the document must
    carry it, or the form a front end fills from it silently lacks one."""
    carried = {f.name for f in dataclasses.fields(StationDocument)}
    assert set(STATION_FIELDS) <= carried, sorted(set(STATION_FIELDS) - carried)


def test_map_regions_are_in_the_json_but_never_named_in_the_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The privacy split this task introduced (spec §6): `--json` carries the
    region names for a local front end to fill a form from; the terminal,
    the kind of thing that gets pasted into an issue, shows only a count.
    Nothing in the suite asserted this directly until now -- a regression
    that printed a name in the text, or dropped `map_regions` from the JSON,
    would have passed every other test here."""
    station = STATIONS["station-regions"]
    assert station is not None and station.map_regions  # the fixture, not a stub

    rc, text = _station(monkeypatch, tmp_path, capsys, station)
    assert rc == 0
    rc, out = _station(monkeypatch, tmp_path, capsys, station, "--json")
    assert rc == 0
    doc = parse_one(out)

    assert doc["map_regions"] == list(station.map_regions)
    for region in station.map_regions:
        assert region in out, f"{region!r} missing from --json"
        assert region not in text, f"{region!r} leaked into the text form"


def _hardware(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    found: list[Parkable],
    *flags: str,
    kept: list[KeptEntry] | None = None,
) -> tuple[int, str]:
    from hammunition.hardware import power

    skipped = [("fixture-radio", "its port has no power control")]
    monkeypatch.setattr(cli, "_survey_parkables", lambda args: (found, skipped))
    monkeypatch.setattr(power, "read_kept", lambda: kept or [])
    rc = cli.main(["hardware", "state", *flags])
    return rc, capsys.readouterr().out


# A kept entry for a device that is not attached: same name/identifier as
# GPS, a different port, so `hardware-kept-absent` exercises the "kept
# parked, not attached" branch neither of the other two scenarios reaches.
KEPT_ABSENT = KeptEntry(name="gps-receiver", address="1-9", vendor="1234", product="5678")

HARDWARE: dict[str, tuple[list[Parkable], list[KeptEntry] | None]] = {
    "hardware-one": ([GPS], None),
    "hardware-none": ([], None),
    "hardware-kept-absent": ([], [KEPT_ABSENT]),
}


@pytest.mark.parametrize("name", sorted(HARDWARE))
def test_hardware_text_is_unchanged(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    found, kept = HARDWARE[name]
    rc, out = _hardware(monkeypatch, capsys, found, kept=kept)
    assert rc == 0
    assert_golden_text(name, out)


@pytest.mark.parametrize("name", sorted(HARDWARE))
def test_hardware_document_matches_its_golden_and_its_schema(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.hardware import render_hardware

    found, kept = HARDWARE[name]
    rc, out = _hardware(monkeypatch, capsys, found, "--json", kept=kept)
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "hardware"
    validate(doc)
    assert_golden(name, doc)
    _rc, text = _hardware(monkeypatch, capsys, found, kept=kept)
    # The kept-but-absent row renders "NAME@ADDRESS" (D-056 text); the
    # shared checker splits tokens at `@`, so name and address are checked
    # as the two fields the JSON carries them in.
    assert_text_values_in_json(text, doc, render_hardware)


def test_a_device_carries_every_key_and_value_the_helper_prints(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The helper's `state` array is what the tray reads; a front end reading
    the CLI must get the same rows, value for value, not merely the same
    keys (I1: the helper is the source of truth). Three cases in one fixture
    set, so each is exercised: a plain attached device, a device that is
    both attached and kept, and a kept entry with nothing attached."""
    import io
    import json
    from contextlib import redirect_stdout

    devctl = importlib.import_module("hammunition.cli.devctl")
    from hammunition.hardware import power

    attached_only = Parkable(
        name="attached-only",
        summary="An attached, not-kept device",
        method="usb_deauthorize",
        quiet=(),
        sysfs_path="/sys/bus/usb/devices/1-2",
        identifier="1111:2222",
        parked=False,
    )
    kept_attached = Parkable(
        name="kept-attached",
        summary="An attached, kept device",
        method="usb_deauthorize",
        quiet=(),
        sysfs_path="/sys/bus/usb/devices/1-3",
        identifier="3333:4444",
        parked=True,
    )
    kept_attached_entry = KeptEntry(
        name="kept-attached", address="1-3", vendor="3333", product="4444"
    )
    kept_absent_entry = KeptEntry(name="kept-absent", address="9-9", vendor="dead", product="beef")

    found = [attached_only, kept_attached]
    kept = [kept_attached_entry, kept_absent_entry]

    buf = io.StringIO()
    monkeypatch.setattr(devctl, "_survey", lambda: (found, []))
    # devctl imports `read_kept` by name at module load, so it must be
    # patched on `devctl` itself -- patching `power.read_kept` only reaches
    # `cmd_hardware_state`, which re-imports it fresh on every call.
    monkeypatch.setattr(devctl, "read_kept", lambda: kept)
    with redirect_stdout(buf):
        devctl._state()
    helper_rows = json.loads(buf.getvalue())
    assert len(helper_rows) == 3, "fixture must cover attached, kept+attached, kept+absent"

    monkeypatch.setattr(cli, "_survey_parkables", lambda args: (found, []))
    monkeypatch.setattr(power, "read_kept", lambda: kept)
    assert cli.main(["hardware", "state", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)

    assert doc["devices"] == helper_rows, (doc["devices"], helper_rows)
