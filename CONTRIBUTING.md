<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contributing to Hammunition

The engine does not exist yet, so this is not the moment for large code
contributions. It **is** the moment for the things that are hard to do later and
easy to do now.

## The most useful thing you can send

**`lsusb` output for a device we don't own.** No code, about thirty seconds, and
it unblocks work nobody without the hardware can do.

A device whose USB identifier is guessed produces a udev rule that *silently
never matches*. The operator gets hardware that enumerates, works as root, and
has no `/dev` symlink — indistinguishable from a bad cable, with no error message
anywhere in the chain. So this catalog refuses to guess, and every unknown
identifier is recorded as a gap instead.

See [`docs/contributing/hardware.md`](docs/contributing/hardware.md) for how, and
[`docs/reference/hardware-gaps.md`](docs/reference/hardware-gaps.md) for what is
outstanding. Both are generated from the catalog, so neither can drift from it.

## Also valuable

- **Corrections to the inventories.** If `docs/reference/` says something wrong
  about a package you maintain or use, that is the most valuable issue you can
  file. Several of our own claims have turned out to be wrong; each correction is
  recorded in the document that made the claim rather than quietly edited out, so
  you can see what happens to one before filing it.
- **Answers to [`docs/QUESTIONS.md`](docs/QUESTIONS.md).**
- **A catalog entry for hardware nobody here owns.** `identification_gap` exists
  precisely so that *"this device exists and here is what Linux needs for it"* is
  a shippable state rather than a blocker.

## Licensing and copyright

**Two licences**, split on the architectural boundary — see
[D-023](docs/DECISIONS.md):

| Tree | Licence |
|---|---|
| `src/`, `scripts/`, `tests/`, `docs/` | GPL-3.0-or-later |
| `catalog/` | CC0-1.0 |

Files carry SPDX headers per the [REUSE](https://reuse.software/) specification.
A new file gets the header for the tree it lives in; `tests/test_licensing.py`
fails the build if it does not, because a manifest copy-pasted from a Python
module silently inherits the wrong identifier.

### You keep your copyright

**There is no CLA and no copyright assignment.** We are not asking for either.

- **You retain copyright on your own contributions**, licensed under
  GPL-3.0-or-later (or CC0-1.0 for `catalog/`) by the act of contributing.
- Contributions made by Renegade Penguin LLC are the LLC's.
- Everything else stays with whoever wrote it.

This is the ordinary arrangement for a GPL project, and it is written down
because people reasonably assume otherwise when a company name appears in the
copyright headers. The LLC is named there because a legal person can enforce the
licence and a handle cannot — **not** because it is collecting rights from
contributors.

A CLA would be a barrier to exactly the drive-by manifest and `lsusb`
contributions this project most wants, and the multi-maintainer governance
argument does not need one.

### Attribution

Handles are fine everywhere attribution appears — commit authorship, `Co-Authored-By`,
credits, the `evidence` field of a USB identifier you captured. The copyright
holder line is a separate thing from attribution, and neither replaces the other.

## Before you open a pull request

```
ruff check . && ruff format --check .
python3 scripts/audit_gitignore.py
python3 scripts/check_doc_links.py
git config core.hooksPath .githooks     # once per clone; see below
```

That last line enables a `commit-msg` hook that refuses a commit whose message
describes a change the commit does not contain — a decision it says it amended
but did not touch, a file it says it added that git does not have (**D-031**).
It is opt-in because git will not run hooks from a clone by design, and a
project that works around that is asking you to execute its code on clone. CI
runs the same script over every commit in your pull request regardless, so
enabling it locally saves you a round trip rather than gating anything.

Tests and `mypy --strict` run against a target container rather than your
machine — `scripts/run-targets.sh`. CI is the authority: it pins Python 3.11+ and
your development machine may be older.

Small, logically scoped commits. Documentation is not optional: a manifest
missing a required documentation field fails validation, because the docs
generator reads those fields and an undocumented package cannot ship.
