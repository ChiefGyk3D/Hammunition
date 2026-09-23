# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The two privileged artefacts hardware apply installs, and their removal."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from xml.etree import ElementTree

import pytest

from hammunition.hardware.polkit import (
    ACTION_ID,
    HELPER_PATH,
    POLICY_PATH,
    PolkitArtifacts,
    plan_polkit,
    policy_xml,
    wrapper_script,
    writable_by_non_root,
)

_BASE_ARTIFACTS = {
    "helper_path": "/usr/local/libexec/hammunition-devctl",
    "helper_content": "helper",
    "policy_path": "/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy",
    "policy_content": "policy",
    "interpreter": "/usr/bin/python3",
}


def _stat(uid: int, mode: int = 0o40755) -> os.stat_result:
    return os.stat_result((mode, 0, 0, 1, uid, 0, 0, 0, 0, 0))


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


def test_the_plan_flags_a_stale_policy_even_when_the_helper_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falsifies an implementation that hardcodes ``policy_current = True``:
    the interpreter-moved test above only ever asserts ``helper_current is
    False`` and never writes a policy file at all, so ``policy_current`` is
    False there for the wrong reason (absence, not content). Here the helper
    matches exactly and the policy is present but stale, so only a real
    content comparison on the policy file can make this pass."""
    helper = tmp_path / "hammunition-devctl"
    policy = tmp_path / "action.policy"
    monkeypatch.setattr("hammunition.hardware.polkit.HELPER_PATH", str(helper))
    monkeypatch.setattr("hammunition.hardware.polkit.POLICY_PATH", str(policy))
    helper.write_text(wrapper_script("/usr/bin/python3"))
    policy.write_text("<policyconfig>stale, from a previous version</policyconfig>")

    artefacts = plan_polkit(interpreter="/usr/bin/python3")
    assert artefacts.helper_current is True
    assert artefacts.policy_current is False
    assert artefacts.is_noop is False


def test_is_noop_is_a_property_of_both_flags_together() -> None:
    both = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter=None,
        unsafe_package=None,
    )
    assert both.is_noop is True

    helper_only = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=False,
        unsafe_interpreter=None,
        unsafe_package=None,
    )
    assert helper_only.is_noop is False

    policy_only = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=False,
        policy_current=True,
        unsafe_interpreter=None,
        unsafe_package=None,
    )
    assert policy_only.is_noop is False


def test_needs_confirmation_when_either_check_finds_something_unsafe() -> None:
    safe = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter=None,
        unsafe_package=None,
    )
    assert safe.needs_confirmation is False

    unsafe_interpreter = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter="/opt/hammunition/.venv",
        unsafe_package=None,
    )
    assert unsafe_interpreter.needs_confirmation is True

    unsafe_package = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter=None,
        unsafe_package="/opt/hammunition",
    )
    assert unsafe_package.needs_confirmation is True


def test_writable_by_non_root_finds_the_first_offending_component_from_the_leaf_up() -> None:
    """The operator's own venv, sitting under a root-owned prefix -- the
    normal, expected shape D-056's ruling is about, not an exotic attack."""
    chain = {
        "/opt/hammunition/.venv/bin/python3": _stat(0, 0o100755),
        "/opt/hammunition/.venv/bin": _stat(0),
        "/opt/hammunition/.venv": _stat(1000),
        "/opt/hammunition": _stat(0),
        "/opt": _stat(0),
        "/": _stat(0),
    }
    offending = writable_by_non_root(
        "/opt/hammunition/.venv/bin/python3", stat_fn=lambda p: chain[p]
    )
    assert offending == "/opt/hammunition/.venv"


def test_writable_by_non_root_is_none_when_every_component_is_closed() -> None:
    chain = {
        "/opt/hammunition/.venv/bin/python3": _stat(0, 0o100755),
        "/opt/hammunition/.venv/bin": _stat(0),
        "/opt/hammunition/.venv": _stat(0),
        "/opt/hammunition": _stat(0),
        "/opt": _stat(0),
        "/": _stat(0),
    }
    offending = writable_by_non_root(
        "/opt/hammunition/.venv/bin/python3", stat_fn=lambda p: chain[p]
    )
    assert offending is None


def test_writable_by_non_root_flags_a_root_owned_but_world_writable_component() -> None:
    """Ownership alone is not the whole check: a root-owned directory that is
    group- or other-writable is exactly as replaceable as one somebody else
    owns outright."""
    chain = {
        "/opt/thing": _stat(0, 0o40777),
        "/opt": _stat(0),
        "/": _stat(0),
    }
    offending = writable_by_non_root("/opt/thing", stat_fn=lambda p: chain[p])
    assert offending == "/opt/thing"
