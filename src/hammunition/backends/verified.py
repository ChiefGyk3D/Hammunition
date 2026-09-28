# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Writing into the prefix from a file that was verified somewhere else.

A fetch verifies a download into the operator's cache; the install step
copies it into a prefix only root may write. Between the two, anything
running as the operator can replace the cache entry -- with other bytes, or
with a symlink to a file only root can read, which ``shutil.copyfile`` under
root follows and publishes. So the copy that lands in the prefix is verified
itself, never assumed from the fetch:

* **Where the engine can write the destination** (an unprivileged prefix, or
  the engine already running as root) the source is opened with
  ``O_NOFOLLOW``, must be a regular file, and is hashed while it is copied
  into a mode-0600 temporary beside the destination. The temporary replaces
  the destination only when the digest matches.
* **Where it cannot** (the operator running the engine, a root-owned
  prefix) the same steps go through the runner, which escalates them: the
  source is checked not to be a symlink, copied as root into a mode-0600
  temporary, hashed *as root from that temporary* -- a file in a root-owned
  directory the operator cannot swap -- and published only on a match. A
  symlink swapped in after the check is copied into a file nobody else can
  read, fails the hash, and is removed.

The in-process copy the binary backend replaced failed with EACCES on the
field laptop's first full install (2026-09-12): a prefix under ``/usr`` is
written through the runner or not at all.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from .base import BackendError, Command, CommandRunner

_CHUNK = 1024 * 1024
ALGORITHMS = ("sha256", "md5")


def _hasher(algorithm: str) -> hashlib._Hash:
    if algorithm == "sha256":
        return hashlib.sha256()
    if algorithm == "md5":
        return hashlib.md5(usedforsecurity=False)
    raise BackendError(f"no verification by {algorithm!r}")  # pragma: no cover


def _open_regular(path: Path) -> int:
    """A read descriptor on *path*, refusing a symlink or anything not a regular file."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        if exc.errno == errno.ELOOP:  # the last component is a symlink
            raise BackendError(f"{path} is a symlink; refusing to copy it into the prefix") from exc
        raise BackendError(f"cannot open {path}: {exc.strerror or exc}") from exc
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise BackendError(f"{path} is not a regular file; refusing to copy it into the prefix")
    return fd


def digest_of(path: Path, algorithm: str = "sha256") -> str:
    """The digest of *path*, read through ``O_NOFOLLOW``."""
    fd = _open_regular(path)
    digest = _hasher(algorithm)
    with os.fdopen(fd, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PrefixWriter:
    """Installs verified files, writes small text files and removes files in a prefix.

    ``privileged`` is whether the destination needs root
    (:func:`~hammunition.backends.source.needs_root_for`); ``euid`` is who the
    engine is (None: this process). The runner is needed only when the first
    is true and the second is not root.
    """

    privileged: bool
    runner: CommandRunner | None = None
    euid: int | None = None

    @property
    def direct(self) -> bool:
        euid = os.geteuid() if self.euid is None else self.euid
        return not self.privileged or euid == 0

    def _run(self, argv: Sequence[str], description: str, *, stdin: str | None = None) -> str:
        if self.runner is None:
            raise BackendError(
                f"{description}: the destination needs root and no runner was supplied "
                f"to escalate the step"
            )
        result = self.runner.run(
            Command(argv=tuple(argv), description=description, requires_root=True, stdin=stdin)
        )
        if not result.ok:
            raise BackendError(f"{description} failed: {result.stderr.strip()[:300]}")
        return result.stdout

    @staticmethod
    def _temporary(dest: Path) -> Path:
        return dest.with_name(dest.name + f".part.{os.getpid()}")

    def install_verified(
        self, src: Path, dest: Path, *, algorithm: str, digest: str, mode: int = 0o644
    ) -> None:
        """Copy *src* to *dest*, publishing it only if its *algorithm* digest is *digest*."""
        if self.direct:
            self._install_direct(src, dest, algorithm=algorithm, digest=digest, mode=mode)
        else:
            self._install_escalated(src, dest, algorithm=algorithm, digest=digest, mode=mode)

    def _install_direct(
        self, src: Path, dest: Path, *, algorithm: str, digest: str, mode: int
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(_open_regular(src), "rb") as reader:
            self._publish(reader, src, dest, algorithm=algorithm, digest=digest, mode=mode)

    def install_stream(
        self,
        reader: IO[bytes],
        dest: Path,
        *,
        algorithm: str,
        digest: str,
        what: str,
        mode: int = 0o644,
    ) -> None:
        """Publish bytes read from *reader* (a pipe from a process running as the
        operator) at *dest*, only if their digest is *digest*. For an engine that
        can write the prefix itself: root reading an operator's file through a
        pipe the operator's own process fills never opens the operator's path."""
        if not self.direct:
            raise BackendError(
                f"{what}: a stream is published only by an engine that can write {dest}"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._publish(reader, Path(what), dest, algorithm=algorithm, digest=digest, mode=mode)

    def _publish(
        self, reader: IO[bytes], src: Path, dest: Path, *, algorithm: str, digest: str, mode: int
    ) -> None:
        temporary = self._temporary(dest)
        hasher = _hasher(algorithm)
        try:
            out = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
            )
            with os.fdopen(out, "wb") as writer:
                while chunk := reader.read(_CHUNK):
                    hasher.update(chunk)
                    writer.write(chunk)
            got = hasher.hexdigest()
            if got != digest:
                raise BackendError(
                    f"{src} does not match the {algorithm} it was verified by "
                    f"(expected {digest}, copied {got}); it changed after the fetch. "
                    f"Nothing was installed."
                )
            os.chmod(temporary, mode)
            os.replace(temporary, dest)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def _install_escalated(
        self, src: Path, dest: Path, *, algorithm: str, digest: str, mode: int
    ) -> None:
        # Early and cheap; the root-side hash below is what actually decides.
        os.close(_open_regular(src))
        temporary = self._temporary(dest)
        self._run(("install", "-d", "-m", "0755", "--", str(dest.parent)), f"Create {dest.parent}")
        self._run(
            ("install", "-m", "0600", "-T", "--", str(src), str(temporary)),
            f"Copy {src.name} into {dest.parent}",
        )
        tool = "sha256sum" if algorithm == "sha256" else "md5sum"
        try:
            out = self._run((tool, "--", str(temporary)), f"Hash the copy of {src.name} as root")
            got = out.split()[0] if out.split() else ""
            if got != digest:
                raise BackendError(
                    f"{src} does not match the {algorithm} it was verified by "
                    f"(expected {digest}, copied {got}); it changed after the fetch. "
                    f"Nothing was installed."
                )
            self._run(("chmod", f"{mode:04o}", "--", str(temporary)), f"Set the mode of {dest}")
            self._run(("mv", "-f", "-T", "--", str(temporary), str(dest)), f"Install {dest}")
        except BackendError:
            # The root-only temporary never outlives a refusal or a failed publish.
            self._run(("rm", "-f", "--", str(temporary)), f"Remove {temporary}")
            raise

    def write_text(self, dest: Path, text: str, *, mode: int = 0o644) -> None:
        """Write a small text file (a snapshot sidecar) into the prefix."""
        temporary = self._temporary(dest)
        if self.direct:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Created, never opened: O_EXCL|O_NOFOLLOW as _publish does, so a
            # link planted at the temporary's name is refused, not written through.
            try:
                out = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                )
            except OSError as exc:
                raise BackendError(
                    f"cannot create the temporary {temporary}: {exc.strerror or exc}; "
                    f"something already exists at that name"
                ) from exc
            try:
                with os.fdopen(out, "w") as writer:
                    writer.write(text)
                os.chmod(temporary, mode)
                os.replace(temporary, dest)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
            return
        self._run(("install", "-d", "-m", "0755", "--", str(dest.parent)), f"Create {dest.parent}")
        self._run(("tee", "--", str(temporary)), f"Write {dest}", stdin=text)
        self._run(("chmod", f"{mode:04o}", "--", str(temporary)), f"Set the mode of {dest}")
        self._run(("mv", "-f", "-T", "--", str(temporary), str(dest)), f"Install {dest}")

    def remove(self, paths: Sequence[Path]) -> None:
        """Remove *paths*; one already gone is not an error."""
        if self.direct:
            for path in paths:
                path.unlink(missing_ok=True)
            return
        self._run(
            ("rm", "-f", "--", *(str(p) for p in paths)), "Remove " + ", ".join(map(str, paths))
        )
