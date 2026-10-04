# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import getpass
import socket
from pathlib import Path

import pytest

from .fixture_scan import findings, host_pattern, live_identity_findings, user_pattern

FIX = Path(__file__).parent / "fixtures"


def test_placeholders_are_clean() -> None:
    assert (
        findings('{"callsign": "N0CALL", "alt": "N0TST", "grid": "FN31pr", "path": "/home/user/x"}')
        == []
    )


def test_a_real_looking_callsign_is_found() -> None:
    assert any("callsign" in f for f in findings('{"callsign": "ZZ9ZZ"}'))
    assert any("callsign" in f for f in findings("QQ1QQ"))


def test_a_real_looking_grid_is_found() -> None:
    assert any("grid" in f for f in findings('{"grid_square": "JJ00aa"}'))


def test_a_real_home_path_is_found() -> None:
    assert any("home" in f for f in findings("/home/someoneelse/.config"))


def test_the_live_username_and_hostname_are_found_in_machine_contexts() -> None:
    user = getpass.getuser()
    if len(user) >= 3:
        assert findings(f"on {user}@somewhere")
        assert findings(f"owner: {user}")
    host = socket.gethostname().split(".")[0]
    if len(host) >= 3:
        assert findings(f"on user@{host}")


def test_a_bare_word_is_not_an_identity() -> None:
    for name in ("runner", "root", "example"):
        assert not host_pattern(name).search(f"the {name} of the {name}s, {name}/1, {name}-tray")
        assert not user_pattern(name).search(f"the {name} of the {name}s, {name}/1, {name}-tray")


def test_machine_contexts_are_found() -> None:
    for text in ("user@example", "example.local", "hostname: example"):
        assert host_pattern("example").search(text), text
    for text in ("/home/example/x", "example@box", "owner: example"):
        assert user_pattern("example").search(text), text


@pytest.mark.parametrize("name", ["runner", "root"])
def test_committed_fixtures_pass_whoever_runs_the_suite(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(getpass, "getuser", lambda: name)
    monkeypatch.setattr(socket, "gethostname", lambda: name)
    for path in sorted(FIX.iterdir()):
        if path.is_file():
            assert findings(path.read_text()) == [], f"{path.name} as {name}"


def test_the_recording_time_check_is_a_bare_substring_check() -> None:
    user = getpass.getuser()
    if len(user) >= 3:
        assert live_identity_findings(f"... {user} ...")


def test_a_serial_by_id_path_is_found() -> None:
    assert findings("/dev/serial/by-id/usb-Silicon_Labs_CP2105_0123ABCD-if00")
    assert findings("/dev/serial/by-id/usb-FIXTURE-if00") == []
