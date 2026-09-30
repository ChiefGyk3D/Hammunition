# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""MkDocs build hook for the documentation site (D-063).

The pages under `docs/` are written to read correctly on GitHub, where a
relative link to `../../catalog/packages/direwolf.yaml` or to
`../DECISIONS.md` opens that file. On the published site those files are not
pages: the catalog is outside `docs/`, and the project records are excluded
from the site on purpose (CLAUDE.md: DECISIONS, PARITY-POLICY, DESIGN and
why-hammunition are not part of the user-facing site). Left alone, all 268
such links on the 2026-09-30 tree were build warnings and dead links.

So at build time, and only there, a relative link whose target is not a page
or file of the site is pointed at the same file on GitHub. The source stays
as it is, the link checker (`scripts/check_doc_links.py`) keeps checking it
against the repository, and nothing here writes to the tree.

A link whose target does not exist in the repository either is left exactly
as written, so MkDocs reports it and `mkdocs build --strict` fails: this hook
repairs where a link *points*, never hides that it points at nothing.

Measured 2026-09-30: Zensical 0.0.66 builds this tree but runs no MkDocs
hook, so when the site moves to it this rewriting has to move into the page
generators; D-063 records that.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.files import Files
    from mkdocs.structure.pages import Page

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = "docs"
REF = "main"

FENCE = re.compile(r"^\s*(```|~~~)")
# An inline link or image target: ](target) or ](target "title").
INLINE = re.compile(r"(\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")
# A reference definition: [id]: target
REFDEF = re.compile(r"^(\s{0,3}\[[^\]]+\]:\s*)(\S+)(.*)$")
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#|/)", re.IGNORECASE)


def _repo_url_for(target_path: str, src_uri: str, repo_url: str) -> str | None:
    """The GitHub URL for a link's target, or None when it is not ours to move."""
    in_docs = posixpath.normpath(posixpath.join(posixpath.dirname(src_uri), target_path))
    repo_path = posixpath.normpath(posixpath.join(DOCS_DIR, in_docs))
    if repo_path.startswith("../") or repo_path == "..":
        return None
    on_disk = REPO_ROOT / repo_path
    if not on_disk.exists():
        return None
    kind = "tree" if on_disk.is_dir() else "blob"
    return f"{repo_url.rstrip('/')}/{kind}/{REF}/{repo_path}"


def rewrite_links(
    markdown: str,
    src_uri: str,
    is_site_file: Callable[[str], bool],
    repo_url: str,
) -> str:
    """Point every relative link whose target is not part of the site at GitHub.

    `src_uri` is the page's path inside `docs/`; `is_site_file` answers whether
    a path inside `docs/` is a page or file the site publishes.
    """

    def fix(target: str) -> str:
        if EXTERNAL.match(target):
            return target
        path, sep, anchor = target.partition("#")
        if not path:
            return target
        in_docs = posixpath.normpath(posixpath.join(posixpath.dirname(src_uri), path))
        if not in_docs.startswith("../") and is_site_file(in_docs):
            return target
        url = _repo_url_for(path, src_uri, repo_url)
        if url is None:
            return target
        return url + (sep + anchor if sep else "")

    out: list[str] = []
    in_fence = False
    for line in markdown.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        ref = REFDEF.match(line)
        if ref:
            out.append(ref.group(1) + fix(ref.group(2)) + ref.group(3))
            continue
        out.append(INLINE.sub(lambda m: m.group(1) + fix(m.group(2)) + m.group(3), line))
    return "\n".join(out)


def on_page_markdown(markdown: str, *, page: Page, config: MkDocsConfig, files: Files) -> str:
    """MkDocs hook entry point: rewrite this page's out-of-site links."""

    from mkdocs.structure.files import InclusionLevel

    def is_site_file(path: str) -> bool:
        f = files.get_file_from_path(path)
        return f is not None and f.inclusion is not InclusionLevel.EXCLUDED

    return rewrite_links(markdown, page.file.src_uri, is_site_file, str(config.repo_url))
