#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 The Hammunition contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fail on broken internal documentation references.

CLAUDE.md: "CI fails on broken internal links."

Two kinds are checked, because our docs use both:

1. Markdown links — ``[text](path)``
2. Backtick-quoted repo paths — ``` `docs/reference/dispositions.md` ```

The second matters more in practice: this project's prose references files by
backticked path far more often than by markdown link, so a checker that only
understood markdown links would validate almost nothing.

External URLs are not checked. They fail for reasons unrelated to our
correctness and would make the build flaky.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
BACKTICK_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:md|ya?ml|py|toml|sh|cfg))`")

SKIP_SCHEMES = ("http://", "https://", "mailto:", "#")

# Anchored to the repo root, exactly like the `.gitignore` entries they mirror.
# The unanchored form also matched `docs/reference/` — a required documentation
# section — and silently excluded all seven inventory documents from checking,
# which is the same bug the `.gitignore` had. A test asserts they are scanned.
SKIP_ROOTS = {"reference", "vendor"}
SKIP_ANYWHERE = {".git", "node_modules", ".venv", "__pycache__"}

# Paths named in prose that are deliberately not repo files.
#
# Third-party paths live inside AHRL's or 73Linux's trees. They exist locally
# under the gitignored reference/ directory but never in a CI checkout, so they
# must be allowlisted by name rather than by existence — otherwise the docs
# would have to stop citing their evidence, which is worse than this list.
ALLOW_MISSING = {
    # operator-local config, gitignored by construction
    "example.local.yml",
    "station.local.yml",
    # AHRL v27 tarball (reference/)
    "bin/install_ahrl",
    "bin/test_menus_debian13.py",
    "bin/find_errors_ahrl",
    "bin/not_on_rpi.py",
    # build scripts inside upstream source trees AHRL unpacks (reference/)
    "./autogen.sh",
    "./build_linux.sh",
    # 73Linux repository
    "73.sh",
    "bin/menu.sh",
    "bin/runner.sh",
    "bin/template-maker.sh",
}


def _candidates(path: str, doc: Path) -> list[Path]:
    """A backticked path may be repo-relative or relative to the doc."""
    return [REPO_ROOT / path, doc.parent / path]


def scanned_docs() -> list[Path]:
    """Every markdown file the checker will actually open, repo-relative.

    Exposed so the regression test can assert on the *real* filter rather than
    reimplementing it — a test that copies the logic it is guarding passes
    happily when the logic is broken, which is how the original bug survived.
    """
    out: list[Path] = []
    for md in sorted(REPO_ROOT.rglob("*.md")):
        rel = md.relative_to(REPO_ROOT)
        if rel.parts[0] in SKIP_ROOTS or any(p in SKIP_ANYWHERE for p in rel.parts):
            continue
        out.append(rel)
    return out


def check() -> int:
    broken: list[str] = []
    checked = 0

    for rel in scanned_docs():
        md = REPO_ROOT / rel
        text = md.read_text()

        for target in MD_LINK.findall(text):
            if target.startswith(SKIP_SCHEMES):
                continue
            path, _, _anchor = target.partition("#")
            if not path:
                continue
            checked += 1
            if not (md.parent / path).resolve().exists():
                broken.append(f"{rel}: [link] {target}")

        for target in BACKTICK_PATH.findall(text):
            if target in ALLOW_MISSING or Path(target).name in ALLOW_MISSING:
                continue
            if "/" not in target:
                continue
            checked += 1
            if not any(c.exists() for c in _candidates(target, md)):
                broken.append(f"{rel}: [path] {target}")

    print(f"checked {checked} internal reference(s)")
    if broken:
        print(f"\n{len(broken)} broken:", file=sys.stderr)
        for item in sorted(set(broken)):
            print(f"  {item}", file=sys.stderr)
        return 1
    print("no broken internal references")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
