# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Opt-in unattended linger.  D-073 §5a."""

from __future__ import annotations

from pathlib import Path

from hammunition.hardware.linger import (
    LingerRecord,
    plan_linger,
    read_record,
    write_record,
)
from hammunition.hardware.polkit import policy_xml


def test_enable_when_off_runs_loginctl_and_records_ours() -> None:
    plan = plan_linger(on=True, uid=1000, username="op", already_on=False, existing=None)
    assert plan.command == ("loginctl", "enable-linger", "op")
    assert plan.record is not None and plan.record.enabled_by_us is True


def test_enable_when_already_on_records_not_ours_and_runs_nothing() -> None:
    plan = plan_linger(on=True, uid=1000, username="op", already_on=True, existing=None)
    assert plan.command is None
    assert plan.record is not None and plan.record.enabled_by_us is False


def test_disable_only_when_ours() -> None:
    ours = LingerRecord(uid=1000, enabled_by_us=True)
    plan = plan_linger(on=False, uid=1000, username="op", already_on=True, existing=ours)
    assert plan.command == ("loginctl", "disable-linger", "op")
    assert plan.remove_record is True


def test_disable_is_a_no_op_when_not_ours() -> None:
    not_ours = LingerRecord(uid=1000, enabled_by_us=False)
    plan = plan_linger(on=False, uid=1000, username="op", already_on=True, existing=not_ours)
    assert plan.command is None
    assert plan.remove_record is False


def test_record_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "linger.yaml"
    write_record(LingerRecord(uid=1000, enabled_by_us=True), path=path)
    back = read_record(path=path)
    assert back == LingerRecord(uid=1000, enabled_by_us=True)


def test_record_absent_reads_none(tmp_path: Path) -> None:
    assert read_record(path=tmp_path / "nope.yaml") is None


def test_the_polkit_action_wording_covers_keeping_services_running() -> None:
    xml = policy_xml()
    assert "log out" in xml or "logout" in xml or "logged out" in xml


def test_re_enabling_when_already_ours_keeps_it_ours() -> None:
    """Review I3: running --unattended twice must not flip the record to
    not-ours, which would make --no-unattended a no-op."""
    ours = LingerRecord(uid=1000, enabled_by_us=True)
    plan = plan_linger(on=True, uid=1000, username="op", already_on=True, existing=ours)
    assert plan.record is not None and plan.record.enabled_by_us is True


def test_off_only_disables_when_the_record_is_this_uid() -> None:
    """Review I3: the record is keyed by uid; user B's off must not disable
    B's own linger (which we never set) nor delete A's record."""
    a_record = LingerRecord(uid=1000, enabled_by_us=True)
    plan = plan_linger(on=False, uid=2000, username="userb", already_on=True, existing=a_record)
    assert plan.command is None
    assert plan.remove_record is False
