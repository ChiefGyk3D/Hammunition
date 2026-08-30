#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sweep every pinned artifact URL in the catalog for liveness.

The digital-modes campaign found four manifests whose URLs had been
constructed from AHRL's bundled tarball names and never fetched — two of
them for upstreams that had stopped publishing source archives entirely.
Users found nothing, because nothing ever asked the URLs whether they were
real. This asks.

Deliberately **not** a per-push CI job: it needs the live internet, hosts
flake, and a red CI nobody trusts is worse than none (CLAUDE.md's own
lesson list). It is a maintenance sweep — run it before a release, after a
campaign, or on a schedule — and its verdicts are hard 4xx answers, kept
apart from hosts that merely failed to answer today.

Exit codes: 0 all reachable, 1 at least one URL is definitively dead
(4xx/410), 2 only transient trouble (timeouts, 5xx, DNS) — retry later.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402

USER_AGENT = "hammunition-url-sweep/1 (+https://github.com/ChiefGyk3D/Hammunition)"


def artifact_urls(catalog: dict[str, PackageManifest]) -> list[tuple[str, str]]:
    """(manifest name, url) for every RemoteArtifact in every install block."""
    found: list[tuple[str, str]] = []
    for name, manifest in sorted(catalog.items()):
        for block in manifest.install:
            for attr in ("artifact", "source"):
                remote = getattr(block.install, attr, None)
                if remote is not None:
                    found.append((name, remote.url))
    return found


def probe(url: str, timeout: float) -> tuple[str, str]:
    """('ok'|'dead'|'transient', detail). HEAD first, ranged GET as fallback —
    some hosts refuse HEAD while serving the file happily."""
    for method, headers in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
        request = urllib.request.Request(
            url, method=method, headers={"User-Agent": USER_AGENT, **headers}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return "ok", f"{method} {response.status}"
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410, 403):
                if method == "GET":
                    return "dead", f"HTTP {exc.code}"
                continue  # some hosts 403/404 HEAD only; let GET decide
            if method == "GET":
                return "transient", f"HTTP {exc.code}"
        except Exception as exc:
            if method == "GET":
                return "transient", str(exc)[:80]
    return "transient", "unreachable"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--only", nargs="*", default=[], help="limit to these manifests")
    args = parser.parse_args()

    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    urls = artifact_urls(catalog)
    if args.only:
        urls = [(n, u) for n, u in urls if n in args.only]

    dead: list[tuple[str, str, str]] = []
    transient: list[tuple[str, str, str]] = []
    for name, url in urls:
        verdict, detail = probe(url, args.timeout)
        mark = {"ok": " ", "dead": "✗", "transient": "?"}[verdict]
        print(f"[{mark}] {name}: {detail}  {url}")
        if verdict == "dead":
            dead.append((name, url, detail))
        elif verdict == "transient":
            transient.append((name, url, detail))

    print(f"\n{len(urls)} URL(s): {len(urls) - len(dead) - len(transient)} ok, "
          f"{len(dead)} dead, {len(transient)} unreachable today")
    if dead:
        print("\nDead pins — the manifest's URL no longer exists upstream:")
        for name, url, detail in dead:
            print(f"  {name}: {detail} {url}")
        return 1
    return 2 if transient else 0


if __name__ == "__main__":
    raise SystemExit(main())
