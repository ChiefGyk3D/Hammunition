#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assemble CHANGELOG.md from the fragments under changelog.d/.

A pull request adds one file, ``changelog.d/<pr-or-branch>.<kind>.md``,
holding its entry exactly as it should read in the changelog, starting with
its bullet. Nobody edits CHANGELOG.md in a pull request: every change used to
append to ``## Unreleased`` and conflict with every other. This is the
towncrier pattern in the standard library.

    changelog.py preview
    changelog.py assemble --version v0.20.0 --date 2026-10-09 [--summary TEXT]

``preview`` prints the section the fragments would produce and changes
nothing. ``assemble`` writes it into CHANGELOG.md as a new release section,
deletes the fragments, and leaves ``## Unreleased`` reading ``Nothing yet.``
Entries are ordered by kind (``KINDS``), then by the fragment's name with
numbers compared as numbers, so the output does not depend on the order the
files were created in.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

KINDS = ("added", "changed", "fixed", "removed", "docs", "decision")
NOTHING_YET = "Nothing yet."
_NAME = re.compile(
    r"^(?P<id>[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*)\.(?P<kind>[a-z]+)\.md$"
)
_VERSION = re.compile(r"^v\d+\.\d+\.\d+$")


class FragmentError(Exception):
    """A fragment that cannot be assembled; the message names the file."""


def _natural(text: str) -> list[tuple[int, int, str]]:
    return [
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in re.split(r"(\d+)", text)
        if part
    ]


def load_fragments(directory: Path) -> list[tuple[str, str, str]]:
    """Return ``(kind, name, entry)`` for every fragment, in assembly order."""
    found: list[tuple[str, str, str]] = []
    errors: list[str] = []
    if not directory.is_dir():
        raise FragmentError(f"{directory} does not exist")
    for path in sorted(directory.iterdir()):
        if path.name == "README.md" or path.name.startswith("."):
            continue
        match = _NAME.match(path.name)
        if match is None or match["kind"] not in KINDS:
            errors.append(
                f"{path.name}: name must be <pr-or-branch>.<kind>.md with kind one of "
                f"{', '.join(KINDS)}"
            )
            continue
        entry = path.read_text(encoding="utf-8").strip("\n")
        entry = "\n".join(line.rstrip() for line in entry.splitlines())
        if not entry.startswith("- "):
            errors.append(f"{path.name}: must hold one entry starting with its '- ' bullet")
        elif re.search(r"\n\n+- ", entry):
            errors.append(f"{path.name}: holds more than one entry; one entry per file")
        else:
            found.append((match["kind"], path.name, entry))
    if errors:
        raise FragmentError("\n".join(errors))
    found.sort(key=lambda f: (KINDS.index(f[0]), _natural(f[1])))
    return found


def render_entries(fragments: list[tuple[str, str, str]]) -> str:
    if not fragments:
        return NOTHING_YET + "\n"
    return "\n\n".join(entry for _, _, entry in fragments) + "\n"


def release_section(
    fragments: list[tuple[str, str, str]], version: str, date: str, summary: str | None
) -> str:
    heading = f"## {version} — {date}" + (f" — {summary}" if summary else "")
    return f"{heading}\n\n{render_entries(fragments)}"


def assemble_text(
    changelog: str,
    fragments: list[tuple[str, str, str]],
    version: str,
    date: str,
    summary: str | None,
) -> str:
    if not _VERSION.match(version):
        raise FragmentError(f"version {version!r} must look like v0.20.0")
    try:
        parsed = datetime.date.fromisoformat(date)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != date:
        raise FragmentError(f"date {date!r} must be a real YYYY-MM-DD date")
    if not fragments:
        raise FragmentError("no fragments under changelog.d/: nothing to assemble")
    if re.search(rf"^## {re.escape(version)}\b", changelog, re.M):
        raise FragmentError(f"CHANGELOG.md already has a section for {version}")
    match = re.search(r"^## Unreleased\n.*?(?=^## )", changelog, re.M | re.S)
    if match is None:
        raise FragmentError("CHANGELOG.md has no '## Unreleased' section followed by a release")
    replacement = (
        f"## Unreleased\n\n{NOTHING_YET}\n\n"
        + release_section(fragments, version, date, summary)
        + "\n"
    )
    return changelog[: match.start()] + replacement + changelog[match.end() :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview", help="print the section Unreleased would contain")
    asm = sub.add_parser("assemble", help="write a release section and delete the fragments")
    asm.add_argument("--version", required=True)
    asm.add_argument("--date", required=True)
    asm.add_argument("--summary", help="text after the date in the release heading")
    args = parser.parse_args(argv)

    directory = args.root / "changelog.d"
    changelog_path = args.root / "CHANGELOG.md"
    try:
        fragments = load_fragments(directory)
        if args.command == "preview":
            sys.stdout.write(render_entries(fragments))
            return 0
        new = assemble_text(
            changelog_path.read_text(encoding="utf-8"),
            fragments,
            args.version,
            args.date,
            args.summary,
        )
    except FragmentError as err:
        print(f"changelog: {err}", file=sys.stderr)
        return 2
    changelog_path.write_text(new, encoding="utf-8")
    for _, name, _ in fragments:
        (directory / name).unlink()
    print(f"changelog: {args.version} written with {len(fragments)} entries; fragments removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
