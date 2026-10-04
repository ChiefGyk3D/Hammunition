# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Directories under the operator's home are the operator's, even under sudo.

Found by review (Task 6, fix round 3): on a fresh machine ``sudo hammunition
install`` fetched first, as root, and ``Fetcher`` created
``~/.cache/hammunition/artifacts`` root-owned; the operator's own
``install -d ~/.cache/hammunition/build/osm-navit`` then failed with EACCES
and every map region failed. Root now creates a missing directory under the
operator's home one component at a time, through ``O_NOFOLLOW`` descriptors,
and hands each one it made to the operator with ``fchown``; an existing
component the operator does not own is refused by name, with the fix.

The suite runs as an ordinary user on a laptop and as real root in the CI
containers, and must mean the same thing in both ("test the matrix, not your
machine"). So nothing here reads the real uid: ``geteuid`` is pinned to 0,
the operator is a fixed non-root account (uid/gid :data:`OPERATOR_ID`) whose
home is a temporary directory, ``fstat`` reports every directory under that
home as the operator's unless a test says otherwise, and ``fchown`` is
recorded, never performed -- a real chown to 4242 is refused to a user and
would succeed for root, which is exactly the difference to keep out.
"""

from __future__ import annotations

import os
import pwd
from pathlib import Path
from typing import Any

import pytest

from hammunition.paths import OperatorDirError, ensure_operator_dir, operator_dir_problem

OPERATOR_ID = 4242


def _root_owned(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    """Make *directory* read as root-owned, as an older sudo run leaves it,
    through ``fstat`` on the descriptor the walk opened (fix round 4, item 2)."""
    real_fstat = os.fstat

    def fstat(fd: int) -> os.stat_result:
        result = real_fstat(fd)
        if os.readlink(f"/proc/self/fd/{fd}") == str(directory):
            fields = list(result)
            fields[4] = 0  # st_uid
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(os, "fstat", fstat)


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
        chowned.append((uid, gid))  # recorded; ownership is what fstat says below

    real_fstat = os.fstat

    def fstat(fd: int) -> os.stat_result:
        result = real_fstat(fd)
        where = os.readlink(f"/proc/self/fd/{fd}")
        if where == str(home) or where.startswith(str(home) + os.sep):
            fields = list(result)
            fields[4], fields[5] = OPERATOR_ID, OPERATOR_ID  # st_uid, st_gid
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(os, "fchown", fchown)
    monkeypatch.setattr(os, "fstat", fstat)
    return fake, home, chowned


def test_root_creates_missing_operator_dirs_and_hands_each_one_over(operator: Any) -> None:
    fake, home, chowned = operator
    target = home / ".cache" / "hammunition" / "artifacts"
    ensure_operator_dir(target)
    assert target.is_dir()
    # .cache, hammunition, artifacts: every directory root made, and nothing else.
    assert chowned == [(fake.pw_uid, fake.pw_gid)] * 3


def test_existing_operator_dirs_are_left_alone(operator: Any) -> None:
    _, home, chowned = operator
    (home / ".cache").mkdir()
    ensure_operator_dir(home / ".cache" / "hammunition")
    assert len(chowned) == 1


def test_a_root_owned_ancestor_is_refused_by_name_with_the_fix(
    operator: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, home, chowned = operator
    left = home / ".cache" / "hammunition"
    left.mkdir(parents=True)
    _root_owned(monkeypatch, left)
    with pytest.raises(OperatorDirError) as excinfo:
        ensure_operator_dir(left / "build" / "osm-navit")
    message = str(excinfo.value)
    assert str(left) in message
    assert f"sudo chown -R operator: {left}" in message
    assert chowned == []
    assert operator_dir_problem(left / "build", "operator") == message


def test_a_symlinked_component_is_refused_not_followed(operator: Any, tmp_path: Path) -> None:
    _, home, chowned = operator
    elsewhere = tmp_path / "sudoers.d"
    elsewhere.mkdir()
    (home / ".cache").symlink_to(elsewhere)
    with pytest.raises(OperatorDirError, match="symlink"):
        ensure_operator_dir(home / ".cache" / "hammunition")
    assert list(elsewhere.iterdir()) == []
    assert chowned == []


def test_outside_any_operator_home_it_is_a_plain_mkdir(operator: Any, tmp_path: Path) -> None:
    _, _, chowned = operator
    target = tmp_path / "srv" / "cache"
    ensure_operator_dir(target)
    assert target.is_dir() and chowned == []


def test_the_fetcher_makes_its_cache_the_operator_s(operator: Any) -> None:
    import hashlib
    import io
    from collections.abc import Iterator
    from contextlib import contextmanager
    from typing import IO

    from hammunition.fetch import Fetcher

    fake, home, chowned = operator
    body = b"region"

    class Transport:
        @contextmanager
        def open(self, url: str) -> Iterator[IO[bytes]]:
            yield io.BytesIO(body)

    cache = home / ".cache" / "hammunition" / "artifacts"
    fetcher = Fetcher(cache, transport=Transport())
    md5 = hashlib.md5(body, usedforsecurity=False).hexdigest()
    fetcher.fetch_md5("https://download.geofabrik.de/x-260101.osm.pbf", md5, expected_size=6)
    assert cache.is_dir()
    assert chowned == [(fake.pw_uid, fake.pw_gid)] * 3


def test_a_build_tree_under_sudo_leaves_the_build_root_the_operator_s(operator: Any) -> None:
    """prepare_tree and extract create the build root; it must stay the operator's."""
    from hammunition.backends.source import prepare_tree

    fake, home, chowned = operator
    build = home / ".cache" / "hammunition" / "build"
    prepare_tree(build / "wsjtx-0123abcd" / "src")
    # .cache, hammunition, build, the unit's directory: the operator's. The
    # tree itself is the build's (D-043 hands it over when installed).
    assert chowned == [(fake.pw_uid, fake.pw_gid)] * 4
    assert (build / "wsjtx-0123abcd" / "src").is_dir()


def test_a_root_owned_cache_fails_the_fetch_by_name(
    operator: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.backends import BackendError
    from hammunition.fetch import Fetcher

    _, home, _ = operator
    cache = home / ".cache"
    cache.symlink_to(home.parent)  # anything the walk refuses
    fetcher = Fetcher(cache / "hammunition" / "artifacts")
    with pytest.raises(BackendError, match="symlink"):
        fetcher.fetch_md5("https://download.geofabrik.de/x.osm.pbf", "0" * 32, expected_size=1)


def test_a_root_owned_ancestor_of_staging_fails_the_region_with_the_fix(
    operator: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fix round 3, item 1: named, not a bare EACCES from the operator's install -d."""
    from hammunition.backends.derived import DerivedBackend
    from hammunition.manifest.schema import DerivedDataInstall
    from test_regions_backend import VT, _AsOperator, _install_region, _stock, navit_manifest

    _, home, _ = operator
    left = home / ".cache" / "hammunition"
    left.mkdir(parents=True)
    _root_owned(monkeypatch, left)
    calls = _AsOperator(monkeypatch).calls
    prefix = tmp_path / "prefix"
    _install_region(prefix, VT)
    manifest = navit_manifest()
    backend = DerivedBackend(
        prefix=prefix,
        files=[VT],
        staging=left / "build" / "osm-navit",
        stock=_stock(tmp_path),
        euid=0,
        owner="operator",
        privileged=False,
    )
    block = manifest.install[0].install
    assert isinstance(block, DerivedDataInstall)
    steps: list[Any] = backend.steps(manifest, block)
    convert = next(s for s in steps if s.kind == "convert")
    assert "FAILED" in convert.perform()
    assert f"sudo chown -R operator: {left}" in backend.ledger.failed[VT.slug]
    assert calls == []


# ---------------------------------------------------------------------------
# Fix round 4: nothing is removed before the parent is proven the operator's
# ---------------------------------------------------------------------------


def _victim(tmp_path: Path, home: Path) -> tuple[Path, Path]:
    """The reviewer's reproduction: build/unit-abc -> a victim holding src/."""
    victim = tmp_path / "victim"
    (victim / "src").mkdir(parents=True)
    (victim / "src" / "precious").write_text("keep me\n")
    (victim / "src.unpack").mkdir()
    build = home / ".cache" / "hammunition" / "build"
    build.mkdir(parents=True)
    (build / "unit-abc").symlink_to(victim)
    return build / "unit-abc" / "src", victim


def test_prepare_tree_refuses_a_symlinked_parent_before_removing_anything(
    operator: Any, tmp_path: Path
) -> None:
    from hammunition.backends import BackendError
    from hammunition.backends.source import prepare_tree

    _, home, _ = operator
    destination, victim = _victim(tmp_path, home)
    with pytest.raises(BackendError, match="symlink"):
        prepare_tree(destination)
    assert (victim / "src" / "precious").read_text() == "keep me\n"


def test_extract_refuses_a_symlinked_parent_before_removing_anything(
    operator: Any, tmp_path: Path
) -> None:
    import tarfile

    from hammunition.backends import BackendError
    from hammunition.backends.source import extract

    _, home, _ = operator
    destination, victim = _victim(tmp_path, home)
    archive = tmp_path / "a.tar"
    with tarfile.open(archive, "w"):
        pass
    with pytest.raises(BackendError, match="symlink"):
        extract(archive, destination)
    assert (victim / "src" / "precious").read_text() == "keep me\n"
    assert (victim / "src.unpack").is_dir()


def test_prepare_tree_clears_an_existing_tree_through_the_parent(operator: Any) -> None:
    from hammunition.backends.source import prepare_tree

    _, home, _ = operator
    src = home / ".cache" / "hammunition" / "build" / "unit-abc" / "src"
    (src / "old").mkdir(parents=True)
    (src / "old" / "stale.o").write_bytes(b"x")
    assert prepare_tree(src).startswith("cleared and recreated")
    assert src.is_dir() and list(src.iterdir()) == []


def test_a_directory_that_appears_mid_walk_is_a_named_refusal(
    operator: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 4, item 4: EEXIST from a race is OperatorDirError, not a raw OSError."""
    _, home, _ = operator

    def mkdir(*args: Any, **kwargs: Any) -> None:
        raise FileExistsError(17, "File exists")

    monkeypatch.setattr(os, "mkdir", mkdir)
    with pytest.raises(OperatorDirError, match=r"\.cache"):
        ensure_operator_dir(home / ".cache" / "hammunition")


def test_a_failed_fchown_leaks_no_descriptor(
    operator: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 4, item 3."""
    _, home, _ = operator

    def fchown(fd: int, uid: int, gid: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "fchown", fchown)
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(OperatorDirError, match=r"\.cache"):
        ensure_operator_dir(home / ".cache" / "hammunition")
    assert len(os.listdir("/proc/self/fd")) == before
