#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate the GitHub wiki from docs/ — a mirror of the MkDocs site.

The wiki is not a second place to write. Every page is the same Markdown the
site is built from, rewritten for a flat namespace, and
`.github/workflows/wiki.yml` replaces the wiki's contents with this output on
every push to main. CLAUDE.md: "Generate what can be generated"; a wiki typed
by hand would be a copy that drifts.

What is written, into the directory named by `--out`:

* one page per document in the `mkdocs.yml` nav, plus every generated package
  page under `docs/packages/`. GitHub wikis are flat, so the page name is the
  docs path with `/` turned into `-` and each word capitalised:
  `getting-started/install.md` is `Getting-Started-Install.md`. Two documents
  that derive the same name (compared without case, as GitHub does) are an
  error, never a silent overwrite.
* `Home.md` from `docs/index.md`, under a banner saying what the wiki is.
* `_Sidebar.md` from the nav, groups and pages in nav order.
* `_Footer.md` naming the source commit given with `--commit`. Never a clock
  or a hostname (D-031): the output is a function of the tree and the commit.
* `Software-by-activity.md` from the menu vocabulary, `catalog/categories.yaml`
  (D-055): one chapter per group, one section per tag, every unit carrying it.

Links are rewritten as `scripts/site_hooks.py` does for the site: a relative
link to another wiki page becomes that page's wiki name; one to anything else
in the repository (the catalog, the project records the site excludes) points
at the file on GitHub `main`. MkDocs-only syntax is reduced to plain Markdown:
admonitions become blockquotes, `{ .class }` attribute lists and `[TOC]` go.

Needs no network.

Usage:
    scripts/gen_wiki.py --out DIR [--commit SHA]    # write the wiki tree
    scripts/gen_wiki.py --check [--out DIR]         # validate; compare DIR if given
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import Status  # noqa: E402
from hammunition.menus import load_vocabulary  # noqa: E402

DOCS = REPO_ROOT / "docs"
REPO_URL = "https://github.com/ChiefGyk3D/Hammunition"
SITE_URL = "https://chiefgyk3d.github.io/Hammunition/"
REF = "main"

ACTIVITY_PAGE = "Software-by-activity"
RESERVED = {"home", "_sidebar", "_footer", ACTIVITY_PAGE.lower()}

FENCE = re.compile(r"^\s*(```|~~~)")
INLINE = re.compile(r"(\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")
REFDEF = re.compile(r"^(\s{0,3}\[[^\]]+\]:\s*)(\S+)(.*)$")
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#|/|<)", re.IGNORECASE)
ADMONITION = re.compile(r"^(\s*)(?:!!!|\?\?\?\+?)\s+([\w-]+)(?:\s+\"([^\"]*)\")?\s*$")
ATTR_LIST = re.compile(r"[ \t]*\{:?[ \t]*[.#][\w .#:=-]*\}")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

BANNER = (
    "> **This wiki is generated.** It mirrors `docs/` in the repository and is "
    "rebuilt on every push to `main`, so it cannot drift from the site. The "
    f"canonical documentation is <{SITE_URL}>. Do not edit a page here: the next "
    f"push replaces it. Corrections go to `docs/` by pull request at "
    f"<{REPO_URL}>.\n\n"
)


class WikiError(Exception):
    """A tree the wiki cannot be generated from."""


# ---------------------------------------------------------------------------
# Names and the nav
# ---------------------------------------------------------------------------


def wiki_name(doc_path: str) -> str:
    """`getting-started/install.md` -> `Getting-Started-Install`."""
    if doc_path == "index.md":
        return "Home"
    stem = doc_path.removesuffix(".md").removesuffix("/index")
    stem = re.sub(r"[^A-Za-z0-9_/.-]", "-", stem).replace("/", "-").replace(".", "-")
    return "-".join(w[:1].upper() + w[1:] for w in stem.split("-") if w)


def _nav_paths(nav: list[Any]) -> list[str]:
    out: list[str] = []
    for item in nav:
        if isinstance(item, str):
            out.append(item)
        else:
            (value,) = item.values()
            if isinstance(value, str):
                out.append(value)
            else:
                out.extend(_nav_paths(value))
    return out


def page_set(nav: list[Any]) -> dict[str, str]:
    """docs path -> wiki name, for the nav and the package pages."""
    paths = _nav_paths(nav)
    paths += sorted(p.relative_to(DOCS).as_posix() for p in (DOCS / "packages").glob("*.md"))
    names: dict[str, str] = {}
    seen: dict[str, str] = {}
    for path in dict.fromkeys(paths):
        if not (DOCS / path).is_file():
            raise WikiError(f"the nav names {path}, which is not a file under docs/")
        name = wiki_name(path)
        key = name.lower()
        if key in RESERVED and path != "index.md":
            raise WikiError(f"{path} derives the reserved wiki name {name}")
        if key in seen:
            raise WikiError(f"{path} and {seen[key]} both derive the wiki name {name}")
        seen[key] = path
        names[path] = name
    return names


# ---------------------------------------------------------------------------
# Markdown rewriting
# ---------------------------------------------------------------------------


def _admonitions(lines: list[str]) -> list[str]:
    out: list[str] = []
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else ADMONITION.match(line)
        if not m:
            out.append(line)
            i += 1
            continue
        indent = len(m.group(1))
        kind, title = m.group(2), m.group(3)
        body: list[str] = []
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if nxt.strip() == "":
                body.append("")
            elif len(nxt) - len(nxt.lstrip()) >= indent + 4:
                body.append(nxt[indent + 4 :])
            else:
                break
            i += 1
        while body and body[-1] == "":
            body.pop()
        out.append(f"{m.group(1)}> **{title or kind.capitalize()}**")
        out.append(f"{m.group(1)}>")
        out.extend(f"{m.group(1)}> {b}".rstrip() if b else f"{m.group(1)}>" for b in body)
        out.append("")
    return out


def _target(target: str, src: str, names: dict[str, str], is_image: bool) -> str:
    """The wiki or GitHub form of one relative link target."""
    if EXTERNAL.match(target):
        return target
    path, sep, anchor = target.partition("#")
    if not path:
        return target
    in_docs = posixpath.normpath(posixpath.join(posixpath.dirname(src), path))
    candidates = [in_docs, posixpath.join(in_docs, "index.md")]
    if not is_image:
        for c in candidates:
            if c in names:
                return names[c] + (sep + anchor if sep else "")
    repo_path = posixpath.normpath(posixpath.join("docs", in_docs))
    on_disk = REPO_ROOT / repo_path
    if repo_path.startswith("..") or not on_disk.exists():
        raise WikiError(f"{src}: the link {target} points at nothing in the repository")
    kind = "tree" if on_disk.is_dir() else "blob"
    url = f"{REPO_URL}/{kind}/{REF}/{repo_path}"
    if is_image or Path(path).suffix.lower() in IMAGE_EXT:
        return url + "?raw=true"
    return url + (sep + anchor if sep else "")


def convert(markdown: str, src: str, names: dict[str, str]) -> str:
    """One docs page as a wiki page."""
    lines = _admonitions(markdown.split("\n"))
    out: list[str] = []
    in_fence = False
    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if line.strip() == "[TOC]":
            continue
        line = ATTR_LIST.sub("", line)
        ref = REFDEF.match(line)
        if ref:
            out.append(ref.group(1) + _target(ref.group(2), src, names, False) + ref.group(3))
            continue

        def fix(m: re.Match[str]) -> str:
            is_image = IMAGE_EXT & {Path(m.group(2).partition("#")[0]).suffix.lower()} != set()
            return m.group(1) + _target(m.group(2), src, names, is_image) + m.group(3)

        out.append(INLINE.sub(fix, line))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The generated pages
# ---------------------------------------------------------------------------


def _title(path: str) -> str:
    for line in (DOCS / path).read_text().split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return Path(path).stem


def sidebar(nav: list[Any], names: dict[str, str]) -> str:
    out: list[str] = []

    def walk(items: list[Any], depth: int) -> None:
        pad = "  " * depth
        for item in items:
            if isinstance(item, str):
                out.append(f"{pad}- [{_title(item)}]({names[item]})")
                continue
            ((label, value),) = item.items()
            if isinstance(value, str):
                out.append(f"{pad}- [{label}]({names[value]})")
                continue
            first = value[0] if value and isinstance(value[0], str) else None
            if first and first.endswith("index.md"):
                out.append(f"{pad}- [{label}]({names[first]})")
                rest = value[1:]
            else:
                out.append(f"{pad}- **{label}**")
                rest = value
            walk(rest, depth + 1)

    for position, group in enumerate(nav):
        walk([group], 0)
        if position == 0:
            out.append(f"- [Software by activity]({ACTIVITY_PAGE})")
    return "\n".join(out) + "\n"


def footer(commit: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit):
        src = f"`{commit}`"
    else:
        src = f"[`{commit[:12]}`]({REPO_URL}/commit/{commit})"
    return (
        f"Generated from `docs/` at commit {src}. "
        f"Canonical site: <{SITE_URL}>. Edit `docs/` by pull request, not this wiki.\n"
    )


def software_by_activity(names: dict[str, str]) -> str:
    vocab = load_vocabulary(REPO_ROOT / "catalog" / "categories.yaml")
    manifests = load_catalog(REPO_ROOT / "catalog" / "packages")
    titles = {c.name: c for c in vocab.categories}
    by_tag: dict[str, list[str]] = {}
    for name in sorted(manifests):
        for tag in manifests[name].categories:
            by_tag.setdefault(tag, []).append(name)
    grouped = {c for g in vocab.groups for c in g.categories}
    stray = sorted(set(by_tag) - grouped)
    if stray:
        raise WikiError(f"tags in no group of the vocabulary: {', '.join(stray)}")

    out = [
        "# Software by activity\n",
        "Every program the catalog carries, laid out the way the desktop menu is "
        + "(D-050, D-055): one chapter per activity, one section per thing a person "
        + "looks for. A program with several tags is listed under each. Generated "
        + "from `catalog/categories.yaml` and the package manifests.\n",
    ]
    for group in vocab.groups:
        out.append(f"## {group.title}\n")
        out.append(f"{group.summary}\n")
        for tag in group.categories:
            members = by_tag.get(tag, [])
            if not members:
                continue
            cat = titles[tag]
            out.append(f"### {cat.title or tag}\n")
            out.append(f"{cat.summary}\n")
            for name in members:
                page = names.get(f"packages/{name}.md")
                if page is None:
                    raise WikiError(f"no package page for {name}; run gen_package_reference.py")
                m = manifests[name]
                retired = " *(retired)*" if m.status is Status.retired else ""
                out.append(f"- [{name}]({page}){retired} — {m.summary}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def render(commit: str = "unknown") -> dict[str, str]:
    """Every wiki file, name -> content. Raises WikiError on a tree it cannot map."""
    config = yaml.safe_load(_strip_tags((REPO_ROOT / "mkdocs.yml").read_text()))
    nav = config["nav"]
    names = page_set(nav)
    files: dict[str, str] = {}
    for path, name in names.items():
        body = convert((DOCS / path).read_text(), path, names)
        if path == "index.md":
            body = BANNER + body
        files[f"{name}.md"] = body if body.endswith("\n") else body + "\n"
    files[f"{ACTIVITY_PAGE}.md"] = software_by_activity(names)
    files["_Sidebar.md"] = sidebar(nav, names)
    files["_Footer.md"] = footer(commit)
    empty = sorted(f for f, c in files.items() if not c.strip())
    if empty:
        raise WikiError(f"empty wiki pages: {', '.join(empty)}")
    return files


def _strip_tags(text: str) -> str:
    """mkdocs.yml may carry `!!python/name` tags; the nav needs none of them."""
    return re.sub(r"!!python/\S+", "", text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="directory to write the wiki into")
    parser.add_argument("--commit", default="unknown", help="source commit SHA for the footer")
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing: validate, and compare --out if it exists",
    )
    args = parser.parse_args()
    if not args.check and args.out is None:
        parser.error("--out is required unless --check")

    try:
        files = render(args.commit)
    except WikiError as e:
        print(f"gen_wiki: {e}", file=sys.stderr)
        return 1

    if args.check:
        if args.out is not None and args.out.is_dir():
            have = {p.name: p.read_text() for p in args.out.glob("*.md")}
            if have != files:
                diff = sorted(
                    set(have) ^ set(files) | {f for f in files if have.get(f) != files[f]}
                )
                print(f"{args.out} is out of date ({', '.join(diff[:8])}); run scripts/gen_wiki.py")
                return 1
        print(f"wiki is up to date ({len(files)} pages generate cleanly)")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (args.out / name).write_text(content)
    print(f"wrote {len(files)} wiki pages to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
