# Continuous integration

CI is two things: the generic checks, which are the maintainer's reusable
workflows in
[ChiefGyk3D/git-your-ship-together](https://github.com/ChiefGyk3D/git-your-ship-together)
(GYST), and the checks only this engine has, which stay in
`.github/workflows/ci.yml`. The GYST calls are pinned by commit
(`# v1.6.3` in the file); Dependabot re-pins them weekly, with a seven-day
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
read them. `pages.yml` and `wiki.yml` publish and stay local.

The pytest command is `scripts/ci-test.sh`: it checks out
`hammunition-gps-tether` at the tag the catalog pins (the contract test reads
its source, issue #215) and runs `pytest`. `make check` is the local gate and
runs the same lint, types, tests and link check without the containers.

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
