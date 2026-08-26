#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 The Hammunition contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Audit .gitignore for the unanchored-pattern bug.

Three times now a `.gitignore` rule written for a project-root output directory
has been unanchored, so it also matched a directory of the same name deeper in
the tree and silently excluded work:

* `reference/` also matched `docs/reference/`, a required documentation section.
  Seven generated inventories were untracked and the doc-link checker, which
  skipped the same directory for the same reason, reported success.
* `state/` also matched `src/hammunition/state/`, a source package. `git add`
  refused it, the commit went through without it, and mypy, pytest and ruff all
  stayed green because they read the working tree rather than the index.

The regression tests written after each are good backstops and are the wrong
shape: each asserts something about the *one* directory that already broke. This
asserts the property.

Two checks, because the failures have two different shapes:

**Nothing in the source tree may be ignored.** Enumerates the working tree under
the source roots and asks git. Catches a collision the moment the directory
exists, which is one commit earlier than `git add` refusing it and several
commits earlier than someone noticing.

**Every pattern must be anchored, or justified.** Catches a collision *before*
the directory exists, which is the only check that would have prevented all
three rather than detected them. A pattern naming a build artifact or an output
directory is anchored to the repo root or it is a bug waiting for a filename.
Patterns that must match at any depth -- caches, editor cruft, and above all
secrets -- say so here, by name, with a reason.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories whose contents are the project. Nothing under these may be ignored.
SOURCE_ROOTS = ("src", "tests", "scripts", "catalog", "docs", "containers", ".github")

# Paths that are legitimately ignored inside a source root: build and cache
# output that appears wherever the tool that made it ran.
LEGITIMATE_INSIDE_SOURCE = (
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".venv",
    "_build",
    ".egg-info",
)

# Patterns allowed to be unanchored, each with the reason. Anything not here and
# not anchored is a finding. Kept as an explicit list rather than a heuristic:
# the whole failure mode is a rule that looked obviously fine.
JUSTIFIED_UNANCHORED: dict[str, str] = {
    # Secrets. Unanchored is the point -- a key committed from a subdirectory is
    # exactly as leaked as one committed from the root.
    ".env": "secret, must match at any depth",
    ".env.*": "secret, must match at any depth",
    "*.pem": "secret, must match at any depth",
    "*.key": "secret, must match at any depth",
    "*.p12": "secret, must match at any depth",
    "*.pfx": "secret, must match at any depth",
    "*.asc": "secret, must match at any depth",
    "*.gpg": "secret, must match at any depth",
    "secrets.yml": "secret, must match at any depth",
    "secrets.yaml": "secret, must match at any depth",
    "*_rsa": "secret, must match at any depth",
    "*_ed25519": "secret, must match at any depth",
    ".netrc": "secret, must match at any depth",
    ".credentials": "secret, must match at any depth",
    # Operator-specific station config. Same reasoning: a callsign committed from
    # a subdirectory is still committed.
    "station.local.yml": "operator config, must match at any depth",
    "station.local.yaml": "operator config, must match at any depth",
    "*.local.yml": "operator config, must match at any depth",
    "*.local.yaml": "operator config, must match at any depth",
    # Third-party archives. D-011: provenance stays clean wherever the tarball
    # was unpacked.
    **{
        ext: "third-party archive, must match at any depth (D-011)"
        for ext in (
            "*.tar",
            "*.tar.gz",
            "*.tgz",
            "*.tar.bz2",
            "*.tar.xz",
            "*.zip",
            "*.7z",
            "*.rar",
            "*.gz",
            "*.bz2",
            "*.xz",
            "*.iso",
            "*.img",
            "*.deb",
            "*.rpm",
            "*.AppImage",
            "*.snap",
            "*.flatpak",
            "*.dmg",
            "*.qcow2",
            "*.whl",
        )
    },
    # Tool caches and virtualenvs. Created wherever the tool was run.
    **{
        name: "tool cache or virtualenv, created at any depth"
        for name in (
            "__pycache__/",
            "*.py[cod]",
            "*$py.class",
            "*.so",
            ".eggs/",
            "*.egg-info/",
            "*.egg",
            ".venv/",
            "venv/",
            "ENV/",
            "env/",
            ".python-version",
            ".pytest_cache/",
            ".mypy_cache/",
            ".ruff_cache/",
            ".tox/",
            ".nox/",
            ".hypothesis/",
            ".dmypy.json",
            "dmypy.json",
            ".cache/",
            ".container-cache/",
            ".hammunition/",
            ".direnv/",
            "share/python-wheels/",
            "docs/_build/",
            ".docusaurus/",
        )
    },
    # Editor and OS cruft.
    **{
        name: "editor or OS cruft, appears at any depth"
        for name in (".idea/", ".vscode/", "*.swp", "*.swo", "*~", ".DS_Store", "Thumbs.db")
    },
    # Generated udev rules. Unanchored on purpose -- the engine may write them
    # anywhere -- with an explicit negation for the catalog's own.
    "*.rules": "engine output, written wherever the operator points it",
    # Run output. A log or a coverage annotation is written next to whatever
    # produced it, so anchoring these would not catch the files they exist for.
    # The working-tree check is what keeps them honest.
    "*.log": "run output, written wherever the run happened",
    "*.cover": "coverage annotation, written next to the source it annotates",
    ".Python": "virtualenv marker, created inside whatever venv directory exists",
}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def patterns() -> list[tuple[int, str]]:
    """Every effective pattern in .gitignore, with its line number."""
    found = []
    for number, raw in enumerate((REPO_ROOT / ".gitignore").read_text().splitlines(), 1):
        line = raw.strip()
        if line and not line.startswith("#"):
            found.append((number, line))
    return found


def is_anchored(pattern: str) -> bool:
    """git anchors a pattern to the .gitignore's directory if it has a slash.

    A leading slash anchors it. So does an interior slash -- `docs/_build/`
    matches only at the root. A trailing slash alone means "directory" and
    anchors nothing, which is the entire bug.
    """
    body = pattern.rstrip("/")
    return body.startswith("/") or "/" in body


def unjustified(entries: list[tuple[int, str]] | None = None) -> list[tuple[int, str]]:
    """Findings among *entries*, defaulting to the repository's own .gitignore.

    Parameterised so the tests can assert the property on synthetic patterns --
    including the two that actually broke -- rather than only on a .gitignore
    that currently passes.
    """
    findings = []
    for number, pattern in entries if entries is not None else patterns():
        if pattern.startswith("!"):
            continue  # a negation cannot over-match; it can only rescue
        if is_anchored(pattern):
            continue
        if pattern in JUSTIFIED_UNANCHORED:
            continue
        findings.append((number, pattern))
    return findings


def ignored_source_paths() -> list[str]:
    """Working-tree paths under the source roots that git would ignore."""
    candidates: list[str] = []
    for root in SOURCE_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            relative = path.relative_to(REPO_ROOT).as_posix()
            if any(part in relative for part in LEGITIMATE_INSIDE_SOURCE):
                continue
            candidates.append(relative + ("/" if path.is_dir() else ""))
    if not candidates:
        return []
    # check-ignore --no-index so the answer is about the rules, not about what
    # happens to be tracked already. A tracked file is exempt from ignore rules,
    # which is precisely why the state/ bug survived a clean test run.
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=REPO_ROOT,
        input="\n".join(candidates),
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    problems = 0

    swallowed = ignored_source_paths()
    if swallowed:
        problems += len(swallowed)
        print(f"FAIL: {len(swallowed)} path(s) in the source tree are git-ignored:")
        for path in swallowed:
            rule = git("check-ignore", "-v", "--no-index", path).stdout.strip()
            print(f"  {path}\n      {rule}")
    else:
        print("ok: nothing in the source tree is ignored")

    loose = unjustified()
    if loose:
        problems += len(loose)
        print(f"\nFAIL: {len(loose)} unanchored pattern(s) with no recorded reason:")
        for number, pattern in loose:
            print(f"  .gitignore:{number}  {pattern}")
        print(
            "\n  Anchor it to the repo root (/pattern) if it names a project-root\n"
            "  artifact, or add it to JUSTIFIED_UNANCHORED with the reason it must\n"
            "  match at any depth."
        )
    else:
        print(f"ok: all {len(patterns())} patterns are anchored or justified")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
