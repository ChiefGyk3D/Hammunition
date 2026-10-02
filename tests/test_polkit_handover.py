# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The hand-over: an installed helper that answers ``--version`` is the tray's.
D-056, amended 2026-10-02.

`hardware apply` stops writing the engine's own wrapper once one answers. The
probe is run for real here against a script in tmp_path, never against the
host's installed helper (conftest patches `installed_helper_version` for every
other test).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from hammunition.hardware import polkit

def _script(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def real_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unpatched probe, restored for the one test that runs it."""
    monkeypatch.setattr(polkit, "installed_helper_version", polkit._probe_helper_version)


def test_a_helper_that_answers_version_is_reported(tmp_path: Path, real_probe: None) -> None:
    helper = _script(tmp_path / "devctl", 'echo "hammunition-devctl 1.2.0"\n')
    assert polkit.installed_helper_version(str(helper)) == "hammunition-devctl 1.2.0"


def test_the_engines_own_helper_does_not_answer_version(tmp_path: Path, real_probe: None) -> None:
    """argparse without a version action exits 2: the engine's wrapper is not a hand-over."""
    helper = _script(tmp_path / "devctl", "echo 'usage: error' >&2\nexit 2\n")
    assert polkit.installed_helper_version(str(helper)) is None


@pytest.mark.parametrize("body", ["exit 0\n", "echo\nexit 0\n"])
def test_an_empty_answer_is_not_a_version(tmp_path: Path, real_probe: None, body: str) -> None:
    assert polkit.installed_helper_version(str(_script(tmp_path / "devctl", body))) is None


def test_a_missing_or_unrunnable_helper_is_not_a_hand_over(tmp_path: Path, real_probe: None) -> None:
    assert polkit.installed_helper_version(str(tmp_path / "nope")) is None
    plain = tmp_path / "plain"
    plain.write_text("not executable")
    assert polkit.installed_helper_version(str(plain)) is None


def test_a_helper_that_hangs_is_given_up_on(tmp_path: Path, real_probe: None) -> None:
    helper = _script(tmp_path / "devctl", "sleep 30\n")
    assert polkit.installed_helper_version(str(helper), timeout=0.3) is None


def test_the_probe_runs_the_helper_with_exactly_one_argument(
    tmp_path: Path, real_probe: None
) -> None:
    helper = _script(tmp_path / "devctl", 'echo "$#:$1"\n')
    assert polkit.installed_helper_version(str(helper)) == "1:--version"


def test_run_as_root_the_probe_drops_to_the_invoking_operator() -> None:
    """Planning must not run a user-owned tree as root (D-056's own gate comes later)."""
    assert polkit._probe_identity(euid=1000, sudo_uid="1000", sudo_gid="1000") is None
    assert polkit._probe_identity(euid=0, sudo_uid="1000", sudo_gid="1001") == (1000, 1001)
    # root with no sudo: the unprivileged account nobody, never root itself
    nobody = polkit._probe_identity(euid=0, sudo_uid=None, sudo_gid=None)
    assert nobody is not None and nobody[0] != 0


def _artifacts(**kwargs: object) -> polkit.PolkitArtifacts:
    return polkit.plan_polkit("/usr/bin/python3", **kwargs)  # type: ignore[arg-type]


def test_a_handed_over_helper_is_current_and_carries_no_interpreter_findings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    policy = tmp_path / "devctl.policy"
    policy.write_text("the tray's own policy, a different file\n")
    monkeypatch.setattr(polkit, "POLICY_PATH", str(policy))
    monkeypatch.setattr(polkit, "installed_helper_version", lambda *a, **k: "hammunition-devctl 1.0")
    art = _artifacts()
    assert art.handed_over == "hammunition-devctl 1.0"
    assert art.helper_current and art.policy_current and art.is_noop
    assert art.unsafe_interpreter is None and art.unsafe_package is None
    assert not art.must_refuse and not art.needs_confirmation


def test_a_handed_over_policy_is_never_rewritten_but_an_absent_one_is(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(polkit, "POLICY_PATH", str(tmp_path / "absent.policy"))
    monkeypatch.setattr(polkit, "installed_helper_version", lambda *a, **k: "v1")
    art = _artifacts()
    assert art.helper_current and not art.policy_current and not art.is_noop


def test_no_hand_over_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(polkit, "installed_helper_version", lambda *a, **k: None)
    art = _artifacts()
    assert art.handed_over is None
    assert art.helper_content == polkit.wrapper_script("/usr/bin/python3")
    assert os.path.exists(art.interpreter)


def test_the_probe_goes_through_the_module_name_so_a_stub_takes_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake(path: str = polkit.HELPER_PATH, timeout: float = 10.0) -> str | None:
        seen.append(path)
        return None

    monkeypatch.setattr(polkit, "installed_helper_version", fake)
    _artifacts()
    assert seen == [polkit.HELPER_PATH]
