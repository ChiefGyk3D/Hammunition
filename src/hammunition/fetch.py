# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fetching a remote artifact, and refusing to hand back one that is not what
the manifest said it would be.

CLAUDE.md, Security requirements: *"Verify checksums/signatures for any non-apt
source; refuse to install if absent."* The schema already makes the absent case
unrepresentable — :class:`~hammunition.manifest.schema.RemoteArtifact` requires
``sha256`` — so this module's job is the other half: that a file which fails
verification never becomes usable by anything downstream.

**Content-addressed by the expected digest.** A verified artifact lands at
``<cache>/<sha256>-<name>``. The path encodes the expectation, so a file sitting
at that path can only ever be content that matched it. There is no metadata
sidecar to fall out of step with the file, and two manifests naming the same
bytes share one entry.

**Nothing unverified is ever at the final path.** The download streams to a
temporary file in the same directory, is hashed as it is written, and is moved
into place with :func:`os.replace` only after the digest matches. A mismatch
deletes the temporary file and raises. This ordering is the whole point: a
verify-after-install, or a verify that leaves the bad file behind for a later
run to find, would satisfy the letter of the requirement and none of it.

**A cached file is re-verified every time, not trusted for having been
verified once.** Re-hashing costs a disk read and catches a cache that was
corrupted, truncated by a full disk, or edited between runs.

**The network is a seam.** :class:`Transport` is the only thing here that
touches it, so the tests inject bytes rather than reaching the internet — and
the suite blocks non-loopback sockets to keep that honest rather than merely
intended.

Two things this deliberately does not do. It does not shell out to ``curl`` or
``wget``: an argv is not a shell, but a redirect-following downloader that
writes where it is told is a larger surface than :mod:`urllib` with the file
handle in our hands. And it does not verify signatures yet —
``signature_url``/``signing_key_fingerprint`` are carried in the schema and are
not read here, so a manifest supplying them gets no more checking than one that
does not. That gap is named rather than papered over; see
:func:`signature_gap`.
"""

from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from hammunition.backends import BackendError
from hammunition.manifest.schema import RemoteArtifact
from hammunition.paths import artifact_cache_dir

__all__ = [
    "DEFAULT_MAX_BYTES",
    "FetchResult",
    "Fetcher",
    "Transport",
    "UrllibTransport",
    "VerificationError",
    "signature_gap",
]

#: Refuse a download larger than this. A source tarball is single-digit MB and
#: the largest artifact in the catalog is well under this; the limit exists so
#: a redirect to something enormous fills a bounded amount of disk rather than
#: whatever is free. Raise it per-fetch if a genuine artifact ever needs it.
DEFAULT_MAX_BYTES = 512 * 1024 * 1024

_CHUNK = 64 * 1024


class VerificationError(BackendError):
    """A fetched artifact did not match the digest the manifest declared.

    A subclass of :class:`~hammunition.backends.BackendError` so it is fatal by
    the same rule everything else is: D-016 forbids continuing past a failure,
    and this is the failure it would be worst to continue past.
    """


class Transport(Protocol):
    """Where bytes come from. The only part of this module that is network."""

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:  # pragma: no cover - protocol
        """Yield a readable binary stream for *url*, or raise BackendError."""
        ...


ALLOWED_SCHEMES = frozenset({"http", "https"})


class UrllibTransport:
    """The real one: HTTPS (and HTTP) via :mod:`urllib`, and nothing else.

    **Built with :class:`~urllib.request.OpenerDirector` rather than
    :func:`~urllib.request.build_opener`, and that is not a style choice.**
    ``build_opener`` adds urllib's *default* handler set — ``FileHandler``,
    ``FTPHandler``, ``DataHandler`` — to whatever you pass it; the argument list
    only supplements or overrides. An opener built the obvious way therefore
    serves ``file:///etc/anything`` happily, so a redirect off an ordinary https
    URL could hand this module the contents of a local file and it would hash it,
    cache it, and report a successful fetch. Constructing the director directly
    and adding only the HTTP handlers is what actually closes that door. (This
    was not theoretical: the first version of this class used ``build_opener``
    and ``test_the_real_transport_has_no_handler_for_file_urls`` caught it.)

    With no handler registered for a scheme the director returns ``None``
    instead of raising, which would surface later as an attribute error on
    something that is not a stream, so the scheme is also checked up front and
    a ``None`` response is refused by name. Three layers — schema, scheme
    check, handler set — because the redirect chain is the one the schema
    cannot see.

    Plain ``http`` is permitted because the digest, not the transport, is what
    makes an artifact trustworthy here: a tampered download over TLS and one
    over cleartext are both caught by the same comparison. TLS still hides
    *which* artifact was fetched, so https is preferred in manifests.
    """

    def __init__(self, *, timeout: float = 60.0) -> None:
        self.timeout = timeout
        director = urllib.request.OpenerDirector()
        for handler in (
            urllib.request.HTTPHandler(),
            urllib.request.HTTPSHandler(),
            urllib.request.HTTPRedirectHandler(),
            urllib.request.HTTPErrorProcessor(),
            urllib.request.HTTPDefaultErrorHandler(),
        ):
            director.add_handler(handler)
        self._opener = director

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:
        scheme = urllib.parse.urlsplit(url).scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            raise BackendError(
                f"refusing to fetch {url!r}: only {'/'.join(sorted(ALLOWED_SCHEMES))} "
                f"are fetchable. A 'file' or 'ftp' URL — reached directly or through "
                f"a redirect — is not a download and will not be treated as one."
            )
        request = urllib.request.Request(url, headers={"User-Agent": "hammunition"})
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise BackendError(f"{url} returned HTTP {exc.code} ({exc.reason})") from exc
        except urllib.error.URLError as exc:
            raise BackendError(f"{url} could not be fetched: {exc.reason}") from exc
        except OSError as exc:  # timeouts, connection resets, DNS
            raise BackendError(f"{url} could not be fetched: {exc}") from exc
        if response is None:
            # No handler claimed the scheme. Unreachable given the check above,
            # and refused by name anyway rather than returned as a stream.
            raise BackendError(f"no handler would fetch {url!r}")
        with response:
            yield response


@dataclass(frozen=True)
class FetchResult:
    """A verified artifact on local disk."""

    path: Path
    """Where it is. Content-addressed, so this path implies the digest."""

    sha256: str
    """The digest that was actually computed, not the one that was expected.
    They are equal — a mismatch raises rather than returning — but recording the
    computed one means the log says what was measured."""

    from_cache: bool
    """True when a previously-fetched copy was re-verified instead of downloaded."""

    size: int


def _safe_name(url: str) -> str:
    """A filename for the cache, derived from the URL but never trusting it.

    The digest is what identifies the file; this is only so a human can tell
    what is in the cache. Anything that could escape the directory or confuse a
    shell is dropped rather than escaped, and the result is capped — a URL is
    attacker-influenced input in the general case, and a cache path is not the
    place to find out how long a filename can be.
    """
    tail = url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0].split("#", 1)[0]
    kept = "".join(c for c in tail if c.isalnum() or c in "._-")
    kept = kept.lstrip(".")  # never a dotfile, never `..`
    return kept[:64] or "artifact"


def signature_gap(artifact: RemoteArtifact) -> str | None:
    """What this engine does *not* check about *artifact*, in one sentence.

    Returned rather than logged so the caller can put it in the plan, where a
    gap belongs — CLAUDE.md requires the capability matrix to report honest
    gaps, and a manifest that carries a signature URL the engine ignores is
    exactly the kind of thing that reads as covered when it is not.
    """
    if artifact.signature_url is None and artifact.signing_key_fingerprint is None:
        return None
    return (
        "declares a signature, which this engine build does not verify — only "
        "the sha256 is checked. The signature fields are catalog data waiting "
        "on a verifier; treat this artifact as digest-pinned, not signed."
    )


class Fetcher:
    """Downloads artifacts into a content-addressed cache, verifying each one."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        transport: Transport | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        owner: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir if cache_dir is not None else artifact_cache_dir(owner)
        self.transport: Transport = transport if transport is not None else UrllibTransport()
        self.max_bytes = max_bytes

    def path_for(self, artifact: RemoteArtifact) -> Path:
        """Where this artifact lives once verified. Pure; touches no disk.

        Lets the plan disclose the destination before anything is written,
        which is the same contract the transaction log's ``Records:`` section
        keeps.
        """
        return self.cache_dir / f"{artifact.sha256}-{_safe_name(artifact.url)}"

    def fetch(self, artifact: RemoteArtifact) -> FetchResult:
        """Return a verified local copy of *artifact*, downloading if needed.

        Raises :class:`VerificationError` if what arrives does not match the
        manifest's digest, and :class:`~hammunition.backends.BackendError` if it
        could not be fetched at all. There is no return value that means
        "unverified".
        """
        final = self.path_for(artifact)

        if final.exists():
            actual = _digest_file(final)
            if actual == artifact.sha256:
                return FetchResult(
                    path=final,
                    sha256=actual,
                    from_cache=True,
                    size=final.stat().st_size,
                )
            # Content-addressed, so this cannot be a stale version: it is a
            # corrupted or tampered cache entry. Drop it and fetch again rather
            # than failing -- and never serve it.
            final.unlink()

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Same directory as the destination so the final move is a rename
        # within one filesystem, which is atomic. A temp file in /tmp would
        # make it a copy, and a copy can be interrupted half-written.
        temporary = final.with_name(final.name + f".part.{os.getpid()}")
        try:
            actual, size = self._download(artifact.url, temporary)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

        if actual != artifact.sha256:
            temporary.unlink(missing_ok=True)
            raise VerificationError(
                f"{artifact.url} does not match the digest the manifest declares.\n"
                f"  expected sha256: {artifact.sha256}\n"
                f"  actually got:    {actual}\n"
                f"The download has been discarded. This is either a corrupted "
                f"transfer, an upstream that re-cut a release under the same URL, "
                f"or an artifact that is not the one the catalog was written "
                f"against — and none of those may be installed."
            )

        os.replace(temporary, final)
        return FetchResult(path=final, sha256=actual, from_cache=False, size=size)

    def _download(self, url: str, destination: Path) -> tuple[str, int]:
        """Stream *url* to *destination*, hashing as it goes. Returns (digest, size).

        Hashing the bytes as they are written, rather than re-reading the file
        afterwards, means the digest is over what was actually stored and
        leaves no window between the two.
        """
        digest = hashlib.sha256()
        size = 0
        with self.transport.open(url) as stream, destination.open("wb") as handle:
            while True:
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_bytes:
                    raise BackendError(
                        f"{url} exceeds the {self.max_bytes} byte limit and was "
                        f"abandoned part-way. If this artifact is genuinely this "
                        f"large, raise the limit deliberately rather than removing it."
                    )
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        return digest.hexdigest(), size


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
