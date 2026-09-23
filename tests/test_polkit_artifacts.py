# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The two privileged artefacts hardware apply installs, and their removal."""

from __future__ import annotations

import shlex
from pathlib import Path
from xml.etree import ElementTree

import pytest

from hammunition.hardware.polkit import (
    ACTION_ID,
    HELPER_PATH,
    POLICY_PATH,
    plan_polkit,
    policy_xml,
    wrapper_script,
)


def test_the_policy_is_well_formed_xml() -> None:
    root = ElementTree.fromstring(policy_xml())
    assert root.tag == "policyconfig"


def test_the_policy_declares_exactly_one_action_with_our_id() -> None:
    root = ElementTree.fromstring(policy_xml())
    actions = root.findall("action")
    assert len(actions) == 1
    assert actions[0].get("id") == ACTION_ID


def test_the_policy_prompts_once_then_stays_quiet_for_the_session() -> None:
    root = ElementTree.fromstring(policy_xml())
    defaults = root.find("action/defaults")
    assert defaults is not None
    assert defaults.findtext("allow_active") == "auth_self_keep"
    assert defaults.findtext("allow_inactive") == "auth_admin"
    assert defaults.findtext("allow_any") == "auth_admin"


def test_the_policy_annotates_the_wrapper_path_it_authorises() -> None:
    root = ElementTree.fromstring(policy_xml())
    annotations = {a.get("key"): (a.text or "") for a in root.findall("action/annotate")}
    assert annotations["org.freedesktop.policykit.exec.path"] == HELPER_PATH
    assert annotations["org.freedesktop.policykit.exec.allow_gui"] == "true"


def test_the_wrapper_execs_the_interpreter_that_owns_the_package() -> None:
    """A venv install's entry point is not on root's PATH, and polkit
    annotates an absolute path. The wrapper is the stable indirection."""
    body = wrapper_script("/opt/hammunition/.venv/bin/python3")
    assert body.startswith("#!/bin/sh\n")
    assert "/opt/hammunition/.venv/bin/python3" in body
    assert "hammunition.cli.devctl" in body
    assert body.rstrip().endswith('"$@"')


def test_the_wrapper_quotes_an_interpreter_path_with_a_space() -> None:
    body = wrapper_script("/home/op/my venv/bin/python3")
    assert shlex.quote("/home/op/my venv/bin/python3") in body


def test_the_plan_names_both_artefacts_at_their_fixed_paths() -> None:
    artefacts = plan_polkit(interpreter="/usr/bin/python3")
    assert artefacts.helper_path == HELPER_PATH
    assert artefacts.policy_path == POLICY_PATH


def test_the_plan_is_a_noop_when_both_files_already_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotence: apply twice and the second run has nothing to do."""
    helper = tmp_path / "hammunition-devctl"
    policy = tmp_path / "action.policy"
    monkeypatch.setattr("hammunition.hardware.polkit.HELPER_PATH", str(helper))
    monkeypatch.setattr("hammunition.hardware.polkit.POLICY_PATH", str(policy))
    helper.write_text(wrapper_script("/usr/bin/python3"))
    policy.write_text(policy_xml())

    artefacts = plan_polkit(interpreter="/usr/bin/python3")
    assert artefacts.helper_current is True
    assert artefacts.policy_current is True


def test_the_plan_is_not_a_noop_when_the_interpreter_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = tmp_path / "hammunition-devctl"
    monkeypatch.setattr("hammunition.hardware.polkit.HELPER_PATH", str(helper))
    monkeypatch.setattr("hammunition.hardware.polkit.POLICY_PATH", str(tmp_path / "p.policy"))
    helper.write_text(wrapper_script("/old/venv/bin/python3"))

    assert plan_polkit(interpreter="/new/venv/bin/python3").helper_current is False
