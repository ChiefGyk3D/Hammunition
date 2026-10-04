# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The suite cannot reach the operator's own files.

Twice on 2026-10-03 a test run rewrote the maintainer's real station file:
once through a script whose overridden HOME never reached the engine, once
through ``unshare -r pytest`` with ``USER`` still set, where euid is 0 and
``paths.owner_aware_dir`` resolves the *owner's* passwd home.

Falsified: with the ``_isolated_operator_environment`` fixture in
``conftest.py`` disabled, (a) and (b) fail on a normal run, and (c) fails
under a faked euid 0 because ``pwd`` hands back the real home.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import conftest
from hammunition import paths, station

_BAD_VARS = ("USER", "SUDO_USER", "LOGNAME")


def _under(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def _not_real(path: Path) -> bool:
    return not any(_under(path, h) for h in conftest.REAL_HOMES)


def test_resolved_paths_lie_under_the_fixture_root() -> None:
    root = conftest.session_root()
    for p in (
        station.config_path(),
        paths.state_dir(),
        paths.artifact_cache_dir(),
        paths.build_root(),
        paths.data_dir(),
        paths.user_config_base(),
    ):
        assert _under(p, root), f"{p} is outside the isolated root {root}"
        assert _not_real(p), f"{p} is under a real home"


def test_environment_names_no_account() -> None:
    present = [v for v in _BAD_VARS if v in os.environ]
    assert not present, f"{present} set; owner detection could find a real account"


@pytest.mark.parametrize("owner", ["root", conftest.REAL_LOGIN])
def test_euid_zero_never_resolves_a_real_home(owner: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    root = conftest.session_root()
    for p in (
        station.config_path(owner=owner),
        paths.state_dir(owner=owner),
        paths.artifact_cache_dir(owner=owner),
        paths.user_config_base(owner=owner),
    ):
        assert _not_real(p), f"owner={owner!r} resolved {p}, a real home"
        assert _under(p, root), f"owner={owner!r} resolved {p}, outside {root}"
