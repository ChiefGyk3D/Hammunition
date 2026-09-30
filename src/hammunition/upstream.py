# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The catalog's pin versus upstream: `update --upstream`.  D-053, second half.

The offline report (:mod:`hammunition.update`) compares the machine with the
catalog. This compares the catalog with the world, through the probes D-010
gave every manifest, and it is opt-in because it is the one thing the engine
does that talks to someone else's server: GitHub's API for a release, a git
host's ref list for tags, PyPI's JSON for a project, a plain-text file for a
label. Nothing is downloaded beyond those answers, and nothing is written.

Every network call goes through an injected function, so the comparison is
testable without a network and the real fetchers are a few lines each. A
probe that cannot be answered -- no repository named and none derivable, a
timeout, a 404 -- is a row that says so, never a crash and never a guess.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

from hammunition.kiwix import BookFile, BookPin, KiwixError, KiwixGone, current_file, file_date
from hammunition.manifest.schema import GitInstall, PackageManifest, SourceInstall

CURRENT = "current"
NEWER_UPSTREAM = "newer upstream"
DIFFERS = "differs"
UNANSWERED = "unanswered"
EXPIRED = "pin expired"
NOT_UPSTREAM = "not an upstream probe"

Http = Callable[[str], str]
"""GET a URL, return its body as text; raise on any failure."""
LsRemote = Callable[[str], Sequence[str]]
"""``git ls-remote --tags --refs URL``, as bare tag names; raise on failure."""

GITHUB_API = "https://api.github.com"
_GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})


@dataclass(frozen=True)
class UpstreamRow:
    unit: str
    method: str
    catalog: str
    upstream: str | None
    state: str
    detail: str


def _version_key(text: str) -> tuple[int, ...] | None:
    """Numeric parts of a version-like string, or None when it has none.

    ``v4.2.13`` -> (4, 2, 13); ``release-1.0-beta230(03-Sep-2026)`` -> (1, 0,
    230, 3, 2026). Enough to order tags from one project against each other;
    not a claim to understand every scheme, which is why *differs* exists.
    """
    parts = tuple(int(n) for n in re.findall(r"\d+", text))
    return parts or None


def _normalise(text: str) -> str:
    return re.sub(r"^(?:v|V|release-|rel-)", "", text.strip())


def compare(catalog: str, upstream: str) -> str:
    """One of CURRENT, NEWER_UPSTREAM or DIFFERS."""
    a, b = _normalise(catalog), _normalise(upstream)
    if a == b or a in b or b in a:
        return CURRENT
    ka, kb = _version_key(a), _version_key(b)
    if ka is not None and kb is not None and kb > ka:
        return NEWER_UPSTREAM
    return DIFFERS


def highest_tag(tags: Sequence[str]) -> str | None:
    """The tag with the greatest numeric parts; None when no tag has any."""
    keyed = [(key, tag) for tag in tags if (key := _version_key(tag)) is not None]
    if not keyed:
        return None
    return max(keyed)[1]


def github_repo_of(manifest: PackageManifest) -> str | None:
    """``owner/name`` from the probe, else from a git or source block's URL."""
    probe = manifest.update.probe
    if probe.repo:
        return probe.repo.strip("/")
    for block in manifest.install:
        method = block.install
        url: str | None = None
        if isinstance(method, GitInstall):
            url = method.repo
        elif isinstance(method, SourceInstall):
            url = method.source.url
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.hostname in _GITHUB_HOSTS:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1].removesuffix('.git')}"
    return None


def git_url_of(manifest: PackageManifest) -> str | None:
    """A clone URL whose tags answer a ``github_tags`` probe, from any host."""
    repo = manifest.update.probe.repo
    if repo and "://" not in repo:
        return f"https://github.com/{repo.strip('/')}"
    if repo:
        return repo
    for block in manifest.install:
        if isinstance(block.install, GitInstall):
            return block.install.repo
    github = github_repo_of(manifest)
    return f"https://github.com/{github}" if github else None


def probe_upstream(manifest: PackageManifest, *, http: Http, ls_remote: LsRemote) -> UpstreamRow:
    """Ask upstream what its current version is and compare it to the pin."""
    probe = manifest.update.probe
    method = probe.method
    catalog = manifest.version

    def row(upstream: str | None, state: str, detail: str) -> UpstreamRow:
        return UpstreamRow(manifest.name, method, catalog, upstream, state, detail)

    try:
        if method == "github_release":
            repo = github_repo_of(manifest)
            if repo is None:
                return row(None, UNANSWERED, "no GitHub repository named or derivable")
            body = json.loads(http(f"{GITHUB_API}/repos/{repo}/releases/latest"))
            tag = str(body.get("tag_name") or "")
            if not tag:
                return row(None, UNANSWERED, f"{repo}: latest release carries no tag_name")
            return row(tag, compare(catalog, tag), f"latest release of {repo}")
        if method == "github_tags":
            url = git_url_of(manifest)
            if url is None:
                return row(None, UNANSWERED, "no repository named or derivable")
            tags = list(ls_remote(url))
            best = highest_tag(tags)
            if best is None:
                return row(None, UNANSWERED, f"{url}: {len(tags)} tag(s), none version-like")
            return row(best, compare(catalog, best), f"highest of {len(tags)} tag(s) at {url}")
        if method == "pypi":
            project = probe.package or manifest.name
            body = json.loads(http(f"https://pypi.org/pypi/{project}/json"))
            latest = str(body.get("info", {}).get("version") or "")
            if not latest:
                return row(None, UNANSWERED, f"PyPI project {project}: no version in its JSON")
            return row(latest, compare(catalog, latest), f"PyPI project {project}")
        if method == "label_file":
            assert probe.url is not None  # the schema requires it
            body = http(probe.url).strip()
            label = body.splitlines()[0].strip() if body else ""
            if not label:
                return row(None, UNANSWERED, f"{probe.url}: empty")
            state = CURRENT if label == catalog.strip() else DIFFERS
            return row(label, state, f"label at {probe.url}, compared verbatim")
        if method == "binary_version":
            return row(
                None,
                NOT_UPSTREAM,
                "binary_version reads the installed program, not upstream; not asked here",
            )
        return row(None, NOT_UPSTREAM, f"probe method {method!r} asks nobody")
    except Exception as exc:
        return row(None, UNANSWERED, f"{type(exc).__name__}: {exc}"[:200])


OPDS = "https://opds.library.kiwix.org/catalog/v2/entries"
KIWIX_REGENERATE = "regenerate the pins with scripts/gen_kiwix_pins.py"


def probe_kiwix(
    unit: str, books: Sequence[BookFile], *, text: Callable[[str], str]
) -> list[UpstreamRow]:
    """Each chosen book's pin against the file Kiwix publishes now (D-065).

    One OPDS answer per book (about 3 KB). When Kiwix's newest file is not
    the pinned one, the pinned file's ``.meta4`` is asked for too: Kiwix
    keeps the two newest dated files of a book, so a pin one behind is
    still published and goes at the next publication (*newer upstream*),
    and a pin that answers 404 is gone already (*pin expired*).
    """
    from urllib.parse import quote

    rows: list[UpstreamRow] = []
    for book in books:
        pin = book.pin

        def row(upstream: str | None, state: str, detail: str, pin: BookPin = pin) -> UpstreamRow:
            return UpstreamRow(f"{unit}/{pin.id}", "kiwix", pin.published, upstream, state, detail)

        try:
            answer = text(f"{OPDS}?name={quote(book.book.name)}")
            newest = current_file(answer, book.book.name, book.book.flavour)
            if newest is None:
                rows.append(row(None, UNANSWERED, "Kiwix's catalogue lists no file of this book"))
                continue
            if newest == pin.file:
                rows.append(row(file_date(newest), CURRENT, "the pinned file is Kiwix's newest"))
                continue
            if file_date(newest) < pin.published:
                rows.append(
                    row(
                        file_date(newest),
                        DIFFERS,
                        f"Kiwix's newest is {newest}, older than the pin",
                    )
                )
                continue
            try:
                text(f"{pin.url}.meta4")
            except KiwixGone:
                rows.append(
                    row(
                        file_date(newest),
                        EXPIRED,
                        f"{pin.file} is no longer published (Kiwix keeps two dated files "
                        f"per book) and an install will refuse it; {KIWIX_REGENERATE}",
                    )
                )
                continue
            rows.append(
                row(
                    file_date(newest),
                    NEWER_UPSTREAM,
                    f"Kiwix published {newest}; it keeps two dated files per book, so the "
                    f"pinned {pin.file} goes at the next publication; {KIWIX_REGENERATE}",
                )
            )
        except KiwixError as exc:
            rows.append(row(None, UNANSWERED, f"{exc}"[:200]))
    return rows


def render(rows: Sequence[UpstreamRow]) -> str:
    asked = [r for r in rows if r.state != NOT_UPSTREAM]
    out = [f"Upstream ({len(asked)} asked):"]
    width = max((len(r.unit) for r in rows), default=8)
    for r in rows:
        if r.state == NOT_UPSTREAM:
            continue
        shown = r.upstream if r.upstream is not None else "?"
        out.append(
            f"  {r.unit:<{width}}  {r.state:<16} catalog {r.catalog}  upstream {shown}  ({r.detail})"
        )
    counts = {
        s: sum(1 for r in asked if r.state == s)
        for s in (CURRENT, NEWER_UPSTREAM, DIFFERS, UNANSWERED, EXPIRED)
    }
    out.append("")
    expired = f", {counts[EXPIRED]} pin(s) expired" if counts[EXPIRED] else ""
    out.append(
        f"{counts[CURRENT]} current, {counts[NEWER_UPSTREAM]} with a newer upstream, "
        f"{counts[DIFFERS]} differing in a way the numbers do not order, "
        f"{counts[UNANSWERED]} unanswered{expired}."
    )
    newer = [r.unit for r in asked if r.state == NEWER_UPSTREAM]
    if newer:
        out.append(
            "A newer upstream is a catalog question: re-pin the manifest, measure the build, then"
        )
        out.append(f"`hammunition install {' '.join(newer)}` on a machine rebuilds at the new pin.")
    out.append(
        "Answers came from GitHub, git hosts, PyPI, Kiwix or a version file; nothing was "
        "downloaded or written."
    )
    return "\n".join(out)


# --- the real fetchers ---------------------------------------------------------


def http_get(url: str, *, timeout: float = 15.0, token: str | None = None) -> str:
    import urllib.request

    headers = {"User-Agent": "hammunition-update (+https://github.com/ChiefGyk3D/Hammunition)"}
    if token and url.startswith(GITHUB_API):
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return str(response.read().decode("utf-8", errors="replace"))


def parse_ls_remote(stdout: str) -> list[str]:
    tags: list[str] = []
    for line in stdout.splitlines():
        _sha, _tab, ref = line.partition("\t")
        if ref.startswith("refs/tags/"):
            tags.append(ref.removeprefix("refs/tags/").removesuffix("^{}"))
    return tags
