# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The privileged helper: what it accepts, and everything it refuses.

This is the only code in the project that runs as root on an operator's
desktop at the press of a switch, so its refusals are the feature. It takes a
name and derives every path itself.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from hammunition.cli.devctl import main, resolve, resolve_kept
from hammunition.hardware.polkit import WritabilityFinding, WritabilityRisk
from hammunition.hardware.power import KeptEntry, Parkable, PowerError


@pytest.fixture(autouse=True)
def _unprivileged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this file calls `main()`, which checks `os.geteuid() ==
    0` before running the D-056 writability gate (fix round 1). Pinned to a
    non-root value here so the suite's outcome depends on what a test stubs,
    not on whether the container actually running it happens to run pytest
    as root -- `containers/Dockerfile.target` has no `USER` directive, so the
    container matrix runs as uid 0 and this file's tests would silently
    depend on that fact without a pin (CLAUDE.md: test the matrix, not your
    machine). Reusing the `monkeypatch` fixture: a test that itself asks for
    `monkeypatch` and re-pins `os.geteuid` to 0 gets the same instance and
    correctly overrides this default for that one test only."""
    monkeypatch.setattr(os, "geteuid", lambda: 1000)


def _parkable(name: str, address: str, parked: bool = False) -> Parkable:
    return Parkable(
        name=name,
        summary=f"{name} summary",
        method="usb_deauthorize",
        quiet=(),
        sysfs_path=f"/sys/bus/usb/devices/{address}",
        identifier="1546:01a7",
        parked=parked,
    )


def test_resolve_finds_the_only_device_of_that_name() -> None:
    found = [_parkable("gps-receiver", "1-4")]
    assert resolve("gps-receiver", found).address == "1-4"


def test_resolve_refuses_a_name_that_is_not_parkable() -> None:
    with pytest.raises(PowerError, match="not a parkable"):
        resolve("hackrf", [_parkable("gps-receiver", "1-4")])


def test_resolve_names_what_is_parkable_when_it_refuses() -> None:
    with pytest.raises(PowerError, match="gps-receiver"):
        resolve("hackrf", [_parkable("gps-receiver", "1-4")])


def test_resolve_refuses_an_ambiguous_name_naming_both_addresses() -> None:
    """Review Focus 2. Two pucks attached: `park gps-receiver` means either,
    and picking one silently parks the wrong receiver."""
    found = [_parkable("gps-receiver", "1-4"), _parkable("gps-receiver", "1-5")]
    with pytest.raises(PowerError) as caught:
        resolve("gps-receiver", found)
    message = str(caught.value)
    assert "1-4" in message and "1-5" in message


def test_resolve_accepts_an_address_to_disambiguate() -> None:
    found = [_parkable("gps-receiver", "1-4"), _parkable("gps-receiver", "1-5")]
    assert resolve("gps-receiver@1-5", found).address == "1-5"


def test_resolve_refuses_an_address_that_is_not_attached() -> None:
    """The address-specific refusal, not the generic one -- both happen to
    contain the substring '1-9' (`resolve()` formats the generic message
    with the unsplit `name`, which is `gps-receiver@1-9`), so a `match="1-9"`
    assertion alone passes even if the address-specific `raise` in
    `resolve()` is deleted outright. Pin the wording that only the
    address-specific branch produces, and assert the attached listing
    (`1-4`) is present too -- that is the part that actually makes the
    refusal useful to the operator typing the wrong address.
    """
    with pytest.raises(PowerError, match=r"at address '1-9' is attached"):
        resolve("gps-receiver@1-9", [_parkable("gps-receiver", "1-4")])


def test_resolve_names_what_is_attached_when_the_address_is_wrong() -> None:
    with pytest.raises(PowerError) as caught:
        resolve("gps-receiver@1-9", [_parkable("gps-receiver", "1-4")])
    assert "1-4" in str(caught.value)


def test_state_prints_json_a_tray_can_read(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: ([_parkable("gps-receiver", "1-4", parked=True)], []),
    )
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [])
    assert main(["state"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "name": "gps-receiver",
            "summary": "gps-receiver summary",
            "address": "1-4",
            "identifier": "1546:01a7",
            "method": "usb_deauthorize",
            "parked": True,
            "kept": False,
            "attached": True,
        }
    ]


def test_state_is_valid_json_when_nothing_is_parkable(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The applet parses this on a 5 s timer. An empty survey printing a
    human sentence instead of `[]` is a parse error every five seconds."""
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [])
    assert main(["state"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_state_reports_skipped_devices_on_stderr_not_in_the_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: ([], [("gps-receiver", "authorized could not be read")]),
    )
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [])
    assert main(["state"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "authorized" in captured.err


def test_park_refuses_an_unknown_name_with_exit_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey", lambda: ([_parkable("gps-receiver", "1-4")], [])
    )
    assert main(["park", "hackrf"]) == 2
    assert "not a parkable" in capsys.readouterr().err


def test_park_refuses_a_device_whose_node_now_holds_something_else(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 4. Unplug and replug between `state` and `park` and the
    address can be reused by a different device. The helper re-surveys, so the
    stale name is simply gone -- it must say so, not write to the address."""
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    assert main(["park", "gps-receiver"]) == 2
    assert "not a parkable" in capsys.readouterr().err


def test_an_unknown_verb_is_refused() -> None:
    with pytest.raises(SystemExit):
        main(["incinerate", "gps-receiver"])


def test_refuses_to_run_as_root_when_the_tree_is_group_or_other_writable(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-056's ruling: the install-time check in `hardware apply` is repeated
    here, at the moment this process is actually about to act as root, in
    case the tree became writable since. Gated on ``geteuid() == 0``, pinned
    to 0 here specifically to reach the branch at all -- overriding this
    file's autouse ``_unprivileged`` fixture for this one test.

    Fix round 2: only the group/other-writable class is refused. Round 1
    refused on *any* writability finding, including one specific non-root
    account merely owning the tree -- the documented install's own shape --
    which made this check fire on every privileged run in that state."""
    import hammunition.cli.devctl as devctl

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        devctl,
        "writable_including_symlink_target",
        lambda path: WritabilityFinding(
            "/opt/hammunition/.venv", WritabilityRisk.GROUP_OR_OTHER_WRITABLE
        ),
    )
    monkeypatch.setattr(devctl, "read_kept", lambda: [])
    assert main(["state"]) == 2
    err = capsys.readouterr().err
    assert "/opt/hammunition/.venv" in err
    assert "refusing" in err


def test_warns_but_proceeds_when_the_tree_is_merely_owned_by_non_root(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented install: a venv under `$HOME` is owned by exactly one
    non-root account and nobody else. That must never refuse -- a warning on
    stderr, then the verb still runs."""
    import hammunition.cli.devctl as devctl

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        devctl,
        "writable_including_symlink_target",
        lambda path: WritabilityFinding(
            "/opt/hammunition/.venv", WritabilityRisk.OWNED_BY_NON_ROOT
        ),
    )
    monkeypatch.setattr(devctl, "_survey", lambda: ([], []))
    monkeypatch.setattr(devctl, "read_kept", lambda: [])
    assert main(["state"]) == 0
    err = capsys.readouterr().err
    assert "/opt/hammunition/.venv" in err
    assert "warning" in err.lower()


def test_does_not_refuse_when_not_actually_running_as_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falsifies a check that fired unconditionally: every other test in this
    file runs unprivileged (via the autouse ``_unprivileged`` fixture, pinned
    explicitly here too for the reader's benefit) and would break the moment
    the gate stopped checking ``geteuid()`` first."""
    import hammunition.cli.devctl as devctl

    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        devctl,
        "writable_including_symlink_target",
        lambda path: WritabilityFinding(
            "/opt/hammunition/.venv", WritabilityRisk.GROUP_OR_OTHER_WRITABLE
        ),
    )
    monkeypatch.setattr(devctl, "_survey", lambda: ([], []))
    monkeypatch.setattr(devctl, "read_kept", lambda: [])
    assert main(["state"]) == 0


def test_runtime_check_is_load_bearing_for_the_package_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 3, item 5: the three tests above stub
    `writable_including_symlink_target` module-wide, so dropping either the
    interpreter call or the package-dir call in `_runtime_writability_findings`
    would fail none of them. This exercises the *real* helper against a real
    `tmp_path` tree, with the interpreter pointed at a genuinely safe system
    binary, so only the package-directory call site can be driving the
    refusal."""
    import hammunition.cli.devctl as devctl

    unsafe_root = tmp_path / "pkg"
    unsafe_root.mkdir()
    os.chmod(unsafe_root, 0o777)
    fake_file = unsafe_root / "hammunition" / "cli" / "devctl.py"
    fake_file.parent.mkdir(parents=True)
    fake_file.write_text("# stand-in for this module's own __file__")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(devctl, "__file__", str(fake_file))
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(devctl, "read_kept", lambda: [])

    assert main(["state"]) == 2
    err = capsys.readouterr().err
    assert str(unsafe_root) in err


def test_runtime_check_is_load_bearing_for_the_interpreter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror of the test above: the package directory is pointed at a
    real, safely root-owned system directory (`/usr`), so only the
    interpreter call site can be driving the refusal here."""
    import hammunition.cli.devctl as devctl

    unsafe_root = tmp_path / "venv"
    unsafe_root.mkdir()
    os.chmod(unsafe_root, 0o777)
    fake_python = unsafe_root / "bin" / "python3"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o755)

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    # /usr/fake/cli/devctl.py -> parent.parent is /usr, real and root-owned
    # on any target this suite runs on.
    monkeypatch.setattr(devctl, "__file__", "/usr/fake/cli/devctl.py")
    monkeypatch.setattr(sys, "executable", str(fake_python))
    monkeypatch.setattr(devctl, "read_kept", lambda: [])

    assert main(["state"]) == 2
    err = capsys.readouterr().err
    assert str(unsafe_root) in err


GPS_KEPT = KeptEntry("gps-receiver", "3-5.1", "1546", "01a7")


def _recording(seen: list[object]) -> Callable[[object], list[str]]:
    def fake(plan: object) -> list[str]:
        seen.append(plan)
        return []

    return fake


def test_state_marks_an_attached_kept_device(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: ([_parkable("gps-receiver", "3-5.1", parked=True)], []),
    )
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [GPS_KEPT])
    assert main(["state"]) == 0
    [row] = json.loads(capsys.readouterr().out)
    assert row["kept"] is True and row["attached"] is True and row["parked"] is True


def test_state_lists_a_kept_device_that_is_not_attached(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [GPS_KEPT])
    assert main(["state"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {
            "name": "gps-receiver",
            "summary": "",
            "address": "3-5.1",
            "identifier": "1546:01a7",
            "method": "usb_deauthorize",
            "parked": None,
            "kept": True,
            "attached": False,
        }
    ]


def test_state_still_prints_json_when_the_kept_file_is_foreign(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> list[KeptEntry]:
        raise PowerError("line 1 was not written by Hammunition")

    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", broken)
    assert main(["state"]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out) == []
    assert "line 1" in err


def test_park_until_reboot_plans_no_kept_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey", lambda: ([_parkable("gps-receiver", "3-5.1")], [])
    )
    monkeypatch.setattr("hammunition.cli.devctl.execute", _recording(seen))
    assert main(["park", "--until-reboot", "gps-receiver"]) == 0
    assert seen[0].keep is None  # type: ignore[attr-defined]
    assert main(["park", "gps-receiver"]) == 0
    assert seen[1].keep is not None  # type: ignore[attr-defined]


def test_wake_forgets_a_kept_device_that_is_not_attached(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [GPS_KEPT])
    monkeypatch.setattr("hammunition.cli.devctl.execute", _recording(seen))
    assert main(["wake", "gps-receiver@3-5.1"]) == 0
    assert seen[0].writes == () and seen[0].forget == GPS_KEPT  # type: ignore[attr-defined]


def test_park_of_an_absent_device_is_still_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [GPS_KEPT])
    assert main(["park", "gps-receiver@3-5.1"]) == 2


def test_resolve_kept_refuses_a_bare_name_matching_two_ports() -> None:
    other = KeptEntry("gps-receiver", "3-6", "1546", "01a7")
    with pytest.raises(PowerError, match=r"3-5\.1"):
        resolve_kept("gps-receiver", [GPS_KEPT, other])
    assert resolve_kept("gps-receiver@3-6", [GPS_KEPT, other]) == other


def test_wake_of_an_ambiguous_attached_name_is_refused_even_with_a_kept_entry(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final review finding 1: two attached, one of them kept. A bare name is
    ambiguous among *attached* devices, so it is refused as ambiguous -- never
    turned into a forget of the kept one, which would leave it parked."""
    seen: list[object] = []
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: (
            [_parkable("gps-receiver", "1-4", parked=True), _parkable("gps-receiver", "1-5")],
            [],
        ),
    )
    monkeypatch.setattr(
        "hammunition.cli.devctl.read_kept",
        lambda: [KeptEntry("gps-receiver", "1-4", "1546", "01a7")],
    )
    monkeypatch.setattr("hammunition.cli.devctl.execute", _recording(seen))
    assert main(["wake", "gps-receiver"]) == 2
    assert seen == []
    assert "would be a guess" in capsys.readouterr().err


def test_wake_of_an_ambiguous_name_with_nothing_kept_keeps_the_ambiguity_message(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: ([_parkable("gps-receiver", "1-4"), _parkable("gps-receiver", "1-5")], []),
    )
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [])
    assert main(["wake", "gps-receiver"]) == 2
    err = capsys.readouterr().err
    assert "would be a guess" in err
    assert "neither attached nor kept" not in err


def _time_state() -> Any:
    from datetime import UTC, datetime

    from hammunition.gpstime.state import TimeState

    return TimeState(
        mode="auto",
        mode_set=False,
        daemon="ntpsec",
        gps="awake",
        following="network",
        offset_ms=-4.4,
        last_sync=datetime(2026, 9, 28, 14, 44, tzinfo=UTC),
        last_source="network",
        holdover_seconds=None,
        rtc=True,
        grants=True,
        dhcp_config=False,
        problems=(),
    )


def test_time_state_prints_one_json_object(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.cli import devctl
    from hammunition.gpstime.state import JSON_KEYS

    monkeypatch.setattr(devctl, "_survey", lambda: ([_parkable("gps-receiver", "1-4")], []))
    seen: list[str] = []

    def fake_gather(*, gps: str) -> Any:
        seen.append(gps)
        return _time_state()

    monkeypatch.setattr(devctl, "gather", fake_gather)
    assert main(["time", "state"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert tuple(body) == JSON_KEYS
    assert seen == ["awake"]


def test_time_mode_takes_only_the_four_modes() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["time", "mode", "gps"])
    assert caught.value.code == 2


def test_time_needs_a_verb() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["time"])
    assert caught.value.code == 2


def test_time_mode_applies_the_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from hammunition.cli import devctl

    applied: list[str] = []

    def recording(mode: str) -> list[str]:
        applied.append(mode)
        return []

    monkeypatch.setattr(devctl, "apply_mode", recording)
    assert main(["time", "mode", "gps-only"]) == 0
    assert applied == ["gps-only"]


def test_time_mode_refusal_is_exit_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.cli import devctl
    from hammunition.gpstime.mode import TimeError

    def refusing(mode: str) -> list[str]:
        raise TimeError("ntpsec is not installed")

    monkeypatch.setattr(devctl, "apply_mode", refusing)
    assert main(["time", "mode", "auto"]) == 2
    assert "error: ntpsec is not installed" in capsys.readouterr().err


def test_time_mode_problems_are_exit_1(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.cli import devctl

    monkeypatch.setattr(devctl, "apply_mode", lambda mode: ["ntpsec did not restart"])
    assert main(["time", "mode", "auto"]) == 1
    assert "unverified: ntpsec did not restart" in capsys.readouterr().err


# --- linger (D-073 §5a) ------------------------------------------------------


def test_caller_uid_prefers_pkexec_then_sudo_then_self(monkeypatch: pytest.MonkeyPatch) -> None:
    from hammunition.cli.devctl import caller_uid

    monkeypatch.setenv("PKEXEC_UID", "1001")
    monkeypatch.setenv("SUDO_UID", "1002")
    assert caller_uid() == 1001
    monkeypatch.delenv("PKEXEC_UID")
    assert caller_uid() == 1002
    monkeypatch.delenv("SUDO_UID")
    assert caller_uid() == os.getuid()


def test_linger_handler_uses_the_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`linger on` when it is off runs loginctl enable-linger for the caller's
    own account and writes an ours=True record — without touching real systemd."""
    import hammunition.cli.devctl as devctl
    from hammunition.backends.base import CommandResult, SubprocessRunner
    from hammunition.hardware import linger as linger_mod

    record = tmp_path / "linger.yaml"
    monkeypatch.setattr(linger_mod, "LINGER_RECORD", record)
    monkeypatch.setattr(devctl, "LINGER_RECORD", record)
    monkeypatch.setattr(devctl, "caller_uid", lambda: os.getuid())
    monkeypatch.setattr(devctl, "_linger_is_on", lambda _u: False)

    ran: list[tuple[str, ...]] = []

    def fake_run(self: object, command: Any) -> CommandResult:
        ran.append(command.argv)
        return CommandResult(argv=command.argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(SubprocessRunner, "run", fake_run)

    rc = devctl.main(["linger", "on"])
    assert rc == 0
    assert any(a[:2] == ("loginctl", "enable-linger") for a in ran)
    back = linger_mod.read_record(path=record)
    assert back is not None and back.enabled_by_us is True
