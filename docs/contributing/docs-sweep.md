<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# The docs sweep

Documentation here is written per branch, by whoever builds the feature, and a
large batch of merges leaves pages that were each right on their own branch
and wrong together: a guide still describing the old default, a "not yet
released" for something that was released that afternoon, a README that counts
what the code no longer has. A sweep is the audit that finds those, run once
before every release, and the one pull request that fixes them. The first one
was run on 2026-10-02 after the batch behind v0.19.0; this page is the
checklist it used, so the next one does not start from nothing.

**A sweep is an audit and one fixing PR, not a rewrite.** It fills gaps with
prose grounded in the code and the pull request bodies, fixes contradictions
in favour of the code and `docs/DECISIONS.md`, and leaves everything else
alone. It never invents a measurement.

## The wiki mirror

The GitHub wiki is generated from `docs/`, never written. On every push to
`main`, `.github/workflows/wiki.yml` (a GYST `wiki-publish.yml` caller) runs `scripts/gen_wiki.py` and replaces
every wiki page with its output, so an edit made in the wiki is lost at the
next push. Corrections go to `docs/` by pull request, like any other. The
canonical site stays <https://chiefgyk3d.github.io/Hammunition/>.

To see what the wiki will contain:

```sh
.venv/bin/python scripts/gen_wiki.py --out /tmp/wiki-out
.venv/bin/python scripts/gen_wiki.py --check
```

`--check` writes nothing; it fails on a name collision or a link that points at
nothing. A new page needs no wiki step: it is in the nav, so it is in the wiki.
The workflow needs the wiki's first page created once in the GitHub UI, because
the wiki's git remote does not exist before that; until then it fails naming
that step.

## Set up

```sh
git fetch -q origin
git worktree add ../Hammunition-docs-sweep -b docs-sweep origin/main
cd ../Hammunition-docs-sweep && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

Run the engine only with `--help` and `--dry-run`, with `HOME` pointed at a
scratch directory so no real log or station file is touched, and never with
`sudo`. Nothing is installed or applied on the machine doing the sweep.

## Gather what landed

```sh
git log --merges <last-tag>..origin/main --oneline
git log origin/main --oneline -15
gh pr view N --json title,state,body -q .body     # each merged PR since the tag
```

Read the decisions the batch touched in `docs/DECISIONS.md`, and every
amendment dated since the last sweep (`grep -n "Amendment" docs/DECISIONS.md`).
Note which pull requests are **still open**: their features are not on `main`
and the docs must not describe them as done. Pull request bodies are the
record of what was measured; the section called "What the bench owes" or "Not
measured" in each is a list of claims the docs must not make.

## The six checks

For each merged piece, with the file and line of what you find:

1. **Is there a guide that takes an operator through it end to end?** One
   page or section, reachable from the nav, that says what to install, what to
   run, what the prompts are and what the result looks like. A feature with
   only a reference entry in `docs/reference/cli.md` fails this check.
2. **Do the pages agree with each other and with the code?** Getting started,
   the profile pages, the hardware pages, troubleshooting and the CLI
   reference must give the same answer to "what is the default" and "which
   command". Check every flag cited against the code (below), and every
   default against the manifest or the schema.
3. **Does each page end with what was measured and what was not**, per the
   guides' convention, and is anything claimed as working that the pull
   request body lists as owed to the bench? Check the other direction too: a
   page still saying "not yet run" for something a bench session now records
   (`docs/reference/bench-verification-5430.md`) is as wrong as the reverse.
4. **Is the nav complete and ordered for a newcomer?** Every page is in
   `mkdocs.yml` or is a package page (`tests/test_site.py` enforces that), but
   in-nav is not the same as findable: a guide missing from `docs/guides/index.md`,
   a page filed under Reference that a newcomer needs on day one, a hardware
   group that mixes unrelated things.
5. **Do the counts and the status block match?** README's status table and
   counts, CLAUDE.md's repo layout and decisions table against
   `docs/DECISIONS.md` (the decision record wins), `ls catalog/packages | wc -l`
   and the like, and the number of bench sessions.
6. **Do the sibling repositories' READMEs still say true things?**
   hammunition-tray, hammunition-gps-tether and hammunition-bunker are read,
   not edited, in this pull request; what is stale goes into the PR body as a
   follow-up for each.

### Checking flags against the code

Every flag a page cites must exist. This reads every heading of
`docs/reference/cli.md` that names flags and confirms the program's own
`--help` lists them, and the other way round:

```sh
.venv/bin/python - <<'EOF'
import re, subprocess
H = ".venv/bin/hammunition"
txt = open("docs/reference/cli.md").read()
heads = list(re.finditer(r"^### `(hammunition [^`]*)`", txt, re.M))
for i, m in enumerate(heads):
    end = heads[i + 1].start() if i + 1 < len(heads) else len(txt)
    sec = txt[m.start():end]
    words = []
    for w in m.group(1).split()[1:]:
        if not re.match(r"^[a-z][a-z0-9-]*$", w):
            break
        words.append(w)
    for k in range(len(words), 0, -1):
        r = subprocess.run([H, *words[:k], "--help"], capture_output=True, text=True)
        if r.returncode == 0:
            break
    documented = set(re.findall(r"--[a-z][a-z0-9-]+", m.group(1)))
    real = set(re.findall(r"--[a-z][a-z0-9-]+", r.stdout)) - {"--help", "--json"}
    print(" ".join(words[:k]), "| cited but not real:", sorted(documented - real - {"--help", "--json"}),
          "| real but absent from its section:", sorted(f for f in real if f not in sec))
EOF
```

A flag cited in a guide rather than the reference is checked by hand with
`hammunition <verb> --help`. The check above skips a heading that covers two
verbs (`station show` and `station set`), so run `station set --help` yourself.

## What to fix, and what to leave

Fix, in the one branch: a gap with accurate prose and a cross-link; a
contradiction in favour of the code and `DECISIONS.md`; a nav entry; a count.
Mark anything unmeasured as unmeasured, in the words the pull request used.

Leave alone: generated pages (`docs/packages/`, `docs/profiles/`,
`docs/reference/` pages with a "Generated by" line), which are regenerated
from their input, never edited. When a generated page is wrong, the input is
a manifest, a profile's `documentation:` block or a generator script; fix that
and regenerate with the generator named in the page's first line, then run it
with `--check`. A generator's `--check` writing nothing is itself tested
(`tests/test_docs_generated.py`).

Never write the maintainer's callsign, grid square, regions, host name or a
serial number into a page, a commit or a pull request: placeholders only
(`N0CALL`, `N0TST`, `FN31pr`).

## Gates

```sh
make check > /tmp/sweep-make.log 2>&1; echo "make check rc=$?"
nice -n 19 unshare -r .venv/bin/python -m pytest tests -q -p no:cacheprovider \
    > /tmp/sweep-pytest.log 2>&1; echo "pytest rc=$?"
```

`make check` builds the site with `--strict` and checks links, including
backticked repository paths. Capture to a log and test the exit status; never
pipe a gate into `grep`. Each commit goes through
`scripts/check_commit_claims.py --rev HEAD`.

Then one reviewer (a Sonnet agent), asked to spot-check ten of the new claims
by running the commands they cite rather than reading them. Fix what it finds
that is Critical or Important.

## The pull request

Title: "Docs sweep after the <date> batch: gaps filled, contradictions
resolved, the sweep checklist added". The body is the audit table (page,
finding, fix), then the sibling-repository follow-ups, then what the sweep
could not settle (a question for the maintainer). The maintainer merges it. The sweep is a step of
[cutting a release](releasing.md#before-the-tag).
