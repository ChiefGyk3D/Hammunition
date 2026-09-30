# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The documentation site (D-065): it builds strictly, no page is orphaned,
and the build hook moves only the links it should.

CLAUDE.md: put checks in the test suite and let CI run the test suite. The
Pages workflow builds the same site with the same `--strict`, so a page that
would break the published site breaks here first.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
REPO_URL = "https://github.com/ChiefGyk3D/Hammunition"


def _hooks() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "site_hooks", REPO_ROOT / "scripts" / "site_hooks.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _site_files() -> set[str]:
    """Every docs path the site publishes, from the config's exclusions."""
    config = _config()
    excluded = [
        line.strip().lstrip("/") for line in config["exclude_docs"].splitlines() if line.strip()
    ]
    out = set()
    for p in DOCS.rglob("*"):
        rel = p.relative_to(DOCS).as_posix()
        if any(rel == e or rel.startswith(e) for e in excluded):
            continue
        out.add(rel)
    return out


def _config() -> dict[str, Any]:
    # mkdocs.yml carries no !!python tags, so a plain safe_load reads it.
    loaded = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text())
    assert isinstance(loaded, dict)
    return loaded


def _rewrite(markdown: str, src_uri: str) -> str:
    site = _site_files()
    result = _hooks().rewrite_links(markdown, src_uri, lambda p: p in site, REPO_URL)
    assert isinstance(result, str)
    return result


# ---------------------------------------------------------------------------
# The hook. Each case is one way it could be wrong.
# ---------------------------------------------------------------------------


def test_a_link_to_the_catalog_goes_to_github() -> None:
    out = _rewrite("[x](../../catalog/packages/direwolf.yaml)", "packages/direwolf.md")
    assert out == f"[x]({REPO_URL}/blob/main/catalog/packages/direwolf.yaml)"


def test_a_link_to_an_excluded_record_goes_to_github_with_its_anchor() -> None:
    out = _rewrite("see [D-040](../DECISIONS.md#d-040)", "guides/x.md")
    assert out == f"see [D-040]({REPO_URL}/blob/main/docs/DECISIONS.md#d-040)"


def test_a_link_to_a_directory_goes_to_the_tree_view() -> None:
    out = _rewrite("[catalog](../catalog/)", "index.md")
    assert out == f"[catalog]({REPO_URL}/tree/main/catalog)"


def test_a_link_to_a_site_page_is_left_alone() -> None:
    text = "[rig](rig-control.md#4-test-by-hand) and [pkgs](../packages/index.md)"
    assert _rewrite(text, "guides/digital-modes.md") == text


def test_a_link_to_nothing_is_left_for_mkdocs_to_report() -> None:
    # The hook repairs where a link points; it never hides a dead one.
    text = "[gone](../../catalog/packages/no-such-unit.yaml)"
    assert _rewrite(text, "packages/x.md") == text


def test_external_links_and_anchors_are_untouched() -> None:
    text = "[a](https://example.org/x.md) [b](#here) [c](mailto:x@example.org)"
    assert _rewrite(text, "index.md") == text


def test_code_blocks_are_untouched() -> None:
    text = "```\n[x](../../catalog/packages/direwolf.yaml)\n```"
    assert _rewrite(text, "packages/direwolf.md") == text


def test_a_reference_definition_is_rewritten() -> None:
    out = _rewrite("[src]: ../../catalog/packages/direwolf.yaml", "packages/direwolf.md")
    assert out == f"[src]: {REPO_URL}/blob/main/catalog/packages/direwolf.yaml"


# ---------------------------------------------------------------------------
# The nav. A page that is in no menu and linked from nowhere is a page nobody
# finds; MkDocs only reports it at INFO level, so this makes it a failure.
# ---------------------------------------------------------------------------


def _nav_pages(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, str):
        found.add(node)
    elif isinstance(node, list):
        for item in node:
            found |= _nav_pages(item)
    elif isinstance(node, dict):
        for value in node.values():
            found |= _nav_pages(value)
    return found


def test_every_page_is_in_the_nav_or_is_a_package_page() -> None:
    nav = _nav_pages(_config()["nav"])
    pages = {p for p in _site_files() if p.endswith(".md")}
    # Package pages are reached from the package index, which the generator
    # writes with a link to every one (tests/test_docs_generated.py).
    orphans = sorted(p for p in pages - nav if not p.startswith("packages/"))
    assert not orphans, f"add these to the nav in mkdocs.yml, or exclude them: {orphans}"


def test_the_nav_names_no_missing_page() -> None:
    nav = _nav_pages(_config()["nav"])
    missing = sorted(p for p in nav if not (DOCS / p).is_file())
    assert not missing, f"mkdocs.yml's nav names pages that do not exist: {missing}"


# ---------------------------------------------------------------------------
# The build itself.
# ---------------------------------------------------------------------------


def test_the_site_builds_strictly(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "--site-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        "mkdocs build --strict failed; the published site would too.\n" + result.stderr[-4000:]
    )
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "packages" / "direwolf" / "index.html").is_file()
    # The project records are excluded from the site (CLAUDE.md), and a link
    # to one from a published page leaves for GitHub instead of a 404.
    assert not (tmp_path / "DECISIONS" / "index.html").exists()
    page = (tmp_path / "packages" / "direwolf" / "index.html").read_text()
    assert f"{REPO_URL}/blob/main/catalog/packages/direwolf.yaml" in page


@pytest.mark.parametrize("page", ["guides/index.md", "projects.md", "credits.md", "index.md"])
def test_the_hand_written_entry_pages_exist(page: str) -> None:
    assert (DOCS / page).is_file()
