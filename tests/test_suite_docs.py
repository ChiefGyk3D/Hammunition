# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The suite and EMCOMM pages (issue #298) cannot drift from the catalog.

A suite page names its project's repository. That URL is read from the
catalog's manifest where one exists, never trusted from the page: a page that
sends a reader to a repository that is not the project is a wrong page, and
"verify the URL, do not guess it" is the issue's first rule. Every page follows
`docs/contributing/template-suite-project.md`, and every application has a page
that says how it installs and how it works offline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hammunition.manifest.load import load_catalog

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
SUITE = DOCS / "suite"

#: page -> the manifest whose upstream_url must be that page's repository, or
#: the URL itself where the project has no manifest (it is not installed by us).
PROJECTS: dict[str, str] = {
    "tray.md": "hammunition-tray",
    "hill.md": "hammunition-hill",
    "console.md": "hammunition-console",
    "gps-tether.md": "gps-tether",
    "hammunition.md": "https://github.com/ChiefGyk3D/Hammunition",
    "bunker.md": "https://github.com/ChiefGyk3D/hammunition-bunker",
}

HEADINGS = (
    "## At a glance",
    "## What it is for",
    "## Dependencies",
    "## Install and first run",
    "## Basic usage",
    "## Offline behaviour",
    "## Troubleshooting",
    "## Where the details live",
)


@pytest.fixture(scope="module")
def catalog() -> dict[str, object]:
    return dict(load_catalog(REPO_ROOT / "catalog" / "packages"))


def _repository(page: Path) -> str:
    m = re.search(r"\*\*Repository\*\*\s*\|\s*<(https://[^>]+)>", page.read_text())
    assert m, f"{page.name}: no '**Repository** | <url>' row in At a glance"
    return m.group(1)


@pytest.mark.parametrize("name", sorted(PROJECTS))
def test_the_repository_link_is_the_one_the_catalog_names(
    name: str, catalog: dict[str, object]
) -> None:
    expected = PROJECTS[name]
    if not expected.startswith("https://"):
        expected = catalog[expected].documentation.upstream_url  # type: ignore[attr-defined]
    assert _repository(SUITE / name) == expected


@pytest.mark.parametrize("name", sorted(PROJECTS))
def test_a_suite_page_follows_the_template(name: str) -> None:
    text = (SUITE / name).read_text()
    positions = [text.find(h + "\n") for h in HEADINGS]
    assert all(p >= 0 for p in positions), (
        f"{name} lacks one of {HEADINGS}: see docs/contributing/template-suite-project.md"
    )
    assert positions == sorted(positions), f"{name}: headings out of template order"
    for label in ("**Purpose**", "**Status**", "**Platforms**", "**Independent?**"):
        assert label in text, f"{name}: 'At a glance' lacks {label}"
    assert "**Report problems**" in text


def test_the_suite_index_lists_every_project_page() -> None:
    index = (SUITE / "index.md").read_text()
    for name in PROJECTS:
        assert f"]({name})" in index, f"docs/suite/index.md does not link {name}"
    pages = {p.name for p in SUITE.glob("*.md")} - {"index.md"}
    assert pages == set(PROJECTS), "a suite page is not in tests/test_suite_docs.py::PROJECTS"


def test_every_application_has_a_page_with_install_and_offline_sections(
    catalog: dict[str, object],
) -> None:
    missing = [n for n in catalog if not (DOCS / "packages" / f"{n}.md").is_file()]
    assert not missing, f"applications without a generated page: {missing}"
    for name in catalog:
        text = (DOCS / "packages" / f"{name}.md").read_text()
        assert "## Install and launch" in text, f"{name}: no install section"
        assert "## Offline use" in text, f"{name}: no offline section"


def test_the_suite_units_document_offline_use_and_a_first_task(catalog: dict[str, object]) -> None:
    for name in (
        "hammunition-tray",
        "hammunition-tray-qt",
        "hammunition-hill",
        "hammunition-console",
        "gps-tether",
        "pat",
        "direwolf",
        "osm-regions",
        "kiwix-library",
        "ics-forms",
    ):
        doc = catalog[name].documentation  # type: ignore[attr-defined]
        assert doc.offline and doc.first_task, f"{name}: offline and first_task are required"


def test_the_emcomm_pages_keep_internet_lan_and_radio_apart() -> None:
    text = (DOCS / "emcomm" / "index.md").read_text().lower()
    for word in ("internet", "local network", "radio"):
        assert word in text, f"emcomm/index.md does not distinguish {word}"
    data = " ".join((DOCS / "emcomm" / "offline-data.md").read_text().lower().split())
    assert "does not establish that it exists today, is open" in data, (
        "a mapped facility is not proof it is open; offline-data.md must say so"
    )
