# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The changelog is assembled from fragments, never edited in a pull request.

Every pull request used to append to ``## Unreleased`` while ``main`` moved,
and conflicted on that file alone. A change now adds one file under
``changelog.d/``; ``scripts/changelog.py assemble`` turns them into the
release section. These tests hold the rule in place: nobody appends to
Unreleased again, every fragment is well formed, and a pull request that
changes the engine or the catalog carries one.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "changelog.py"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="scripts/ is not in this tree (target container)"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("changelog_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["changelog_script"] = module
    spec.loader.exec_module(module)
    return module


cl = _load()

BASE = """\
# Changelog

Intro.

## Unreleased

Nothing yet.

## v0.1.0 — 2026-01-01 — first

- **Old.** (#1)
"""


def _tree(tmp_path: Path, fragments: dict[str, str], changelog: str = BASE) -> Path:
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "README.md").write_text("how\n")
    for name, body in fragments.items():
        (tmp_path / "changelog.d" / name).write_text(body)
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    return tmp_path


FRAGS = {
    "30.fixed.md": "- **Fixed thing.** (#30)\n",
    "12.added.md": "- **Added thing**\n  wrapped line. (#12)\n",
    "9.added.md": "- **Added earlier.** (#9)\n",
    "40.decision.md": "- **A decision** (**D-099**). (#40)\n",
}


def test_assemble_orders_by_kind_then_number_and_resets_unreleased(tmp_path: Path) -> None:
    root = _tree(tmp_path, FRAGS)
    rc = cl.main(["--root", str(root), "assemble", "--version", "v0.2.0", "--date", "2026-02-03"])
    assert rc == 0
    text = (root / "CHANGELOG.md").read_text()
    assert "## Unreleased\n\nNothing yet.\n\n## v0.2.0 — 2026-02-03\n\n" in text
    body = text.split("## v0.2.0 — 2026-02-03\n\n")[1].split("## v0.1.0")[0]
    order = [m.group(1) for m in re.finditer(r"^- \*\*(.+?)[.*]", body, re.M)]
    assert order == ["Added earlier", "Added thing", "Fixed thing", "A decision"]
    assert "  wrapped line. (#12)" in body
    assert text.index("v0.2.0") < text.index("v0.1.0")
    assert sorted(p.name for p in (root / "changelog.d").iterdir()) == ["README.md"]


def test_assemble_accepts_a_summary_in_the_heading(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"1.added.md": "- **A.**\n"})
    args = ["--version", "v0.2.0", "--date", "2026-02-03", "--summary", "the rig"]
    assert cl.main(["--root", str(root), "assemble", *args]) == 0
    assert "## v0.2.0 — 2026-02-03 — the rig\n" in (root / "CHANGELOG.md").read_text()


def test_assemble_is_deterministic(tmp_path: Path) -> None:
    outs = []
    for n in ("a", "b"):
        sub = tmp_path / n
        sub.mkdir()
        # Different creation order, same fragments.
        frags = dict(reversed(list(FRAGS.items()))) if n == "b" else FRAGS
        root = _tree(sub, frags)
        args = ["--root", str(root), "assemble", "--version", "v0.2.0", "--date", "2026-02-03"]
        assert cl.main(args) == 0
        outs.append((root / "CHANGELOG.md").read_text())
    assert outs[0] == outs[1]


def test_assemble_is_idempotent_a_second_run_changes_nothing(tmp_path: Path) -> None:
    root = _tree(tmp_path, FRAGS)
    args = ["--root", str(root), "assemble", "--version", "v0.2.0", "--date", "2026-02-03"]
    assert cl.main(args) == 0
    once = (root / "CHANGELOG.md").read_text()
    assert cl.main(args) != 0  # nothing to assemble: refuses, does not duplicate
    assert (root / "CHANGELOG.md").read_text() == once


def test_assemble_refuses_a_version_already_released(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"1.added.md": "- **A.**\n"})
    args = ["--root", str(root), "assemble", "--version", "v0.1.0", "--date", "2026-02-03"]
    assert cl.main(args) != 0
    assert (root / "changelog.d" / "1.added.md").exists()  # nothing deleted on refusal


@pytest.mark.parametrize(
    ("version", "date"),
    [
        ("0.2.0", "2026-02-03"),
        ("v0.2", "2026-02-03"),
        ("v0.2.0", "2026-2-3"),
        ("v0.2.0", "2026-13-01"),
    ],
)
def test_assemble_refuses_a_malformed_version_or_date(
    tmp_path: Path, version: str, date: str
) -> None:
    root = _tree(tmp_path, {"1.added.md": "- **A.**\n"})
    assert cl.main(["--root", str(root), "assemble", "--version", version, "--date", date]) != 0
    assert (root / "changelog.d" / "1.added.md").exists()


def test_preview_prints_what_unreleased_would_hold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(tmp_path, FRAGS)
    assert cl.main(["--root", str(root), "preview"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("- **Added earlier.** (#9)")
    assert "**A decision**" in out
    assert (root / "changelog.d" / "9.added.md").exists()  # preview changes nothing
    (tmp_path / "e").mkdir()
    empty = _tree(tmp_path / "e", {})
    assert cl.main(["--root", str(empty), "preview"]) == 0
    assert capsys.readouterr().out.strip() == "Nothing yet."


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("1.bogus.md", "- **A.**\n"),  # unknown kind
        ("1.md", "- **A.**\n"),  # no kind
        ("1.added.md", "Not a bullet.\n"),  # does not start with its bullet
        ("1.added.md", "\n"),  # empty
        ("1.added.md", "- **A.**\n\n- **B.**\n"),  # two entries in one file
        ("1.added.txt", "- **A.**\n"),  # not markdown
    ],
)
def test_a_malformed_fragment_is_refused_by_name(
    tmp_path: Path, name: str, body: str, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(tmp_path, {name: body})
    assert cl.main(["--root", str(root), "preview"]) != 0
    assert name in capsys.readouterr().err


def test_the_real_fragments_are_well_formed() -> None:
    # Every fragment checked in, whatever branch this is.
    cl.load_fragments(REPO_ROOT / "changelog.d")


def test_unreleased_in_the_real_changelog_is_only_nothing_yet() -> None:
    # The whole point: no pull request appends here again. A release is made by
    # `assemble`, which leaves exactly this behind.
    text = (REPO_ROOT / "CHANGELOG.md").read_text()
    match = re.search(r"^## Unreleased\n(.*?)(?=^## )", text, re.M | re.S)
    assert match, "CHANGELOG.md has no '## Unreleased' heading"
    assert match.group(1).strip() == "Nothing yet.", (
        "Do not edit CHANGELOG.md in a pull request: add changelog.d/<pr>.<kind>.md "
        "instead (changelog.d/README.md)"
    )


def test_the_real_changelog_has_release_headings_in_the_established_shape() -> None:
    text = (REPO_ROOT / "CHANGELOG.md").read_text()
    headings = re.findall(r"^## (?!Unreleased).*$", text, re.M)
    assert headings
    for h in headings:
        assert re.match(r"^## v\d+\.\d+\.\d+ — \d{4}-\d{2}-\d{2}( — .+)?$", h), h


# ---------------------------------------------------------------------------
# A pull request that changes the engine, the catalog or a guide carries a
# fragment. Mirrors the commit-claims job: it runs on a pull request, where
# there is a base to diff against, and skips everywhere else.
# ---------------------------------------------------------------------------

NEEDS_FRAGMENT = ("src/", "catalog/", "docs/guides/")


def needs_fragment(changed: list[str]) -> bool:
    return any(p.startswith(NEEDS_FRAGMENT) for p in changed)


def has_fragment(added: list[str]) -> bool:
    return any(
        p.startswith("changelog.d/") and p.endswith(".md") and p != "changelog.d/README.md"
        for p in added
    )


def test_the_fragment_rule_itself() -> None:
    assert needs_fragment(["src/hammunition/x.py"])
    assert needs_fragment(["catalog/packages/a.yaml"])
    assert needs_fragment(["docs/guides/gps.md"])
    assert not needs_fragment(["docs/DECISIONS.md", "tests/test_x.py", "CLAUDE.md"])
    assert has_fragment(["changelog.d/12.added.md"])
    assert not has_fragment(["changelog.d/README.md", "CHANGELOG.md"])


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout


def test_a_pull_request_that_changes_the_product_carries_a_fragment() -> None:
    base = os.environ.get("GITHUB_BASE_REF")
    if not base:
        pytest.skip("not a pull request run (GITHUB_BASE_REF is unset)")
    ref = f"origin/{base}"
    try:
        _git("rev-parse", "--verify", ref)
    except subprocess.CalledProcessError:
        if os.environ.get("HAMMUNITION_REQUIRE_PR_RANGE"):
            pytest.fail(f"{ref} is not fetched; the job needs fetch-depth: 0")
        pytest.skip(f"{ref} is not available in this checkout")
    changed = _git("diff", "--name-only", f"{ref}...HEAD").split()
    if not needs_fragment(changed):
        return
    added = _git("diff", "--name-only", "--diff-filter=A", f"{ref}...HEAD").split()
    assert has_fragment(added), (
        "This pull request changes src/, catalog/ or docs/guides/ and adds no "
        "changelog fragment. Add changelog.d/<pr>.<kind>.md (kinds: "
        f"{', '.join(cl.KINDS)}); see changelog.d/README.md. Do not edit CHANGELOG.md."
    )
