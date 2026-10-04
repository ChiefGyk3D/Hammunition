#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build, and verify, the offline documentation bundle.

The bundle is this documentation as a folder of plain web pages that opens
from a disk with no network and no server: `docs/offline/index.md` is its
user-facing description. It is built from the same `docs/` tree and `--strict`
build as the site (`mkdocs-offline.yml` inherits `mkdocs.yml`), then:

* `README-OFFLINE.txt`, `BUILD-INFO.txt`, `THIRD-PARTY-NOTICES.txt`, `LICENSE`
  and `SHA256SUMS` are written beside `index.html`;
* the build line (date, commit, the engine and the companion projects the
  catalog pins) is put in every page's footer;
* the folder is **verified**: nothing in it references a host outside it, every
  internal link, asset and anchor resolves, the search index is present and
  covers the pages. A bundle that merely built is not a bundle that works
  offline. `--verify DIR` runs the same check on an extracted copy.

The date is the build time, or `SOURCE_DATE_EPOCH` when set. It exists only in
the bundle, never in anything committed (D-031).

Usage:
    scripts/build_offline_bundle.py [--out DIR] [--commit SHA] [--no-zip]
    scripts/build_offline_bundle.py --verify DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402

CATALOG = REPO_ROOT / "catalog" / "packages"
OFFLINE_CONFIG = REPO_ROOT / "mkdocs-offline.yml"
BUNDLE_NAME = "hammunition-docs"

#: The companion projects whose pinned version the build line names.
SUITE_UNITS = (
    "hammunition-tray",
    "hammunition-tray-qt",
    "hammunition-hill",
    "hammunition-console",
    "gps-tether",
)

#: Hosts a bundle must never reference: the ones a documentation theme tends to
#: reach for. Any absolute resource URL is refused regardless; this list also
#: catches a host named inside a script or style.
FORBIDDEN_HOSTS = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "unpkg.com",
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "googletagmanager.com",
    "google-analytics.com",
)

#: Tag -> attributes whose value is fetched when the page loads.
RESOURCE_ATTRS = {
    "link": ("href",),
    "script": ("src",),
    "img": ("src", "srcset"),
    "source": ("src", "srcset"),
    "video": ("src", "poster"),
    "audio": ("src",),
    "track": ("src",),
    "iframe": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "form": ("action",),
}

#: Tag -> attributes that are navigation: a click, not a load. An external one
#: is allowed and marked in the page; a local one must exist.
NAVIGATION_ATTRS = {"a": ("href",), "area": ("href",)}

#: Material's bundle names two scripts it fetches only conditionally: a
#: ResizeObserver polyfill for browsers older than 2020, and mermaid, loaded only
#: by a page that has a mermaid diagram (`verify` refuses such a page). Named
#: here so the exception is a decision, not a hole in the host check.
KNOWN_UNUSED = (
    "https://unpkg.com/resize-observer-polyfill",
    "https://unpkg.com/mermaid@11/dist/mermaid.min.js",
)

SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "blob:")

THIRD_PARTY = """\
Third-party material in this bundle
===================================

The text is Hammunition's own (see LICENSE). The pages are built with the
tools below, whose files are carried in the bundle so that nothing is fetched
from the internet when you read it. No third-party manuals, books, maps or
datasets are included; links to them are external and marked.

MkDocs                       BSD-2-Clause   https://www.mkdocs.org/
Material for MkDocs          MIT            https://squidfunk.github.io/mkdocs-material/
                             (theme, search worker, icon sets: Material Design
                             Icons, Font Awesome Free icons under CC BY 4.0,
                             Octicons, Simple Icons)
lunr.js                      MIT            https://lunrjs.com/
iframe-worker (shim)         MIT            https://github.com/squidfunk/iframe-worker
                             lets the search run when pages are opened from a
                             disk; copied unmodified, licence below.

--- iframe-worker licence ---

{iframe_licence}
"""

README = """\
Hammunition documentation, offline copy
=======================================

Open index.html in a web browser. Nothing needs installing and no server is
needed.

{build_line}

* This is documentation only. It does not install the software and it holds no
  maps, books or other operational data. Downloading those is a separate step
  (see "Offline documentation" and the EMCOMM pages inside).
* Links marked "(online)" leave this folder and need the internet.
* Search is the box at the top of every page; it searches this copy only.
* Check a copy that was moved: sha256sum -c SHA256SUMS (in this folder).
* To update, build a new bundle from the repository (scripts/build_offline_bundle.py).
  A bundle never updates itself.

Source: https://github.com/ChiefGyk3D/Hammunition
Licence: see LICENSE and THIRD-PARTY-NOTICES.txt
"""


# --------------------------------------------------------------------------- #
# Build information
# --------------------------------------------------------------------------- #


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return out.stdout.strip()


def build_info(commit: str | None, now: datetime) -> dict[str, object]:
    """What the footer and BUILD-INFO.txt say. Versions are read, never typed."""
    engine = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]["version"]
    catalog = load_catalog(CATALOG)
    suite = {
        name: catalog[name].version
        for name in SUITE_UNITS
        if name in catalog and catalog[name].version
    }
    sha = commit or _git("rev-parse", "HEAD") or "unknown"
    return {
        "built": now.strftime("%Y-%m-%d %H:%M UTC"),
        "commit": sha,
        "engine": engine,
        "suite": suite,
    }


def build_line(info: dict[str, object]) -> str:
    suite = info["suite"]
    assert isinstance(suite, dict)
    pinned = ", ".join(f"{name} {version}" for name, version in suite.items())
    return (
        f"Offline copy built {info['built']} from commit {str(info['commit'])[:12]}. "
        f"Hammunition {info['engine']}; pinned: {pinned}."
    )


def build_info_text(info: dict[str, object]) -> str:
    suite = info["suite"]
    assert isinstance(suite, dict)
    lines = [
        "Hammunition offline documentation",
        f"Built:   {info['built']}",
        f"Commit:  {info['commit']}",
        f"Engine:  {info['engine']}",
        "Companion projects, as pinned by the catalog at that commit:",
        *(f"  {name}: {version}" for name, version in suite.items()),
        "",
        "The versions are what the catalog installs, not what is on your machine:",
        "compare with `hammunition status`.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Building
# --------------------------------------------------------------------------- #


def run_mkdocs(site: Path, line: str) -> None:
    env = dict(os.environ, HAMMUNITION_BUNDLE_LINE=line)
    cmd = [
        sys.executable,
        "-m",
        "mkdocs",
        "build",
        "--strict",
        "--quiet",
        "-f",
        str(OFFLINE_CONFIG),
        "-d",
        str(site),
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit("mkdocs build failed; no bundle written")


def write_extras(site: Path, info: dict[str, object]) -> None:
    licence = (REPO_ROOT / "docs/assets/vendor/iframe-worker/LICENSE.txt").read_text()
    (site / "README-OFFLINE.txt").write_text(README.format(build_line=build_line(info)))
    (site / "BUILD-INFO.txt").write_text(build_info_text(info))
    (site / "THIRD-PARTY-NOTICES.txt").write_text(THIRD_PARTY.format(iframe_licence=licence))
    shutil.copyfile(REPO_ROOT / "LICENSE", site / "LICENSE")
    write_sums(site)


def bundle_files(site: Path) -> list[Path]:
    return sorted(p for p in site.rglob("*") if p.is_file() and p.name != "SHA256SUMS")


def write_sums(site: Path) -> None:
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(site).as_posix()}"
        for p in bundle_files(site)
    ]
    (site / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def make_zip(site: Path, dest: Path, now: datetime) -> None:
    stamp = (max(now.year, 1980), now.month, now.day, now.hour, now.minute, now.second)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(site.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(f"{BUNDLE_NAME}/{path.relative_to(site).as_posix()}", stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, path.read_bytes())


# --------------------------------------------------------------------------- #
# Verifying
# --------------------------------------------------------------------------- #


class _Page(HTMLParser):
    """Collects what a page loads, what it links to, and the anchors it offers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.resources: list[tuple[str, str, str]] = []  # (tag, attr, value)
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k: v for k, v in attrs if v is not None}
        for key in ("id", "name"):
            if key in values:
                self.ids.add(values[key])
        for attr in RESOURCE_ATTRS.get(tag, ()):
            if attr in values:
                if attr == "srcset":
                    for part in values[attr].split(","):
                        if part.strip():
                            self.resources.append((tag, attr, part.split()[0]))
                else:
                    self.resources.append((tag, attr, values[attr]))
        for attr in NAVIGATION_ATTRS.get(tag, ()):
            if attr in values:
                self.links.append(values[attr])


_URL_IN_CSS = re.compile(r"""url\(\s*['"]?([^'")\s]+)""", re.IGNORECASE)
_CSS_IMPORT = re.compile(r"""@import\s+(?:url\()?\s*['"]?([^'")\s;]+)""", re.IGNORECASE)


def _is_external(value: str) -> bool:
    v = value.strip().lower()
    return v.startswith(("http://", "https://", "//", "ftp://"))


def _resolve(root: Path, page: Path, value: str) -> Path | None:
    """The file a local reference names, or None when it names nothing local."""
    target = unquote(value.strip().split("#", 1)[0].split("?", 1)[0])
    if not target:
        return page
    base = root if target.startswith("/") else page.parent
    path = (base / target.lstrip("/")).resolve()
    if path.is_dir():
        path = path / "index.html"
    return path


def verify(root: Path) -> list[str]:
    """Every reason this folder will not work with the network off. Empty is ok."""
    root = root.resolve()
    problems: list[str] = []

    def need(rel: str) -> Path:
        p = root / rel
        if not p.is_file():
            problems.append(f"missing {rel}")
        return p

    for rel in (
        "index.html",
        "README-OFFLINE.txt",
        "BUILD-INFO.txt",
        "THIRD-PARTY-NOTICES.txt",
        "LICENSE",
        "SHA256SUMS",
    ):
        need(rel)

    pages = sorted(root.rglob("*.html"))
    parsed: dict[Path, _Page] = {}
    external_links = 0
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="replace")
        rel = page.relative_to(root).as_posix()
        parser = _Page()
        parser.feed(text)
        parsed[page.resolve()] = parser
        for host in FORBIDDEN_HOSTS:
            if host in text:
                problems.append(f"{rel}: names {host}")
        if 'data-md-component="source"' in text:
            problems.append(f"{rel}: has the repository widget, which asks api.github.com")
        if 'class="mermaid"' in text:
            problems.append(f"{rel}: has a mermaid diagram, which Material loads from unpkg.com")
        for css in _URL_IN_CSS.findall(text) + _CSS_IMPORT.findall(text):
            if _is_external(css):
                problems.append(f"{rel}: inline style loads {css}")
        for tag, attr, value in parser.resources:
            if _is_external(value):
                problems.append(f"{rel}: <{tag} {attr}> loads {value}")
            elif not value.lower().startswith(SKIP_SCHEMES):
                target = _resolve(root, page, value)
                if target is None or not target.is_file():
                    problems.append(f"{rel}: <{tag} {attr}> missing asset {value}")
                elif root not in target.parents:
                    problems.append(f"{rel}: <{tag} {attr}> leaves the bundle: {value}")

    for css_file in (*root.rglob("*.css"), *root.rglob("*.js")):
        text = css_file.read_text(encoding="utf-8", errors="replace")
        for allowed in KNOWN_UNUSED:
            text = text.replace(allowed, "")
        rel = css_file.relative_to(root).as_posix()
        for host in FORBIDDEN_HOSTS:
            if host in text:
                problems.append(f"{rel}: names {host}")
        if css_file.suffix == ".css":
            for ref in _URL_IN_CSS.findall(text) + _CSS_IMPORT.findall(text):
                if _is_external(ref):
                    problems.append(f"{rel}: loads {ref}")
                elif not ref.lower().startswith(SKIP_SCHEMES):
                    target = _resolve(root, css_file, ref)
                    if target is None or not target.is_file():
                        problems.append(f"{rel}: missing asset {ref}")

    # Navigation: local links must land on a file and, where they name one, an anchor.
    for page, parser in parsed.items():
        rel = page.relative_to(root).as_posix()
        for value in parser.links:
            if _is_external(value):
                external_links += 1
                continue
            if value.lower().startswith(SKIP_SCHEMES) or value.strip() == "":
                continue
            target = _resolve(root, page, value)
            if target is None or not target.is_file():
                problems.append(f"{rel}: broken link {value}")
                continue
            if root not in target.parents and target != root:
                problems.append(f"{rel}: link leaves the bundle: {value}")
                continue
            fragment = value.partition("#")[2]
            if fragment and target.suffix == ".html":
                other = parsed.get(target)
                if other is not None and unquote(fragment) not in other.ids:
                    problems.append(f"{rel}: missing anchor {value}")

    # Search must work from a disk.
    index_json = root / "search" / "search_index.json"
    index_js = root / "search" / "search_index.js"
    if not index_js.is_file():
        problems.append("missing search/search_index.js (search needs it from file://)")
    if index_json.is_file():
        try:
            docs = json.loads(index_json.read_text(encoding="utf-8"))["docs"]
        except (ValueError, KeyError):
            docs = []
            problems.append("search/search_index.json is not a search index")
        locations = {str(d.get("location", "")).split("#")[0] for d in docs}
        if len(locations) < max(1, len(pages) // 2):
            problems.append(
                f"search index covers {len(locations)} pages of {len(pages)}; it is not complete"
            )
        for need_page in ("suite/index.html", "emcomm/index.html", "offline/index.html"):
            if (
                need_page in {p.relative_to(root).as_posix() for p in pages}
                and need_page not in locations
            ):
                problems.append(f"search index lacks {need_page}")
    else:
        problems.append("missing search/search_index.json")

    if "index.html" in {p.relative_to(root).as_posix() for p in pages}:
        home = (root / "index.html").read_text(encoding="utf-8")
        if "Offline copy built" not in home:
            problems.append("index.html does not show the build date and versions")
    if not any("(online)" in p.read_text(encoding="utf-8") for p in root.rglob("*.css")):
        problems.append("external links are not marked: the (online) style is missing")
    if not (root / "assets/vendor/iframe-worker/shim.js").is_file():
        problems.append("missing the local iframe-worker shim")

    return problems


def verify_sums(root: Path) -> list[str]:
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        return ["missing SHA256SUMS"]
    problems = []
    listed = set()
    for line in sums.read_text().splitlines():
        digest, _, name = line.partition("  ")
        listed.add(name)
        path = root / name
        if not path.is_file():
            problems.append(f"SHA256SUMS names a missing file: {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"checksum mismatch: {name}")
    for path in bundle_files(root):
        if path.relative_to(root).as_posix() not in listed:
            problems.append(f"not in SHA256SUMS: {path.relative_to(root).as_posix()}")
    return problems


def report(root: Path) -> int:
    problems = verify(root) + verify_sums(root)
    if problems:
        print(f"offline bundle: {len(problems)} problem(s) in {root}", file=sys.stderr)
        for line in problems[:50]:
            print(f"  {line}", file=sys.stderr)
        if len(problems) > 50:
            print(f"  ... and {len(problems) - 50} more", file=sys.stderr)
        return 1
    pages = len(list(root.rglob("*.html")))
    print(f"offline bundle ok: {pages} pages, no reference leaves the folder")
    return 0


# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "dist", help="where to write")
    ap.add_argument("--commit", help="commit to record (default: git HEAD)")
    ap.add_argument("--no-zip", action="store_true", help="write the folder only")
    ap.add_argument("--verify", type=Path, metavar="DIR", help="verify an extracted bundle")
    args = ap.parse_args(argv)

    if args.verify:
        return report(args.verify)

    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    now = datetime.fromtimestamp(int(epoch), UTC) if epoch else datetime.now(UTC)
    info = build_info(args.commit, now)
    version = info["engine"]
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    folder = out / BUNDLE_NAME

    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp) / BUNDLE_NAME
        run_mkdocs(site, build_line(info))
        write_extras(site, info)
        if folder.exists():
            shutil.rmtree(folder)
        shutil.copytree(site, folder)

    status = report(folder)
    if status:
        return status
    if not args.no_zip:
        zip_path = out / f"{BUNDLE_NAME}-{version}.zip"
        make_zip(folder, zip_path, now)
        print(f"wrote {zip_path} ({zip_path.stat().st_size // 1024} KiB)")
    print(f"wrote {folder}/ (open index.html)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
