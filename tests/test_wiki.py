# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The generated GitHub wiki mirrors docs/ and cannot drift from the site.

`scripts/gen_wiki.py` writes the wiki; `.github/workflows/wiki.yml` publishes
it. These checks run the real generator over the real tree, so a docs page
that cannot be mapped (a name collision, a link to nothing) fails here, in the
pull request that added it, rather than in the workflow after merge.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "gen_wiki.py"
LINK = re.compile(r"\]\(([^)\s]+)\)")


def _gen() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_wiki", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_wiki"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    return _gen()


@pytest.fixture(scope="module")
def files(gen: ModuleType) -> dict[str, str]:
    out: dict[str, str] = gen.render("abc1234")
    return out


def test_names_are_unique_over_the_real_tree(gen: ModuleType) -> None:
    nav = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text())["nav"]
    names = gen.page_set(nav)
    lowered = [n.lower() for n in names.values()]
    assert len(lowered) == len(set(lowered))
    assert names["getting-started/install.md"] == "Getting-Started-Install"
    assert names["index.md"] == "Home"
    assert names["packages/direwolf.md"] == "Packages-Direwolf"


def test_a_name_collision_is_an_error(gen: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen, "wiki_name", lambda path: "Same")
    with pytest.raises(gen.WikiError, match="both derive"):
        gen.page_set(["credits.md", "projects.md"])


def test_every_relative_link_resolves_to_an_output_page(files: dict[str, str]) -> None:
    pages = {f.removesuffix(".md") for f in files}
    bad: list[str] = []
    for fname, body in files.items():
        in_fence = False
        for line in body.split("\n"):
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
            if in_fence:
                continue
            for target in LINK.findall(line):
                if re.match(r"(?:[a-z][a-z0-9+.-]*:|//|#|/|<)", target, re.IGNORECASE):
                    continue
                if target.partition("#")[0] not in pages:
                    bad.append(f"{fname}: {target}")
    assert not bad, f"links that resolve to no wiki page: {bad[:10]}"


def test_home_has_the_banner_and_the_sidebar_exists(files: dict[str, str]) -> None:
    home = files["Home.md"]
    assert "generated" in home.split("\n")[0]
    assert "https://chiefgyk3d.github.io/Hammunition/" in home.split("\n\n")[0]
    sidebar = files["_Sidebar.md"]
    assert "(Getting-Started-Install)" in sidebar
    assert "(Software-by-activity)" in sidebar
    assert sidebar.index("(Getting-Started)") < sidebar.index("(Guides)")
    assert "abc1234" in files["_Footer.md"]


def test_the_footer_carries_no_clock_or_host(gen: ModuleType) -> None:
    assert "unknown" in gen.footer("unknown")
    assert gen.footer("abc1234") == gen.footer("abc1234")


def test_a_link_to_an_excluded_record_goes_to_github(files: dict[str, str]) -> None:
    mentions = [b for b in files.values() if "docs/DECISIONS.md" in b]
    assert mentions
    assert "DECISIONS.md" not in {f.removeprefix("docs/") for f in files}
    assert not any(re.search(r"\]\((?:\.\./)*DECISIONS\.md", b) for b in files.values()), (
        "a link to DECISIONS.md was left relative"
    )
    assert any(
        "](https://github.com/ChiefGyk3D/Hammunition/blob/main/docs/DECISIONS.md" in b
        for b in files.values()
    )


def test_the_project_records_are_not_pages(files: dict[str, str]) -> None:
    for record in ("Decisions", "Design", "Parity-Policy", "Questions", "Scope", "Session-Log"):
        assert f"{record}.md" not in files


def test_mkdocs_only_syntax_is_gone(files: dict[str, str]) -> None:
    for fname, body in files.items():
        assert not re.search(r"^\s*(?:!!!|\?\?\?)\s", body, re.MULTILINE), fname
        assert "[TOC]" not in body, fname
    assert "<a name=" in files["Guides-Audio-Routing.md"]


def test_software_by_activity_lists_every_unit(gen: ModuleType, files: dict[str, str]) -> None:
    page = files["Software-by-activity.md"]
    assert "## Operate the Station" in page
    for unit in ("direwolf", "wsjtx"):
        assert f"[{unit}](Packages-{gen.wiki_name(unit)})" in page


def test_no_output_file_is_empty(files: dict[str, str]) -> None:
    assert all(c.strip() for c in files.values())


def test_check_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "wiki"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not out.exists()


def test_check_compares_an_existing_output_dir(tmp_path: Path) -> None:
    run = [sys.executable, str(SCRIPT), "--out", str(tmp_path)]
    assert subprocess.run(run, capture_output=True, check=False).returncode == 0
    ok = subprocess.run([*run, "--check"], capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stdout
    (tmp_path / "Credits.md").write_text("changed\n")
    stale = subprocess.run([*run, "--check"], capture_output=True, text=True, check=False)
    assert stale.returncode == 1
    assert "Credits.md" in stale.stdout
