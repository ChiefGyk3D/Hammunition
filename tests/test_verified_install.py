# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Copying a verified cache file into the prefix re-verifies it on the way.

The cache is the operator's; the prefix is root's. A cache entry verified at
fetch time and copied later by root with ``shutil.copyfile`` follows a
symlink put there in between and copies whatever it points at, unverified.
:class:`PrefixWriter` opens the source with ``O_NOFOLLOW``, hashes while it
copies, and replaces the destination only when the digest matches. Where the
engine cannot write the prefix itself it goes through the runner, copies
into a root-only temporary, hashes *that* as root, and only then publishes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hammunition.backends import BackendError, SubprocessRunner
from hammunition.backends.verified import PrefixWriter

BODY = b"verified bytes\n"
SHA = hashlib.sha256(BODY).hexdigest()
MD5 = hashlib.md5(BODY, usedforsecurity=False).hexdigest()


def _writers() -> list[PrefixWriter]:
    # In-process, and through the runner as though escalation were needed:
    # SubprocessRunner(euid=0) adds no sudo, so the privileged path's argv
    # runs as the test user.
    return [
        PrefixWriter(privileged=False),
        PrefixWriter(privileged=True, euid=1000, runner=SubprocessRunner(euid=0)),
    ]


@pytest.mark.parametrize("writer", _writers(), ids=["direct", "runner"])
@pytest.mark.parametrize(("algorithm", "digest"), [("sha256", SHA), ("md5", MD5)])
def test_a_matching_file_is_installed(
    tmp_path: Path, writer: PrefixWriter, algorithm: str, digest: str
) -> None:
    src = tmp_path / "cache" / "x"
    src.parent.mkdir()
    src.write_bytes(BODY)
    dest = tmp_path / "prefix" / "data" / "x"
    writer.install_verified(src, dest, algorithm=algorithm, digest=digest)
    assert dest.read_bytes() == BODY
    assert dest.stat().st_mode & 0o777 == 0o644
    assert list(dest.parent.glob("*.part*")) == []


@pytest.mark.parametrize("writer", _writers(), ids=["direct", "runner"])
def test_a_symlinked_cache_file_is_refused_and_nothing_installed(
    tmp_path: Path, writer: PrefixWriter
) -> None:
    secret = tmp_path / "secret"
    secret.write_bytes(BODY)  # same bytes: only the link itself gives it away
    src = tmp_path / "cache" / "x"
    src.parent.mkdir()
    src.symlink_to(secret)
    dest = tmp_path / "prefix" / "x"
    with pytest.raises(BackendError, match="symlink"):
        writer.install_verified(src, dest, algorithm="sha256", digest=SHA)
    assert not dest.exists()
    assert not dest.parent.exists() or list(dest.parent.iterdir()) == []


@pytest.mark.parametrize("writer", _writers(), ids=["direct", "runner"])
def test_a_file_changed_since_it_was_verified_is_refused(
    tmp_path: Path, writer: PrefixWriter
) -> None:
    src = tmp_path / "x"
    src.write_bytes(b"swapped after the fetch verified it\n")
    dest = tmp_path / "prefix" / "x"
    with pytest.raises(BackendError, match="does not match"):
        writer.install_verified(src, dest, algorithm="sha256", digest=SHA)
    assert not dest.exists()
    assert not dest.parent.exists() or list(dest.parent.iterdir()) == []


@pytest.mark.parametrize("writer", _writers(), ids=["direct", "runner"])
def test_text_and_removal(tmp_path: Path, writer: PrefixWriter) -> None:
    dest = tmp_path / "prefix" / "x.source"
    writer.write_text(dest, "260101\n")
    assert dest.read_text() == "260101\n"
    assert dest.stat().st_mode & 0o777 == 0o644
    other = tmp_path / "prefix" / "y"
    other.write_bytes(b"y")
    writer.remove([dest, other, tmp_path / "prefix" / "absent"])
    assert not dest.exists() and not other.exists()


def test_the_privileged_path_without_a_runner_is_refused(tmp_path: Path) -> None:
    src = tmp_path / "x"
    src.write_bytes(BODY)
    with pytest.raises(BackendError, match="runner"):
        PrefixWriter(privileged=True, euid=1000).install_verified(
            src, tmp_path / "d", algorithm="sha256", digest=SHA
        )
