# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Planning the rig user service: render, substitute, defer, skip.  D-073 §6."""

from __future__ import annotations

from pathlib import Path

from hammunition.manifest.hardware import DeviceManifest
from hammunition.manifest.load import load_catalog, load_hardware
from hammunition.manifest.schema import PackageManifest
from hammunition.station import Station
from hammunition.userservice import (
    device_unit_name,
    plan_user_services,
)

ROOT = Path(__file__).resolve().parent.parent
_BY_ID = "/dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0"


def _rig_service() -> PackageManifest:
    return load_catalog(ROOT / "catalog" / "packages")["rig-service"]


def _devices() -> dict[str, DeviceManifest]:
    _classes, devices = load_hardware(ROOT / "catalog" / "hardware")
    return devices


def test_device_unit_name_matches_systemd_escaping() -> None:
    assert device_unit_name(_BY_ID) == (
        "dev-serial-by\\x2did-usb\\x2dSilicon_Labs_CP2105_...\\x2dif00\\x2dport0.device"
    )


def test_a_cat_rig_renders_the_service() -> None:
    station = Station(rig="yaesu-ft-991a", rig_device=_BY_ID, rig_baud=38400)
    planned, deferrals, notes = plan_user_services(_rig_service(), station, _devices())
    assert not deferrals and not notes
    (svc,) = planned
    assert svc.exec_argv == (
        "/usr/bin/rigctld",
        "-m",
        "1035",
        "-r",
        _BY_ID,
        "-s",
        "38400",
        "-T",
        "127.0.0.1",
        "-t",
        "4532",
    )
    assert "ExecStart=/usr/bin/rigctld -m 1035 -r " + _BY_ID in svc.unit_body
    assert "NoNewPrivileges=yes" in svc.unit_body
    assert "BindsTo=" in svc.unit_body
    assert svc.unit_body.splitlines()[0].startswith("# Written by Hammunition")
    assert set(svc.filled_from) == {"rig", "rig_device", "rig_baud"}


def test_a_missing_device_defers() -> None:
    station = Station(rig="yaesu-ft-991a", rig_baud=38400)
    planned, deferrals, _notes = plan_user_services(_rig_service(), station, _devices())
    assert not planned
    (d,) = deferrals
    assert "rig_device" in d.why


def test_flrig_skips_the_service() -> None:
    station = Station(rig="yaesu-ft-991a", rig_device=_BY_ID, rig_baud=38400, rig_owner="flrig")
    planned, deferrals, notes = plan_user_services(_rig_service(), station, _devices())
    assert not planned and not deferrals
    assert any("flrig" in n for n in notes)


def test_a_ptt_only_rig_renders_the_dummy_service() -> None:
    station = Station(rig="btech-uv-50pro", rig_device=_BY_ID, rig_ptt_line="rts")
    planned, deferrals, notes = plan_user_services(_rig_service(), station, _devices())
    assert not deferrals
    # A PTT-only rig renders, with the no-frequency-control caution as a note.
    assert any("frequency" in n for n in notes)
    (svc,) = planned
    assert svc.exec_argv == (
        "/usr/bin/rigctld",
        "-m",
        "1",
        "-p",
        _BY_ID,
        "-P",
        "RTS",
        "-T",
        "127.0.0.1",
        "-t",
        "4532",
    )


def test_vox_skips_the_service() -> None:
    station = Station(rig="btech-uv-50pro", rig_device=_BY_ID, rig_ptt_line="vox")
    planned, deferrals, notes = plan_user_services(_rig_service(), station, _devices())
    assert not planned and not deferrals
    assert any("VOX" in n or "vox" in n for n in notes)


def test_an_uncatalogued_model_renders_with_a_note() -> None:
    station = Station(rig="hamlib:3073", rig_device=_BY_ID, rig_baud=115200)
    planned, _deferrals, notes = plan_user_services(
        _rig_service(), station, _devices(), model_lister=lambda: {3073: (1200, 115200)}
    )
    (svc,) = planned
    assert "-m" in svc.exec_argv and "3073" in svc.exec_argv
    assert any("unmeasured" in n for n in notes)


def test_a_rig_no_longer_in_the_catalog_defers_with_a_reason() -> None:
    station = Station(rig="ft-gone", rig_device=_BY_ID, rig_baud=38400)
    planned, deferrals, _notes = plan_user_services(_rig_service(), station, _devices())
    assert not planned
    (d,) = deferrals
    assert "catalog" in d.why.lower()


def test_rig_unset_defers_naming_rig() -> None:
    station = Station()
    planned, deferrals, _notes = plan_user_services(_rig_service(), station, _devices())
    assert not planned
    (d,) = deferrals
    assert "rig" in d.why
