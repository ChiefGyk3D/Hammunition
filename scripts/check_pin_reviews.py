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

``--verify-refs`` adds the other half: that each ref **still resolves upstream**.
A commit SHA is 40 hex characters and the schema checks that it looks like one;
it cannot check that it is a revision anybody has. A wrong SHA -- mistyped,
copied from the wrong repository, or shortened and padded back out to 40 -- is
valid by every offline test and fails only when a user tries to install. The
verification performs the *same* fetch the git backend performs, so what is
tested is the operation that will actually run, not a proxy for it. Off by
default because it needs the network and the test suite deliberately has none.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import GitInstall  # noqa: E402


def verify_ref(repo: str, ref: str) -> str | None:
    """Fetch *ref* from *repo* the way the git backend will. None if it worked.

    ``git ls-remote`` is not enough: it lists ref tips, so a tag is visible but a
    commit part-way down a branch is not, and a SHA pin is exactly the case that
    matters. A shallow fetch by ref answers for both and is the operation the
    install performs.
    """
    with tempfile.TemporaryDirectory() as work:
        for argv in (
            ("git", "init", "--quiet", work),
            ("git", "-C", work, "remote", "add", "origin", repo),
            ("git", "-C", work, "fetch", "--depth", "1", "origin", ref),
        ):
            done = subprocess.run(argv, capture_output=True, text=True, check=False)
            if done.returncode != 0:
                return done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "failed"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-refs",
        action="store_true",
        help="also fetch each ref from its upstream to prove it resolves (needs network)",
    )
    args = parser.parse_args()

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
        basis = (
            f"matches {'+'.join(review.distributions)}"
            if review.basis == "distribution_pin"
            else "OWN CHOICE - nothing packages it"
        )
        print(
            f"{state:8} {name:20} {install.ref[:12]}  "
            f"reviewed {review.last_reviewed} by {review.reviewed_by}  "
            f"due {review.due} ({remaining:+d} days)  [{basis}]"
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

    if args.verify_refs:
        # Every git install, not only the pinned ones: a tag can be deleted or
        # re-cut upstream, and that is as install-breaking as a wrong SHA.
        every = [
            (name, block.install)
            for name, manifest in sorted(catalog.items())
            for block in manifest.install
            if isinstance(block.install, GitInstall)
        ]
        print(f"\nverifying {len(every)} git ref(s) against upstream")
        unresolved = []
        for name, install in every:
            problem = verify_ref(install.repo, install.ref)
            if problem is None:
                print(f"  ok       {name:20} {install.ref[:12]}")
            else:
                print(f"  MISSING  {name:20} {install.ref[:12]}  {problem}")
                unresolved.append(name)
        if unresolved:
            print(
                f"\n{len(unresolved)} ref(s) do not resolve upstream: "
                f"{', '.join(unresolved)}.\nA ref that cannot be fetched is an "
                f"install that fails for every user; the schema cannot catch it "
                f"because a wrong SHA is still 40 hex characters."
            )
            return 1

    own = [n for n, i in pins if i.pin_review and i.pin_review.basis == "own_choice"]
    if own:
        print(
            f"\nnote: {len(own)} pin(s) chosen by us rather than by a distribution "
            f"({', '.join(own)}). Re-check whether anything packages them now -- "
            f"a distribution pin is the cheaper and better-vetted basis (D-024)."
        )
    print(f"\n{len(pins)} pin(s), none overdue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
