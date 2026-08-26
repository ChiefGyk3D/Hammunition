#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Refuse a commit whose message describes a change the commit does not contain.

D-031. Three bugs in this repository share one shape — **reading the result you
expected instead of the one you got**:

1. A D-028 amendment matched anchor text that did not exist. The `sed` reported
   success because `sed` always does; the grep that would have caught it was run
   *after* the commit. The commit message described a change the commit did not
   contain.
2. The udev sweep's extraction step failed on every one of 280 packages while
   still emitting 2,750 rows, because `dpkg-deb -x` writes files and *then*
   exits non-zero. The row count was read and reported as success; the log was
   not read.
3. A `state/` directory was written and never committed, because a `.gitignore`
   pattern matched it. Nothing errored. The work simply was not there.

D-025 covers claims that become load-bearing later. This covers the narrower and
more embarrassing case: verifying your own writes, at the moment you make them,
without having to remember to.

Three checks, all mechanical:

``anchors``
    A message that *claims* something about a decision or question — "amends
    D-028", "closes Q-007" — must be accompanied by a diff that touches a line
    mentioning it. Merely citing one as rationale ("per D-014") claims nothing
    and is left alone. Bug 1.
``claimed paths``
    A message that claims something about a path must have that path in the
    staged file list. Bugs 1 and 3.
``phantom paths``
    Any repo path the message mentions which exists on disk but is neither
    tracked nor staged. That is precisely the state where you believe you added
    a file and git disagrees, and it is silent in every other tool. Bug 3.

Run as a ``commit-msg`` hook (see ``.githooks/``) or over an existing commit
with ``--rev``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Verbs that turn a mention into a claim. "per D-014" asserts nothing about the
# diff; "amends D-014" asserts a great deal. Kept deliberately short — a list
# that tries to catch every phrasing produces false positives, and a check that
# cries wolf is a check people disable.
CLAIM_VERBS = (
    r"add(?:s|ed|ing)?|amend(?:s|ed|ing)?|updat(?:e|es|ed|ing)|record(?:s|ed|ing)?|"
    r"clos(?:e|es|ed|ing)|extend(?:s|ed|ing)?|supersed(?:e|es|ed|ing)|"
    r"retract(?:s|ed|ing)?|correct(?:s|ed|ing)?|fix(?:es|ed|ing)?|"
    r"mov(?:e|es|ed|ing)|renam(?:e|es|ed|ing)|remov(?:e|es|ed|ing)|"
    r"delet(?:e|es|ed|ing)|writ(?:e|es|ing)|wrote|creat(?:e|es|ed|ing)|"
    r"introduc(?:e|es|ed|ing)|drop(?:s|ped|ping)?|split(?:s|ting)?"
)
ANCHOR = r"[DQ]-\d{3}"
# A statement that a decision's *content* has changed, without a claim verb in
# sight. This is the phrasing of the bug that prompted the check: "D-028 no
# longer rests on an esptool constant; it rests on three captures" — a
# present-tense assertion about what the document says, in a commit that never
# touched the document. Verbs alone would not have caught it.
STATE_CHANGE = r"no longer|now|instead|as of|has been|have been|already"
# "amends D-028", "D-028 is amended" — satisfied by any changed line mentioning
# it, because the work may legitimately live in code or in a manifest.
CLAIMED_ANCHOR = re.compile(
    rf"(?:\b(?:{CLAIM_VERBS})\b[^.\n]{{0,80}}?({ANCHOR}))"
    rf"|(?:({ANCHOR})\b[^.\n]{{0,40}}?\b(?:is|are|was|were)\s+(?:{CLAIM_VERBS})\b)",
    re.IGNORECASE,
)
# "D-028 no longer rests on…", "now D-028 covers…" — an assertion about what the
# *document* says, which only the document can satisfy. The distinction matters:
# 717ba26 claimed exactly this and passed a weaker version of the check, because
# it changed schema docstrings that happen to mention D-028 while never touching
# the decision itself.
RESTATED_ANCHOR = re.compile(
    rf"(?:({ANCHOR})\b[^.\n]{{0,40}}?\b(?:{STATE_CHANGE})\b)"
    rf"|(?:\b(?:{STATE_CHANGE})\b[^.\n]{{0,40}}?({ANCHOR})\b)",
    re.IGNORECASE,
)

# A repo-relative path: `catalog/hardware/x.yaml`, scripts/foo.py, docs/BAR.md.
# Backticked or bare; must contain a slash or a known extension so that ordinary
# prose does not register as a path.
PATH = re.compile(
    r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,6}|[A-Za-z0-9_-]+/[A-Za-z0-9_./-]*)`"
    r"|(?<![\w/`])((?:src|scripts|tests|catalog|docs|containers|\.github)/[A-Za-z0-9_./-]+)"
)
CLAIMED_PATH = re.compile(
    rf"\b(?:{CLAIM_VERBS})\b[^.\n]{{0,100}}?" + PATH.pattern,
    re.IGNORECASE,
)


ANCHOR_HOME = {"D": Path("docs/DECISIONS.md"), "Q": Path("docs/QUESTIONS.md")}
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    ).stdout


def paths_in(text: str, pattern: re.Pattern[str]) -> set[str]:
    found: set[str] = set()
    for match in pattern.finditer(text):
        for group in match.groups():
            if group and "/" in group:
                found.add(group.rstrip("/.,;:"))
    return found


def anchors_in(text: str, pattern: re.Pattern[str]) -> set[str]:
    return {g.upper() for m in pattern.finditer(text) for g in m.groups() if g}


def section_range(anchor: str) -> tuple[Path, int, int] | None:
    """Line span of an anchor's own section in the document that owns it.

    Needed because a commit that genuinely amends D-028 usually adds prose
    *inside* the section without repeating the string "D-028" anywhere in the
    added lines. Requiring the literal token would flag exactly the commits that
    did the work — a check that punishes correct behaviour gets switched off.
    """
    home = ANCHOR_HOME.get(anchor[0].upper())
    if home is None or not (REPO_ROOT / home).is_file():
        return None
    lines = (REPO_ROOT / home).read_text().splitlines()
    start = next(
        (n for n, line in enumerate(lines, 1) if re.match(rf"^#+\s+{anchor}\b", line)), None
    )
    if start is None:
        return None
    end = next(
        (
            n
            for n, line in enumerate(lines[start:], start + 1)
            if re.match(r"^#+\s+[DQ]-\d{3}\b", line)
        ),
        len(lines),
    )
    return home, start, end


def touched_lines(diff: str, path: Path) -> set[int]:
    """Post-image line numbers the diff writes to, for one file."""
    touched: set[int] = set()
    current: str | None = None
    line_no = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        if line.startswith("@@"):
            match = HUNK.match(line)
            line_no = int(match.group(1)) if match else 0
            continue
        if current != str(path):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            touched.add(line_no)
            line_no += 1
        elif line.startswith((" ", "-")) and not line.startswith("---"):
            if not line.startswith("-"):
                line_no += 1
            else:
                touched.add(line_no)
    return touched


def check(message: str, changed: set[str], diff: str, tracked: set[str]) -> list[str]:
    problems: list[str] = []

    # Strip comment lines a commit template leaves behind.
    body = "\n".join(line for line in message.splitlines() if not line.startswith("#"))

    restated = anchors_in(body, RESTATED_ANCHOR)
    for anchor in sorted(anchors_in(body, CLAIMED_ANCHOR) | restated):
        in_section = False
        span = section_range(anchor)
        if span is not None:
            home, start, end = span
            in_section = bool(touched_lines(diff, home) & set(range(start, end + 1)))

        if anchor in restated:
            if not in_section:
                problems.append(
                    f"the message states what {anchor} says or no longer says, but "
                    f"this commit does not touch {anchor}'s own section. A mention "
                    f"of {anchor} elsewhere in the diff does not settle it — that is "
                    f"how 717ba26 passed while the amendment it described had "
                    f"silently matched nothing."
                )
            continue

        mentioned = any(
            anchor in line
            for line in diff.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )
        if not (mentioned or in_section):
            problems.append(
                f"the message claims something about {anchor}, but no added or "
                f"removed line in this commit mentions it. This is the D-028 "
                f"amendment bug exactly: an anchor-text edit that matched nothing "
                f"still reports success, and the commit message ends up describing "
                f"a change the commit does not contain."
            )

    for path in sorted(paths_in(body, CLAIMED_PATH)):
        if path not in changed and not any(c.startswith(path.rstrip("/") + "/") for c in changed):
            problems.append(
                f"the message claims something about `{path}`, which is not in "
                f"this commit. Either the edit did not land, or the message is "
                f"describing work from a different commit."
            )

    for path in sorted(paths_in(body, PATH)):
        full = REPO_ROOT / path
        prefix = path.rstrip("/") + "/"
        known = (
            path in tracked
            or path in changed
            # A directory is tracked only through the files under it.
            or any(t.startswith(prefix) for t in tracked)
            or any(c.startswith(prefix) for c in changed)
        )
        if full.exists() and not known:
            problems.append(
                f"`{path}` exists on disk but git has neither tracked nor staged "
                f"it. That is the `state/` bug: the file is there, nothing "
                f"errored, and the commit does not contain it. Check .gitignore."
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message_file", nargs="?", help="commit-msg hook argument")
    parser.add_argument("--rev", help="check an existing commit instead")
    args = parser.parse_args()

    if args.rev:
        message = git("log", "-1", "--format=%B", args.rev)
        changed = set(git("diff-tree", "--no-commit-id", "--name-only", "-r", args.rev).split())
        diff = git("show", "--format=", args.rev)
    elif args.message_file:
        message = Path(args.message_file).read_text()
        changed = set(git("diff", "--cached", "--name-only").split())
        diff = git("diff", "--cached")
    else:
        parser.error("give a message file (hook) or --rev")

    tracked = set(git("ls-files").split())
    problems = check(message, changed, diff, tracked)
    if problems:
        print("commit message describes changes this commit does not contain:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}\n", file=sys.stderr)
        print(
            "Fix the commit rather than the message unless the message is what is "
            "wrong. To override for a message this check has misread, commit with "
            "--no-verify and say in the message why.",
            file=sys.stderr,
        )
        return 1
    print("commit claims check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
