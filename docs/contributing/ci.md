# Continuous integration

CI is two things: the generic checks, which are the maintainer's reusable
workflows in
[ChiefGyk3D/git-your-ship-together](https://github.com/ChiefGyk3D/git-your-ship-together)
(GYST), and the checks only this engine has, which stay in
`.github/workflows/ci.yml`. The GYST calls are pinned by commit
(`# v1.7.1` in the file); Dependabot re-pins them weekly, with a seven-day
cooldown, through `.github/dependabot.yml`.

## What runs where

| Check | Where | What it does |
|---|---|---|
| `ci / CI green` | GYST `python-ci.yml`, job `ci` | `ruff check` and `ruff format --check`, `mypy --strict` (Python 3.11, the floor), the pytest suite on 3.11 to 3.14, actionlint and zizmor over `.github/workflows`. The one gate that stands for all of them |
| `security / CodeQL`, `security / Secret scan (gitleaks)`, `security / Dependency audit`, `security / OpenSSF Scorecard` | GYST `security.yml`, job `security` | CodeQL for Python and the workflows, gitleaks over the history, pip-audit over the frozen dev extras, Scorecard on `main`; weekly as well as per push |
| `commit claims` | `ci.yml`, pull requests | The changelog fragment rule and `scripts/check_commit_claims.py` over every commit (D-031) |
| one job per target: `parrot`, `debian-13`, `ubuntu-26.04`, `ubuntu-24.04`, `kali-rolling`, `linuxmint-22.3`, `debian-13-arm64` | `ci.yml` | Rootless Podman builds the target image, validates the capability matrix, runs pytest and `mypy --strict` on that target's own Python. `containers/targets.yaml` declares them and `tests/test_targets_matrix.py` holds the two in step |
| `docs links` | `ci.yml` | `scripts/check_doc_links.py` |
| `repo hygiene` | `ci.yml` | `scripts/audit_gitignore.py` and the hygiene tests |
| `changed git pins resolve upstream` | `ci.yml`, pull requests | `scripts/check_pin_reviews.py --verify-refs --only` the manifests the diff changed (D-024) |
| `commit pin reviews`, `udev rule citations` | `ci.yml`, weekly and on dispatch | Calendar and archive-wide checks that cannot run per push |

Why the engine's own jobs stayed local: GYST's `python-ci.yml` runs one test
command per interpreter on its own runner. It has no notion of a distribution
container matrix, a pull-request-only commit check, a job that needs the
network to resolve upstream refs, or a weekly sweep. Those are this repository's
checks, and they stay in its workflow where the people who change them can
read them.

The two publishing workflows are GYST callers too: `pages.yml` calls
`docs-pages.yml` (`pip install -e ".[docs]"`, then `mkdocs build --strict`,
built on every pull request and deployed only from `main`) and `wiki.yml` calls
`wiki-publish.yml` (`scripts/gen_wiki.py --out wiki-out`, published only from
`main`, the wiki's write token held by a job that runs none of our commands).

The pytest command is `scripts/ci-test.sh`: it checks out
`hammunition-gps-tether` at the tag the catalog pins (the contract test reads
its source, issue #215) and runs `pytest`. `make check` is the local gate and
runs the same lint, types, tests and link check without the containers.

## The suite cannot touch your files

`tests/conftest.py` runs the whole suite inside a temporary `HOME` and
temporary `XDG_*` bases, removes `USER`, `SUDO_USER` and `LOGNAME`, and hides
the passwd database from `hammunition.paths`. It also records the real
`~/.config/hammunition/station.yml` before the run and fails the run, naming
the file, if it differs afterwards. `tests/test_isolation.py` holds all of this.

Why the owner variables matter: under `unshare -r` the process has euid 0, and
`paths.owner_aware_dir` and `user_config_base` then resolve the *owner's*
passwd home, not `$HOME`, when an owner is set. With `USER` still in the
environment that is your real home, and tests that run `station set` write
there. If you run the suite by hand under `unshare -r`, use the safe form:

```
env -u USER -u SUDO_USER -u LOGNAME HOME=$(mktemp -d) unshare -r .venv/bin/python -m pytest tests -q
```

## Required checks on `main`

Branch protection requires a pull request and these status checks (the names
as GitHub reports them):

- `ci / CI green`
- `security / CodeQL`, `security / Secret scan (gitleaks)` and
  `security / Dependency audit`
- `commit claims`
- `parrot`, `debian-13`, `ubuntu-26.04`, `ubuntu-24.04`, `kali-rolling`,
  `linuxmint-22.3`, `debian-13-arm64`
- `docs links`
- `repo hygiene`
- `changed git pins resolve upstream`

`ci / CI green` needs every GYST job and fails if any failed, so a job GYST
adds later can never merge unchecked. The local jobs are not behind it, which
is why each is listed. A pull-request-only job reports as skipped on a push,
which counts as passing. The weekly jobs are not required; they open no pull
request and are read when they go red.

## Pinned dependencies (OpenSSF Scorecard)

Everything CI installs or builds from is pinned by hash, and each pin has a
documented refresh. Never pin from memory; resolve.

**Base images.** Every `image:` in `containers/targets.yaml`, in the matrix in
`ci.yml` and the `ARG BASE` default in `containers/Dockerfile.target` is
`repo:tag@sha256:<multi-arch index digest>`. The tag stays for the reader;
podman follows the digest. The rolling targets (`parrot`, `kali-rolling`,
`linuxmint-22.3`) therefore move only when the pin does. Re-resolve all of them
from the registry and rewrite the three places:

```sh
containers/refresh-digests.sh          # rewrite in place
containers/refresh-digests.sh --check  # report stale pins, change nothing
```

**Python packages.** `requirements/runtime.txt`, `dev.txt` and `docs.txt` are
universal, hash-pinned locks (one file covers Python 3.11 to 3.14 and every
platform) generated by `uv pip compile` from `pyproject.toml`. CI, the
Dockerfile, `bootstrap.sh` and the Pages, wiki and release workflows install
with `pip install --require-hashes -r requirements/<set>.txt`, then
`pip install --no-deps -e .` for the engine itself. After changing a dependency
in `pyproject.toml`, or to take newer releases:

```sh
scripts/refresh-locks.sh        # needs uv and the network
python scripts/check_locks.py --check   # offline; tests/test_locks.py runs it
```

`check_locks.py --recompile` regenerates each lock with `uv` and fails on any
difference. The `Makefile`'s developer venv still installs from `pyproject.toml`
directly, on purpose: it is where you try newer versions.
