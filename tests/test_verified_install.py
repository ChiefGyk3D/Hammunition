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
import os
from pathlib import Path

import pytest

from hammunition.backends import BackendError, Command, CommandResult, SubprocessRunner
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


class _FailingOn:
    """Runs commands as the test user, failing the first whose argv[0] is *tool*."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        self.inner = SubprocessRunner(euid=0)

    def run(self, command: Command) -> CommandResult:
        if command.argv[0] == self.tool:
            return CommandResult(command.argv, 1, "", f"{self.tool}: refused")
        return self.inner.run(command)


@pytest.mark.parametrize("tool", ["chmod", "mv"])
def test_a_failed_publish_removes_the_root_temporary(tmp_path: Path, tool: str) -> None:
    """Fix round 2, item 3."""
    src = tmp_path / "x"
    src.write_bytes(BODY)
    dest = tmp_path / "prefix" / "x"
    writer = PrefixWriter(privileged=True, euid=1000, runner=_FailingOn(tool))
    with pytest.raises(BackendError, match=tool):
        writer.install_verified(src, dest, algorithm="sha256", digest=SHA)
    assert list(dest.parent.iterdir()) == []


def test_a_failed_mkdir_does_not_leak_the_source_descriptor(tmp_path: Path) -> None:
    """Fix round 2, item 3."""
    src = tmp_path / "x"
    src.write_bytes(BODY)
    blocker = tmp_path / "file"
    blocker.write_bytes(b"not a directory")
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(OSError):
        PrefixWriter(privileged=False).install_verified(
            src, blocker / "sub" / "x", algorithm="sha256", digest=SHA
        )
    assert len(os.listdir("/proc/self/fd")) == before


def test_write_text_never_writes_through_a_planted_temporary(tmp_path: Path) -> None:
    """Final review, item 3: the direct path creates its temporary O_EXCL|O_NOFOLLOW."""
    victim = tmp_path / "victim"
    victim.write_text("keep\n")
    dest = tmp_path / "prefix" / "x.source"
    dest.parent.mkdir()
    dest.with_name(dest.name + f".part.{os.getpid()}").symlink_to(victim)
    with pytest.raises(BackendError, match="temporary"):
        PrefixWriter(privileged=False).write_text(dest, "260101\n")
    assert victim.read_text() == "keep\n"
    assert not dest.exists()


# ---------------------------------------------------------------------------
# link(): a symbolic link to a sibling name (D-061, amended 2026-10-02:
# Signal-Server reads SPLAT's terrain files under its own names).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("writer", _writers(), ids=["direct", "runner"])
def test_link_makes_a_relative_link_to_a_sibling(tmp_path: Path, writer: PrefixWriter) -> None:
    target = tmp_path / "prefix" / "36:37:116:117-hd.sdf.bz2"
    target.parent.mkdir()
    target.write_bytes(BODY)
    dest = target.with_name("36_37_116_117-hd.sdf.bz2")
    writer.link(dest, target.name)
    assert dest.is_symlink() and os.readlink(dest) == target.name
    assert dest.read_bytes() == BODY
    writer.link(dest, target.name)  # idempotent: replaced in place
    assert os.readlink(dest) == target.name
    assert sorted(p.name for p in dest.parent.iterdir()) == sorted([target.name, dest.name])


@pytest.mark.parametrize("writer", _writers(), ids=["direct", "runner"])
@pytest.mark.parametrize("target", ["../etc/passwd", "/etc/passwd", "sub/x", "", ".", ".."])
def test_link_refuses_anything_but_a_bare_sibling_name(
    tmp_path: Path, writer: PrefixWriter, target: str
) -> None:
    dest = tmp_path / "prefix" / "x"
    dest.parent.mkdir()
    with pytest.raises(BackendError, match="sibling"):
        writer.link(dest, target)
    assert list(dest.parent.iterdir()) == []


@pytest.mark.parametrize("writer", _writers(), ids=["direct", "runner"])
def test_link_replaces_a_regular_file_and_remove_takes_the_link_only(
    tmp_path: Path, writer: PrefixWriter
) -> None:
    target = tmp_path / "prefix" / "a.sdf.bz2"
    target.parent.mkdir()
    target.write_bytes(BODY)
    dest = target.with_name("b.sdf.bz2")
    dest.write_bytes(b"stale")
    writer.link(dest, target.name)
    assert dest.is_symlink()
    writer.remove([dest])
    assert not dest.is_symlink() and target.read_bytes() == BODY
