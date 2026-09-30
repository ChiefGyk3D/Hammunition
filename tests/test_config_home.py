# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Config files in the operator's home: a manifest's ``~/`` path.

gpredict reads its ground station from ``~/.config/Gpredict`` and tlf its
``logcfg.dat`` from the directory it is started in, so two of the Q-022 #1
blocks cannot live under ``/etc``. ``~/`` is resolved against the *operator*
(the account the run is on behalf of), never ``$HOME``, which sudo resets to
``/root``; and when the engine is root it writes there the way it creates the
operator's cache directories -- through ``O_NOFOLLOW`` descriptors from the
home down, handing what it writes to the operator.

As in ``test_operator_dirs.py``, nothing reads the real uid: ``geteuid`` is
pinned, the operator is a fixed non-root account whose home is a temporary
directory, ``fstat`` reports that home as theirs, and ``fchown`` is recorded,
never performed.
"""

from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import BackendError  # noqa: E402
from hammunition.execute import write_operator_config  # noqa: E402
from hammunition.manifest.schema import ConfigFile, PackageManifest  # noqa: E402
from hammunition.plan import _plan_config  # noqa: E402
from hammunition.station import Station  # noqa: E402

OPERATOR_ID = 4242


@pytest.fixture
def operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    home = tmp_path / "home" / "operator"
    home.mkdir(parents=True)
    fake = pwd.struct_passwd(("operator", "x", OPERATOR_ID, OPERATOR_ID, "", str(home), "/bin/sh"))
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: fake)
    monkeypatch.setattr(pwd, "getpwall", lambda: [fake])
    chowned: list[tuple[int, int]] = []

    def fchown(fd: int, uid: int, gid: int) -> None:
        chowned.append((uid, gid))

    real_fstat = os.fstat

    def fstat(fd: int) -> os.stat_result:
        result = real_fstat(fd)
        where = os.readlink(f"/proc/self/fd/{fd}")
        if where == str(home) or where.startswith(str(home) + os.sep):
            fields = list(result)
            fields[4], fields[5] = OPERATOR_ID, OPERATOR_ID
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(os, "fchown", fchown)
    monkeypatch.setattr(os, "fstat", fstat)
    return fake, home, chowned


def _manifest(path: str) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "fixture",
            "version": "1.0",
            "summary": "A package whose config lives in the operator's home",
            "categories": ["packet"],
            "install": [{"install": {"method": "apt", "packages": ["fixture"]}}],
            "config_files": [{"path": path, "template": "CALL={station.callsign}\n"}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for gpredict and tlf, which read from home.",
                "why_you_want_it": "To exercise the ~/ path resolution.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


# ---------------------------------------------------------------------------
# The schema: absolute or ~/, and a file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/etc/x.conf", "~/.config/App/x.qth", "~/tlf/logcfg.dat"])
def test_absolute_and_home_paths_are_accepted(path: str) -> None:
    assert ConfigFile(path=path, template="x").path == path


@pytest.mark.parametrize(
    "path", ["etc/x.conf", "~operator/x", "~/", "~/../etc/passwd", "/etc/", "~/a/~/b", "$HOME/x"]
)
def test_anything_else_is_refused(path: str) -> None:
    with pytest.raises(ValueError, match="config path"):
        ConfigFile(path=path, template="x")


# ---------------------------------------------------------------------------
# The plan: resolved against the operator, or deferred
# ---------------------------------------------------------------------------


def test_a_home_path_is_resolved_against_the_operator(tmp_path: Path) -> None:
    writable, deferred = _plan_config(
        _manifest("~/.config/App/x.conf"), Station(callsign="N0TST"), tmp_path
    )
    assert not deferred
    assert writable[0][1].path == str(tmp_path / ".config" / "App" / "x.conf")


def test_with_no_operator_a_home_path_is_deferred_not_written_to_root() -> None:
    writable, deferred = _plan_config(_manifest("~/x.conf"), Station(callsign="N0TST"), None)
    assert not writable
    assert "operator's home" in deferred[0].why
    assert "--user" in deferred[0].remedy


def test_an_etc_path_ignores_the_home(tmp_path: Path) -> None:
    writable, _ = _plan_config(_manifest("/etc/x.conf"), Station(callsign="N0TST"), tmp_path)
    assert writable[0][1].path == "/etc/x.conf"


# ---------------------------------------------------------------------------
# Root writing into the operator's home
# ---------------------------------------------------------------------------


def test_root_writes_the_file_and_hands_it_over(operator: Any) -> None:
    fake, home, chowned = operator
    target = home / ".config" / "App" / "x.conf"
    outcome = write_operator_config(target, "CALL=N0TST", 0o644, append=False, backup=True)
    assert target.read_text() == "CALL=N0TST\n"
    assert oct(target.stat().st_mode & 0o777) == "0o644"
    # .config and App were created and handed over, then the file itself.
    assert chowned == [(fake.pw_uid, fake.pw_gid)] * 3
    assert "operator's" in outcome


def test_an_existing_file_is_backed_up_once(operator: Any) -> None:
    _, home, _ = operator
    target = home / "x.conf"
    target.write_text("mine\n")
    write_operator_config(target, "first", 0o644, append=False, backup=True)
    write_operator_config(target, "second", 0o644, append=False, backup=True)
    assert (home / "x.conf.hammunition-backup").read_text() == "mine\n"
    assert target.read_text() == "second\n"


def test_a_symlinked_file_is_refused_not_followed(operator: Any, tmp_path: Path) -> None:
    _, home, chowned = operator
    victim = tmp_path / "shadow"
    victim.write_text("root's\n")
    (home / "x.conf").symlink_to(victim)
    with pytest.raises(BackendError, match="not a regular file"):
        write_operator_config(home / "x.conf", "CALL=N0TST", 0o644, append=False, backup=True)
    assert victim.read_text() == "root's\n"
    assert chowned == []


def test_a_symlinked_directory_is_refused_not_followed(operator: Any, tmp_path: Path) -> None:
    _, home, chowned = operator
    elsewhere = tmp_path / "etc"
    elsewhere.mkdir()
    (home / ".config").symlink_to(elsewhere)
    with pytest.raises(BackendError, match="symlink"):
        write_operator_config(
            home / ".config" / "App" / "x.conf", "CALL=N0TST", 0o644, append=False, backup=True
        )
    assert list(elsewhere.iterdir()) == []
    assert chowned == []


def test_not_root_it_is_the_ordinary_write(tmp_path: Path) -> None:
    target = tmp_path / "x.conf"
    write_operator_config(target, "CALL=N0TST", 0o644, append=False, backup=True)
    assert target.read_text() == "CALL=N0TST\n"


def test_the_plan_step_under_root_is_the_operator_write(operator: Any) -> None:
    """config_steps picks the root-safe writer for a path in a home, and the
    dry run says whose the file will be."""
    from hammunition.distro import Target
    from hammunition.execute import config_steps
    from hammunition.plan import InstallPlan, PlannedPackage

    _, home, _ = operator
    manifest = _manifest("~/.config/App/x.conf")
    writable, _ = _plan_config(manifest, Station(callsign="N0TST"), home)
    plan = InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        packages=(
            PlannedPackage(
                manifest=manifest,
                block=manifest.install[0],
                apt_packages=(),
                already_installed=("fixture",),
            ),
        ),
        config_files=tuple(writable),
    )
    (step,) = config_steps(plan)
    assert "handed to operator" in step.detail
    step.perform()
    assert (home / ".config" / "App" / "x.conf").read_text() == "CALL=N0TST\n"
