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
    WritabilityFinding,
    WritabilityRisk,
    describe_refusal,
    plan_polkit,
    policy_xml,
    wrapper_script,
    writable_by_non_root,
    writable_including_symlink_target,
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


def _owned(path: str) -> WritabilityFinding:
    return WritabilityFinding(path, WritabilityRisk.OWNED_BY_NON_ROOT)


def _writable(path: str) -> WritabilityFinding:
    return WritabilityFinding(path, WritabilityRisk.GROUP_OR_OTHER_WRITABLE)


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


def test_needs_confirmation_true_only_for_the_owned_by_non_root_class() -> None:
    """Fix round 2: `needs_confirmation` must fire for the confirmable class
    (OWNED_BY_NON_ROOT) and never for the refused class
    (GROUP_OR_OTHER_WRITABLE) -- round 1 collapsed the two into one
    boolean and broke the project's own documented install."""
    safe = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter=None,
        unsafe_package=None,
    )
    assert safe.needs_confirmation is False
    assert safe.must_refuse is False

    owned_interpreter = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter=_owned("/opt/hammunition/.venv"),
        unsafe_package=None,
    )
    assert owned_interpreter.needs_confirmation is True
    assert owned_interpreter.must_refuse is False
    assert owned_interpreter.confirmable_paths == ["/opt/hammunition/.venv"]

    owned_package = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter=None,
        unsafe_package=_owned("/opt/hammunition"),
    )
    assert owned_package.needs_confirmation is True
    assert owned_package.must_refuse is False
    assert owned_package.confirmable_paths == ["/opt/hammunition"]


def test_must_refuse_true_only_for_the_group_or_other_writable_class() -> None:
    writable_interpreter = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter=_writable("/opt/hammunition/.venv"),
        unsafe_package=None,
    )
    assert writable_interpreter.must_refuse is True
    assert writable_interpreter.needs_confirmation is False
    assert writable_interpreter.refusing_paths == ["/opt/hammunition/.venv"]

    writable_package = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter=None,
        unsafe_package=_writable("/opt/hammunition"),
    )
    assert writable_package.must_refuse is True
    assert writable_package.needs_confirmation is False
    assert writable_package.refusing_paths == ["/opt/hammunition"]


def test_must_refuse_wins_when_both_classes_are_present_at_once() -> None:
    """A tree can have one component merely non-root-owned and another,
    elsewhere in the same chain, group-writable. The severe fact must never
    be silently outvoted by the milder one."""
    both = PolkitArtifacts(
        **_BASE_ARTIFACTS,
        helper_current=True,
        policy_current=True,
        unsafe_interpreter=_owned("/opt/hammunition/.venv"),
        unsafe_package=_writable("/opt/hammunition"),
    )
    assert both.must_refuse is True
    assert both.needs_confirmation is True  # both facts are still true and disclosed
    assert both.refusing_paths == ["/opt/hammunition"]
    assert both.confirmable_paths == ["/opt/hammunition/.venv"]


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
    assert offending == _owned("/opt/hammunition/.venv")


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
    owns outright -- and it is the severe class, not the confirmable one."""
    chain = {
        "/opt/thing": _stat(0, 0o40777),
        "/opt": _stat(0),
        "/": _stat(0),
    }
    offending = writable_by_non_root("/opt/thing", stat_fn=lambda p: chain[p])
    assert offending == _writable("/opt/thing")


def test_writable_by_non_root_group_or_other_writable_wins_over_a_nearer_owned_component() -> None:
    """Fix round 2: the two-pass scan must not stop at the first (leaf-most)
    finding regardless of class. A merely non-root-owned leaf must not mask
    a group-writable component further up the same chain -- the severe fact
    always wins, wherever it sits."""
    chain = {
        "/opt/hammunition/.venv/bin/python3": _stat(1000, 0o100755),
        "/opt/hammunition/.venv/bin": _stat(1000),
        "/opt/hammunition/.venv": _stat(1000),
        "/opt/hammunition": _stat(0, 0o40777),  # group/other-writable, further up
        "/opt": _stat(0),
        "/": _stat(0),
    }
    offending = writable_by_non_root(
        "/opt/hammunition/.venv/bin/python3", stat_fn=lambda p: chain[p]
    )
    assert offending == _writable("/opt/hammunition")


def test_writable_by_non_root_treats_an_unstattable_component_as_the_severe_class() -> None:
    """A component that cannot be stat'd cannot be proven safe either, and
    the conservative answer is the one that gets refused, not the one that
    gets merely confirmed."""

    def raising(path: str) -> os.stat_result:
        raise OSError("permission denied")

    offending = writable_by_non_root("/opt/hammunition/.venv/bin/python3", stat_fn=raising)
    assert offending is not None
    assert offending.risk is WritabilityRisk.GROUP_OR_OTHER_WRITABLE
    assert offending.unstatable is True, (
        "fix round 3, item 6: an unstat'd component is a different fact from "
        "an actually-writable one, and must be flagged as such"
    )


def test_writable_by_non_root_a_real_writable_component_is_not_flagged_unstatable() -> None:
    """The mirror of the test above: a component that really is group- or
    other-writable (and stat'd successfully) must not carry the `unstatable`
    flag, or `describe_refusal` would understate it."""
    chain = {
        "/opt/thing": _stat(0, 0o40777),
        "/opt": _stat(0),
        "/": _stat(0),
    }
    offending = writable_by_non_root("/opt/thing", stat_fn=lambda p: chain[p])
    assert offending is not None
    assert offending.unstatable is False


def test_describe_refusal_distinguishes_writable_from_unstatable() -> None:
    """Fix round 3, item 6: 'is writable by any local account' is simply
    false of a component that could not be read at all -- different fact,
    different sentence."""
    writable = WritabilityFinding("/opt/thing", WritabilityRisk.GROUP_OR_OTHER_WRITABLE)
    unstatable = WritabilityFinding(
        "/opt/other", WritabilityRisk.GROUP_OR_OTHER_WRITABLE, unstatable=True
    )

    writable_text = describe_refusal([writable])
    assert "writable" in writable_text.lower()
    assert "could not be checked" not in writable_text.lower()

    unstatable_text = describe_refusal([unstatable])
    assert "could not be checked" in unstatable_text.lower()
    assert "is writable by any local account" not in unstatable_text


_SYMLINK_BYPASS_TREE = {
    # The direct (unresolved) chain from the symlink itself. `os.stat`
    # follows a symlink, so the leaf entry carries the target's own (clean)
    # attributes -- the *directory holding the symlink* is the one that is
    # actually unsafe here, one level up.
    "/opt/hamvenv/bin/python3": _stat(0, 0o100755),
    "/opt/hamvenv/bin": _stat(0, 0o40777),  # the bypass: world-writable
    "/opt/hamvenv": _stat(0),
    "/opt": _stat(0),
    "/": _stat(0),
    # The resolved chain: a clean target with a clean chain all the way up,
    # which is exactly why checking only this side missed the bypass.
    "/usr/bin/python3.13": _stat(0, 0o100755),
    "/usr/bin": _stat(0),
    "/usr": _stat(0),
}


def _symlink_bypass_realpath(path: str) -> str:
    """Stands in for :func:`os.path.realpath`: the one path this tree cares
    about resolves through the symlink; anything else (the calls
    ``writable_by_non_root`` makes against an already-resolved path) is the
    identity, matching what ``os.path.realpath`` does to a path with no
    further symlinks to follow."""
    if path == "/opt/hamvenv/bin/python3":
        return "/usr/bin/python3.13"
    return path


def test_writable_including_symlink_target_catches_a_writable_symlink_directory() -> None:
    """Fix round 3, item 1 (Critical) / fix round 4: `plan_polkit` and the
    devctl runtime check both checked only the *resolved* interpreter path,
    but the wrapper ``exec``s the *unresolved* one. A world-writable
    directory holding a symlink to an otherwise root-owned, clean-chain
    target disabled both gates completely: resolving first hides exactly
    the directory an attacker would use to retarget the symlink itself.

    Fix round 4: the round-3 version of this test built the tree for real
    under `tmp_path`, symlinked to the real `/usr/bin/python3.13`, and
    skipped if that path did not exist. That made the test's result a
    property of the machine running it (root-owned there, uid 65534 inside
    an unprivileged user namespace, unknown-and-varying across the seven
    target containers) rather than of the code -- exactly what CLAUDE.md's
    "test the matrix, not your machine" forbids. Both `stat_fn` and
    `realpath_fn` are injected here, so nothing touches the real filesystem
    and the tree's shape is the only thing under test.
    """
    stat_fn = _SYMLINK_BYPASS_TREE.__getitem__

    # The regression, demonstrated directly: checking only the resolved path
    # finds nothing wrong, because the target's own chain really is clean.
    assert (
        writable_by_non_root(_symlink_bypass_realpath("/opt/hamvenv/bin/python3"), stat_fn=stat_fn)
        is None
    )

    # The fix: the union also checks the unresolved path and catches the
    # writable directory the symlink itself sits in.
    finding = writable_including_symlink_target(
        "/opt/hamvenv/bin/python3", stat_fn=stat_fn, realpath_fn=_symlink_bypass_realpath
    )
    assert finding is not None
    assert finding.risk is WritabilityRisk.GROUP_OR_OTHER_WRITABLE
    assert finding.path == "/opt/hamvenv/bin"


def test_writable_including_symlink_target_falsification_resolved_only_misses_it() -> None:
    """Falsifies the exact round-3 fix: a version of the union that checks
    only the resolved path (what every call site did before fix round 3)
    must be shown finding nothing, over the same synthetic tree the test
    above proves the real fix catches."""
    stat_fn = _SYMLINK_BYPASS_TREE.__getitem__

    def resolved_only(path: str) -> WritabilityFinding | None:
        return writable_by_non_root(_symlink_bypass_realpath(path), stat_fn=stat_fn)

    assert resolved_only("/opt/hamvenv/bin/python3") is None, (
        "this is the bug fix round 3 closes, demonstrated directly: a "
        "resolved-only check must find nothing on a tree the real fix flags"
    )
