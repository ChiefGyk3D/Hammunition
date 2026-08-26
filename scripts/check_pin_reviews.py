#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Report commit pins that are due for review.  D-024.

Two failure modes, opposite directions, same cause -- nobody looked:

* An abandoned tag. SDR++'s newest release tag is from 2021 while master moved
  in 2026. Pinning it would ship a five-year-old program.
* An unreviewed commit. Perfectly pinned, perfectly arbitrary, and four years
  from now indistinguishable from the first case.

A tag carries an upstream signal that someone decided a revision was worth
naming. A SHA carries none, so pinning one moves a judgement upstream stopped
making onto us. `PinReview` records that judgement; this reports when it is
stale.

Deliberately NOT run on every push. Whether a pin is well-formed is a property
of the code and is asserted in tests; whether it is *stale* is a property of the
calendar, and failing an unrelated pull request because a date rolled over would
teach people to ignore the job. CI runs this on a schedule instead.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import GitInstall  # noqa: E402


def main() -> int:
    today = date.today()
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")

    pins = [
        (name, block.install)
        for name, manifest in sorted(catalog.items())
        for block in manifest.install
        if isinstance(block.install, GitInstall) and block.install.pin_review
    ]

    if not pins:
        print("no commit pins in the catalog")
        return 0

    overdue = []
    for name, install in pins:
        review = install.pin_review
        assert review is not None
        state = "OVERDUE" if review.is_overdue(today) else "ok"
        remaining = (review.due - today).days
        print(
            f"{state:8} {name:20} {install.ref[:12]}  "
            f"reviewed {review.last_reviewed} by {review.reviewed_by}  "
            f"due {review.due} ({remaining:+d} days)"
        )
        if review.is_overdue(today):
            overdue.append((name, install))

    if overdue:
        print(f"\n{len(overdue)} pin(s) overdue. For each one:")
        print("  1. Read upstream's log since the pinned commit.")
        print("  2. Decide whether to move the pin, and TEST it if you do.")
        print("  3. Update last_reviewed and rationale either way -- deciding not")
        print("     to move a pin is a review, and recording it is the point.")
        print("\nDo not bump last_reviewed without doing 1 and 2. That converts")
        print("this check into a chore that certifies nothing.")
        return 1

    print(f"\n{len(pins)} pin(s), none overdue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
