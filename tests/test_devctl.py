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

import pytest

from hammunition.cli.devctl import main, resolve
from hammunition.hardware.polkit import WritabilityFinding, WritabilityRisk
from hammunition.hardware.power import Parkable, PowerError


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
    with pytest.raises(PowerError, match="1-9"):
        resolve("gps-receiver@1-9", [_parkable("gps-receiver", "1-4")])


def test_state_prints_json_a_tray_can_read(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: ([_parkable("gps-receiver", "1-4", parked=True)], []),
    )
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
        }
    ]


def test_state_is_valid_json_when_nothing_is_parkable(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The applet parses this on a 5 s timer. An empty survey printing a
    human sentence instead of `[]` is a parse error every five seconds."""
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    assert main(["state"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_state_reports_skipped_devices_on_stderr_not_in_the_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: ([], [("gps-receiver", "authorized could not be read")]),
    )
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
        "writable_by_non_root",
        lambda path: WritabilityFinding(
            "/opt/hammunition/.venv", WritabilityRisk.GROUP_OR_OTHER_WRITABLE
        ),
    )
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
        "writable_by_non_root",
        lambda path: WritabilityFinding(
            "/opt/hammunition/.venv", WritabilityRisk.OWNED_BY_NON_ROOT
        ),
    )
    monkeypatch.setattr(devctl, "_survey", lambda: ([], []))
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
        "writable_by_non_root",
        lambda path: WritabilityFinding(
            "/opt/hammunition/.venv", WritabilityRisk.GROUP_OR_OTHER_WRITABLE
        ),
    )
    monkeypatch.setattr(devctl, "_survey", lambda: ([], []))
    assert main(["state"]) == 0
