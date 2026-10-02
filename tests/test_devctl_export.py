# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The two lists ``hardware apply`` exports for the tray's helper.  D-056 amended.

Every path is under the test's tmp_path (`devctl_export_files`). `install` and
`rm` are done to disk the way the CLI's fake runners do them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from hammunition.backends.base import Command
from hammunition.hardware import devctl_export as de
from hammunition.manifest.hardware import (
    DeviceClass,
    DeviceManifest,
    HardwareDocumentation,
)
from hammunition.manifest.load import load_hardware

DOCS = HardwareDocumentation(
    what_it_is="A GNSS receiver used for position and time.",
    what_you_can_do_with_it="Feed gpsd so programs know where and when they are.",
    setup_steps="Plug it in, join dialout, then log out and back in again.",
)


def _entry(
    kind: type[DeviceClass] | type[DeviceManifest],
    name: str,
    *,
    power: bool,
    ids: list[dict[str, Any]] | None = None,
    quiet: list[str] | None = None,
) -> DeviceClass | DeviceManifest:
    body: dict[str, Any] = {
        "name": name,
        "summary": f"{name} summary",
        "documentation": DOCS,
        "usb_ids": ids
        if ids is not None
        else [
            {
                "vendor": "1546",
                "product": "01a8",
                "description": f"{name} id",
                "evidence": "Debian 13 /lib/udev/rules.d/60-gpsd.rules",
                "confirmed": True,
                "node_kind": "serial",
            }
        ],
    }
    if kind is DeviceManifest:
        body["vendor"] = "Example Ltd"
    if power:
        body["power_control"] = {
            "method": "usb_deauthorize",
            "quiet": quiet or [],
            "note": "Parking it drops the interface; waking brings it back.",
        }
    return kind.model_validate(body)


def _catalog() -> tuple[dict[str, DeviceClass], dict[str, DeviceManifest]]:
    classes = {"gps-receiver": _entry(DeviceClass, "gps-receiver", power=True)}
    devices = {
        "modem": _entry(
            DeviceManifest,
            "modem",
            power=True,
            quiet=["networkmanager_autoconnect"],
            ids=[
                {
                    "vendor": "413c",
                    "product": "81d7",
                    "description": "a modem",
                    "evidence": "lsusb capture from real hardware",
                    "confirmed": True,
                    "node_kind": "libusb",
                    "product_string": "Fixture Modem",
                }
            ],
        ),
        "rig": _entry(DeviceManifest, "rig", power=False),
    }
    return classes, devices  # type: ignore[return-value]


def _install(commands: list[Command]) -> None:
    for command in commands:
        argv = command.argv
        if argv[0] == "install":
            src, dest = Path(argv[-2]), Path(argv[-1])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            os.chmod(dest, int(argv[argv.index("-m") + 1], 8))
        elif argv[:2] == ("rm", "-f"):
            Path(argv[2]).unlink(missing_ok=True)


def _applied(tmp_path: Path, **kwargs: Any) -> None:
    classes, devices = _catalog()
    step = de.plan_devctl_export(classes, devices, **kwargs)
    staging = tmp_path / "staging"
    staging.mkdir(exist_ok=True)
    de.stage(step, staging)
    _install(de.install_commands(step, str(staging)))


def test_the_devices_file_carries_only_entries_with_power_control(
    devctl_export_files: Path,
) -> None:
    classes, devices = _catalog()
    doc = yaml.safe_load(de.devices_content(classes, devices))
    assert doc["version"] == 1
    assert [d["name"] for d in doc["devices"]] == ["gps-receiver", "modem"]


def test_the_devices_file_has_what_state_needs_from_the_catalog_alone(
    devctl_export_files: Path,
) -> None:
    classes, devices = _catalog()
    doc = yaml.safe_load(de.devices_content(classes, devices))
    modem = next(d for d in doc["devices"] if d["name"] == "modem")
    assert modem["summary"] == "modem summary"
    assert modem["method"] == "usb_deauthorize"
    assert modem["quiet"] == ["networkmanager_autoconnect"]
    assert modem["usb_ids"] == [
        {
            "vendor": "413c",
            "product": "81d7",
            "product_string": "Fixture Modem",
            "ambiguous": False,
            "distinctive": True,
        }
    ]


def test_an_unconfirmed_identifier_is_not_exported(devctl_export_files: Path) -> None:
    ids = [
        {
            "vendor": "dead",
            "product": "beef",
            "description": "unconfirmed",
            "evidence": "a forum post, never captured",
            "confirmed": False,
        },
        {
            "vendor": "1546",
            "product": "01a8",
            "description": "confirmed",
            "evidence": "Debian 13 /lib/udev/rules.d/60-gpsd.rules",
            "confirmed": True,
        },
    ]
    devices = {"gps": _entry(DeviceManifest, "gps", power=True, ids=ids)}
    doc = yaml.safe_load(de.devices_content({}, devices))
    assert [i["vendor"] for i in doc["devices"][0]["usb_ids"]] == ["1546"]


def test_a_product_string_two_entries_share_is_not_distinctive(devctl_export_files: Path) -> None:
    """detect.match_catalog's rule, carried in the file so state needs no catalog."""

    def ids(desc: str) -> list[dict[str, Any]]:
        return [
            {
                "vendor": "303a",
                "product": "1001",
                "description": desc,
                "evidence": "lsusb capture from real hardware",
                "confirmed": True,
                "product_string": "USB JTAG/serial debug unit",
                "ambiguity": {
                    "basis": "shared_across_products",
                    "evidence": "49 PlatformIO board files carry this identifier",
                },
            }
        ]

    devices = {
        "one": _entry(DeviceManifest, "one", power=True, ids=ids("one")),
        "two": _entry(DeviceManifest, "two", power=False, ids=ids("two")),
    }
    doc = yaml.safe_load(de.devices_content({}, devices))
    only = doc["devices"][0]["usb_ids"][0]
    assert only["ambiguous"] is True
    assert only["distinctive"] is False


def test_the_services_file_names_the_three_units(devctl_export_files: Path) -> None:
    doc = yaml.safe_load(de.services_content("ntpsec.service"))
    assert doc["version"] == 1
    assert [(s["name"], s["unit"], s["scope"]) for s in doc["services"]] == [
        ("gpsd", "gpsd.socket", "system"),
        ("time", "ntpsec.service", "system"),
        ("gps-resume", "hammunition-gps-resume.service", "system"),
    ]
    assert all(s["description"] for s in doc["services"])


def test_the_resume_unit_name_is_the_one_apply_installs(devctl_export_files: Path) -> None:
    from hammunition.hardware import gps_resume

    doc = yaml.safe_load(de.services_content("ntpsec.service"))
    assert doc["services"][2]["unit"] == gps_resume.UNIT_NAME


def test_the_time_unit_follows_the_daemon_the_machine_has(
    devctl_export_files: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.gpstime import state as time_state

    monkeypatch.setattr(time_state, "ntpsec_installed", lambda: False)
    assert de.detect_time_unit()[0] == "ntpsec.service"  # nothing found: D-058's own daemon, named
    chronyd = Path(de.CHRONYD)
    chronyd.parent.mkdir(parents=True)
    chronyd.write_text("")
    assert de.detect_time_unit()[0] == "chrony.service"
    monkeypatch.setattr(time_state, "ntpsec_installed", lambda: True)
    assert de.detect_time_unit()[0] == "ntpsec.service"  # ntpsec wins where both exist: D-058's path


def test_both_files_open_with_our_header_and_say_how_to_change_them(
    devctl_export_files: Path,
) -> None:
    classes, devices = _catalog()
    for text in (de.devices_content(classes, devices), de.services_content("ntpsec.service")):
        assert text.startswith(de.HEADER)
        assert "hammunition hardware unapply" in text.splitlines()[1] + text.splitlines()[2]


def test_a_fresh_machine_plans_both_files_and_nothing_else(devctl_export_files: Path) -> None:
    classes, devices = _catalog()
    step = de.plan_devctl_export(classes, devices, time_unit="ntpsec.service")
    assert not step.is_noop
    commands = de.install_commands(step, "<staging>")
    assert [c.argv for c in commands] == [
        ("install", "-D", "-m", "0644", "<staging>/devctl-devices.yaml", de.DEVICES_PATH),
        ("install", "-D", "-m", "0644", "<staging>/devctl-services.yaml", de.SERVICES_PATH),
    ]
    assert all(c.requires_root for c in commands)


def test_applied_and_verified_then_a_noop(devctl_export_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path, time_unit="ntpsec.service")
    classes, devices = _catalog()
    step = de.plan_devctl_export(classes, devices, time_unit="ntpsec.service")
    assert step.is_noop
    assert de.disclose(step) == []
    assert de.verify(step) == []
    assert de.install_commands(step, "<staging>") == []


def test_a_changed_catalog_rewrites_only_the_devices_file(
    devctl_export_files: Path, tmp_path: Path
) -> None:
    _applied(tmp_path, time_unit="ntpsec.service")
    classes, devices = _catalog()
    del devices["modem"]
    step = de.plan_devctl_export(classes, devices, time_unit="ntpsec.service")
    assert [c.argv[-1] for c in de.install_commands(step, "<staging>")] == [de.DEVICES_PATH]


def test_a_changed_time_daemon_rewrites_only_the_services_file(
    devctl_export_files: Path, tmp_path: Path
) -> None:
    _applied(tmp_path, time_unit="ntpsec.service")
    classes, devices = _catalog()
    step = de.plan_devctl_export(classes, devices, time_unit="chrony.service")
    assert [c.argv[-1] for c in de.install_commands(step, "<staging>")] == [de.SERVICES_PATH]


def test_the_disclosure_prints_both_files_whole_and_how_to_inspect_and_reverse(
    devctl_export_files: Path,
) -> None:
    classes, devices = _catalog()
    step = de.plan_devctl_export(classes, devices, time_unit="chrony.service")
    text = "\n".join(de.disclose(step))
    for line in de.devices_content(classes, devices).splitlines():
        assert line in text
    for line in de.services_content("chrony.service").splitlines():
        assert line in text
    assert de.DEVICES_PATH in text and de.SERVICES_PATH in text
    assert "hammunition services" in text
    assert "hammunition hardware unapply" in text
    assert "chrony.service" in text


def test_the_time_row_says_why_when_no_daemon_was_found(devctl_export_files: Path) -> None:
    classes, devices = _catalog()
    step = de.plan_devctl_export(classes, devices, time_unit="ntpsec.service", time_found=False)
    assert "No time daemon" in "\n".join(de.disclose(step))


def test_verify_names_a_file_that_does_not_match(devctl_export_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path, time_unit="ntpsec.service")
    Path(de.SERVICES_PATH).write_text(de.HEADER + "\nservices: []\n")
    classes, devices = _catalog()
    problems = de.verify(de.plan_devctl_export(classes, devices, time_unit="ntpsec.service"))
    assert any(de.SERVICES_PATH in p and "does not match" in p for p in problems)


def test_verify_names_a_missing_file(devctl_export_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path, time_unit="ntpsec.service")
    Path(de.DEVICES_PATH).unlink()
    classes, devices = _catalog()
    problems = de.verify(de.plan_devctl_export(classes, devices, time_unit="ntpsec.service"))
    assert any(de.DEVICES_PATH in p for p in problems)


@pytest.mark.parametrize("which", ["devices", "services"])
def test_a_file_hammunition_did_not_write_refuses_the_plan(
    devctl_export_files: Path, which: str
) -> None:
    path = Path(de.DEVICES_PATH if which == "devices" else de.SERVICES_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("services: []\n# the operator's own\n")
    classes, devices = _catalog()
    with pytest.raises(de.DevctlExportError, match="not written by Hammunition"):
        de.plan_devctl_export(classes, devices, time_unit="ntpsec.service")
    assert path.read_text() == "services: []\n# the operator's own\n"


def test_a_binary_file_at_the_path_is_foreign_not_a_crash(devctl_export_files: Path) -> None:
    Path(de.DEVICES_PATH).parent.mkdir(parents=True)
    Path(de.DEVICES_PATH).write_bytes(b"\x7fELF\xff\xfe")
    classes, devices = _catalog()
    with pytest.raises(de.DevctlExportError):
        de.plan_devctl_export(classes, devices, time_unit="ntpsec.service")
    assert de.plan_removal().is_empty


def test_removal_takes_back_both_files(devctl_export_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path, time_unit="ntpsec.service")
    removal = de.plan_removal()
    assert removal.devices_ours and removal.services_ours
    commands = de.removal_commands(removal)
    assert [c.argv for c in commands] == [
        ("rm", "-f", de.DEVICES_PATH),
        ("rm", "-f", de.SERVICES_PATH),
    ]
    assert all(c.requires_root for c in commands)
    _install(commands)
    assert de.verify_removal(removal) == []
    assert de.plan_removal().is_empty
    assert Path(de.DEVICES_PATH).parent.exists(), "the directory holds time.yaml; never removed"


def test_removal_leaves_a_file_someone_else_wrote(devctl_export_files: Path) -> None:
    Path(de.SERVICES_PATH).parent.mkdir(parents=True)
    Path(de.SERVICES_PATH).write_text("services: []\n")
    removal = de.plan_removal()
    assert removal.is_empty
    assert de.removal_commands(removal) == []


def test_verify_removal_names_what_survived(devctl_export_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path, time_unit="ntpsec.service")
    problems = de.verify_removal(de.plan_removal())
    assert f"{de.DEVICES_PATH} is still present" in problems
    assert f"{de.SERVICES_PATH} is still present" in problems


def test_the_shipped_catalog_exports_the_gps_receiver(devctl_export_files: Path) -> None:
    """The real catalog, not a fixture: the one class carrying power_control today."""
    classes, devices = load_hardware(Path(__file__).resolve().parent.parent / "catalog" / "hardware")
    doc = yaml.safe_load(de.devices_content(classes, devices))
    gps = next(d for d in doc["devices"] if d["name"] == "gps-receiver")
    assert gps["method"] == "usb_deauthorize"
    assert gps["usb_ids"], "a receiver with no identifiers could never be matched"
    for d in doc["devices"]:
        assert set(d) == {"name", "summary", "method", "quiet", "usb_ids"}


def test_no_station_value_can_reach_either_file(devctl_export_files: Path) -> None:
    """The helper never reads the station (D-056); neither does its data."""
    classes, devices = load_hardware(Path(__file__).resolve().parent.parent / "catalog" / "hardware")
    text = de.devices_content(classes, devices) + de.services_content("ntpsec.service")
    for forbidden in ("callsign", "grid_square", "N0CALL", "FN31pr"):
        assert forbidden not in text
