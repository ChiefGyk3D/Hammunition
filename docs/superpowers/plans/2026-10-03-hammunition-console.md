# hammunition-console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `hammunition-console`, a full-screen terminal front end (urwid) for the Hammunition engine with Home, Install, Station, Logs, Update and Help screens, in its own repository, plus the catalog unit and docs page in the engine repository that install it.

**Architecture:** A pure Python 3.11 program with no engine import. Three channels, each with one job: reads run `hammunition <verb> --json` in worker threads and parse the one document (D-059); every write runs the real `hammunition` command inside an embedded `urwid.Terminal` pane, through a tiny stdlib runner that reports the child's exit status, so the operator types any consent `yes` into the real prompt; the only thing the console stores is its own `config.toml`. Pure view functions (document in, lines out) carry the logic so screens test headlessly against recorded fixtures; a fake `hammunition` script serves those fixtures and simulates a consent prompt on a real tty.

**Tech Stack:** Python 3.11+, `python3-urwid` (floor 2.6, nothing above 2.6's API), standard library only; pytest, ruff, `mypy --strict` as dev tools; GitHub Actions.

**Spec:** `/home/chiefgyk3d/src/Hammunition/docs/superpowers/specs/2026-10-03-console-design.md` (on branch `console-spec`; read with `git -C /home/chiefgyk3d/src/Hammunition show origin/console-spec:docs/superpowers/specs/2026-10-03-console-design.md`). Read it and `docs/reference/json-interface.md` and `docs/reference/cli.md` in the Hammunition repo before Task 3. The maintainer's rulings are spec section 12: name `hammunition-console`, toolkit urwid, first release = Home, Install, Station, Logs, Update, Help (Hardware and Maps deferred), a `hammunition console` engine subcommand only after the first release (not in this plan).

**Two repositories.** Tasks 1-19 happen in a new repository, `ChiefGyk3D/hammunition-console`, cloned to `/home/chiefgyk3d/src/hammunition-console` in Task 1 (the plan does not create it; the executor does). Task 20 happens in `/home/chiefgyk3d/src/Hammunition`. Commands name the directory they run in.

**Not run when written.** Neither urwid nor the engine's branch `profile-state` was available while this plan was written, so no code below has been executed. Every test is real code and every command has an Expected line, but the first run of each task may need small corrections (an urwid signature, an import). Fix the code, never the test's intent, and never weaken an assertion to get green.

## Global Constraints

Every task's requirements include this section.

- **Python 3.11+.** Runtime imports: the standard library and `urwid` only. `pyte` and `textual` are out. No `shell=True` anywhere. No network access by the console, ever.
- **urwid floor 2.6**, the oldest in any target archive (2.6.10 Ubuntu 24.04, 2.6.16 Debian 13 and Parrot, 3.0.4 Ubuntu 26.04 and Kali, measured in the spec). Use nothing above 2.6's API. Do not construct `urwid.raw_display.Screen` or `urwid.display.raw.Screen` yourself; let `urwid.MainLoop` build its screen, and render widgets to canvases in tests. CI runs 2.6.10, 2.6.16 and 3.0.4 and the archive's own `python3-urwid` on Debian 13 and Ubuntu 24.04.
- **Reads** only through `hammunition <verb> --json`, only for verbs in `hammunition_console/verbs.py` `JSON_VERBS` (the engine's "Commands" list in `docs/reference/json-interface.md`), only in worker threads, never in the UI thread. `install` and `uninstall` are read only with `--dry-run`. A command with no JSON form is never run under `--json`.
- **Writes** only by running the real `hammunition` command (or `sudo apt-get install --only-upgrade ...` as the engine's `update` report prints it, see Task 14) inside an `urwid.Terminal` pane, so a consent `yes` is typed by a person. The console never reads the pane's input for `yes`, never echoes it, never injects keystrokes.
- **The console never passes the engine's assume-yes flag (the long form or the short one) and never sets any scripted-consent environment variable.** The engine's scripted-consent family is `HAMMUNITION_ACCEPT_<NAME>` (pattern `^HAMMUNITION_ACCEPT_[A-Z0-9_]+$`, engine `src/hammunition/manifest/schema.py:89`; read by `src/hammunition/consent/gate.py` `resolve_consent`) and `HAMMUNITION_ACCEPT_APT_REPO_<NAME>` (`repo_env_var`, same file). The console also removes every variable with that prefix, and every variable ending `_CONSENT`, from the environment of every child it starts, so one exported in the parent shell never reaches a gate through the console. Only `hammunition_console/guard.py` may contain these tokens, on lines tagged `# consent-guard`; a test greps the package for them.
- **Stores nothing but its own config** under `~/.config/hammunition-console/config.toml` (`$XDG_CONFIG_HOME` honoured): last screen, theme, walkthrough dismissed. One more file lives in that directory: `crash.log`, holding no message text. The console never holds a station value anywhere but in a widget, never writes one to config, log, crash report or environment, and the header says only "station: set" or "station: not set".
- **Engine version floor** is read from the `engine` field of the first `--json` document, never from `hammunition --version`. It is one constant, `ENGINE_FLOOR` in `hammunition_console/engine.py`, with a test. Its value is `(0, 19, 0)`, the version the spike measured and the first with the whole JSON interface; raise it in one line when the engine release that ships E1 and E2 is tagged.
- **Engine prerequisites E1 and E2 are treated as present.** E1 (branch `profile-state`, in progress): each profile row of `list --json` carries `members` (int, units the profile names), `installed` (int, of those the transaction log records as installed) and `installed_size_bytes` (int or null, a floor: apt members only). E2 (issue #239): `update --json` with no names reports retired units as rows and exits 0. Every screen that reads them has a fixture with and a fixture without, and degrades to "unknown" rather than crashing.
- **No identifiers.** Fixtures, docs, tests and logs use `N0CALL`, `N0TST`, `FN31pr`, `/home/user`, the host `host`. No real callsign, grid square, hostname, serial, username or home path in any file, commit, issue or output. Fixtures are reviewed for identifiers before commit (Task 3 explains how, and a test scans them).
- **Install shape follows hammunition-tray:** own repository, tag archive, `install.sh --prefix/--interpreter`, a `/bin/sh` wrapper, `depends: [python3, python3-urwid]`. No venv, no pip, no pipx at install time (D-014). Nothing runs as root; the console refuses to start as root.
- **Security:** never pipe remote content into a shell; GitHub Actions pinned by resolved commit (`git ls-remote --tags`, never from memory); tags reach shell only through `env:`.
- **Documentation is a deliverable:** README, `docs/contract.md`, man page, the engine's `docs/getting-started/console.md`. A feature is not done until documented.
- **Tests:** checks live in the test suite and CI runs the suite. Each guard is falsified before it is trusted: break the thing it watches on purpose and confirm red with a message naming the fix (the plan says where). Sockets are blocked in tests except loopback and unix sockets.
- **Changelog:** never edit `CHANGELOG.md` in a pull request; add `changelog.d/<pr-or-branch>.<kind>.md` (kinds `added`, `changed`, `fixed`, `removed`, `docs`, `decision`).
- **Source headers.** Every `.py` and `.sh` file and `bin/hammunition-console` starts with
  `# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC` and `# SPDX-License-Identifier: GPL-3.0-or-later` (after a shebang if there is one). The code blocks below omit these two lines to stay readable; run `python3 scripts/spdx.py --fix` (created in Task 1) before every commit, and the test in Task 1 fails if one is missing. Licence: GPL-3.0-or-later.
- **Git.** Feature branch `first-release`, merged to `main` by pull request by the maintainer, never by the author. Small commits. Commit messages end with the attribution line the harness supplies (`Co-Authored-By: ...`). The personal `gh` account must be active (`ghwho`; switch with `ghsw`); personal repos commit as `19499446+ChiefGyk3D@users.noreply.github.com`.
- **Out of scope:** Hardware and Maps screens, a step-N-of-M progress bar (E7), transaction history (E6), log search, running any `doctor` fix (E8), launching GUI programs, installing the engine or the helper, any scripted mode, translations, the `hammunition console` subcommand, anything on Raspberry Pi OS, Pop!_OS or Mint that has not been run.

## Review Focus

The five input classes the spec implies but no task's own happy-path tests exercise, most likely first. Each has a test in the task named in brackets.

1. **A terminal escape sequence or other control character inside engine text** (an `error` message, a doctor `detail`, a log file line, a unit summary) must never reach the terminal as a control sequence; the operator expects to read it as plain text, never to have their terminal reprogrammed. [Task 5 `clean()`; Task 8 Home; Task 12 log viewer]
2. **A name typed into the Install box that begins with `-`** (including the assume-yes flag in either spelling) must not become an argv element the engine could read as a flag; the operator expects "a name does not start with '-', nothing was run". [Task 10]
3. **A corrupt, truncated, hand-edited or wrong-typed `config.toml`** must not crash the console or its next start; the operator expects defaults and a working console. [Task 1]
4. **A log path that escapes the log directory (a symlink, `..`) and a followed log that is truncated or deleted by rotation while open**; the operator expects a refusal naming the rule, and a calm "log was rotated away" line, never a traceback. [Task 12]
5. **Documents with `null` where the fixtures have a string or number** (`summary`, `remedy`, `disk_footprint_hint`, `installed_size_bytes`, `detail`), and an `outcome: "refused"` plan with no `remedy`; the operator expects blank or "unknown", never a crash or the word "None". [Task 9, Task 10]

---

## File Structure

New repository `hammunition-console` (`/home/chiefgyk3d/src/hammunition-console`):

```
LICENSE                          GPL-3.0-or-later (copied from the tray)
README.md  CHANGELOG.md  changelog.d/README.md
pyproject.toml                   tool config only (pytest, ruff, mypy); no build system
bin/hammunition-console          /bin/sh wrapper: python3 -P -m hammunition_console
install.sh  uninstall.sh         --prefix, --interpreter (tray shape)
man/hammunition-console.1
docs/contract.md                 which documents are read, per screen, and how each degrades
scripts/spdx.py                  add/check the two header lines
scripts/capture_fixtures.py      record fixtures from a real engine, scrub, scan
scripts/changelog.py             copied from the engine (fragments -> CHANGELOG.md)
scripts/check_version.py         a release tag must agree with the tree and the changelog
.github/workflows/ci.yml  release.yml
hammunition_console/
  __init__.py                    __version__
  __main__.py                    argument handling, tty/TERM/root refusal, start
  helptext.py                    USAGE, KEYS, per-screen help text (no consent tokens)
  config.py                      config.toml load/save, atomic, 0600
  guard.py                       consent guard: forbidden argv, env scrub, allow-list of runnable commands
  verbs.py                       JSON_VERBS: the only verbs ever read under --json
  engine.py                      run --json, parse, schema and version floor, typed errors
  fmt.py                         clean(), human_size(), mask()
  worker.py                      Background: SyncBackground (tests), ThreadBackground (urwid pipe)
  context.py                     Shared state, Context protocol every screen talks to
  app.py                         Shell (stack, header, keys), SizeGuard, palettes, crash log, run()
  runner.py                      stdlib script run inside the pane: runs the command, records its exit status
  pane.py                        PaneScreen: urwid.Terminal around the runner
  walkthrough.py                 first-run checklist: pure steps from documents
  screens/__init__.py
  screens/base.py                Row, Screen, PromptScreen, ConfirmScreen, MessageScreen, describe_error
  screens/home.py  install.py  plan.py  station.py  logs.py  update.py  help.py
tests/
  __init__.py  conftest.py  helpers.py  pty_driver.py
  fake_hammunition.py            answers --json from fixtures; simulates a consent prompt on its tty
  fixture_scan.py  schema_check.py
  fixtures/*.json *.exit manifest.json README.md schemas/*.json
  test_*.py
```

Engine repository (Task 20): `catalog/packages/hammunition-console.yaml`, `docs/getting-started/console.md`, `mkdocs.yml`, `docs/projects.md` and `docs/packages/hammunition-console.md` (generated), `changelog.d/console-unit.added.md`, `tests/test_hammunition_console_unit.py`.

---

### Task 1: Repository, scaffold, entry point, config

**Files:**
- Create: `/home/chiefgyk3d/src/hammunition-console/` (the repository), `LICENSE`, `.gitignore`, `pyproject.toml`, `requirements-dev.txt`
- Create: `hammunition_console/__init__.py`, `hammunition_console/__main__.py`, `hammunition_console/helptext.py`, `hammunition_console/config.py`
- Create: `scripts/spdx.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_spdx.py`, `tests/test_cli.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `hammunition_console.__version__: str`; `helptext.USAGE: str`, `helptext.KEYS: tuple[tuple[str, str], ...]`; `__main__.main(argv=None, *, stdin=None, stdout=None, environ=None, euid=None) -> int` (exit 0 ok, 2 refused to start); `config.Config` dataclass (`last_screen: str = "home"`, `theme: str = "dark"`, `walkthrough_dismissed: bool = False`), `config.SCREENS`, `config.THEMES`, `config.config_dir(environ=None) -> Path`, `config.config_path(environ=None) -> Path`, `config.load(path=None) -> Config`, `config.save(cfg, path=None) -> bool`; `scripts.spdx.missing(root) -> list[Path]`, `scripts.spdx.add_header(text) -> str`.

- [ ] **Step 1: Create and clone the repository, on the personal account**

```bash
ghwho
```
Expected: the personal account (ChiefGyk3D) is the active one. If it is not, run `ghsw`, then `ghwho` again.

```bash
gh repo create ChiefGyk3D/hammunition-console --public --description "A terminal front end for the Hammunition engine: install, station, logs and updates in one full-screen program" --clone --license gpl-3.0 -- /home/chiefgyk3d/src/hammunition-console
cd /home/chiefgyk3d/src/hammunition-console && git config user.email 19499446+ChiefGyk3D@users.noreply.github.com && git checkout -b first-release && git log --oneline | head -3
```
Expected: the repository exists, cloned, with GitHub's initial commit, and `git branch --show-current` prints `first-release`. If `gh repo create` refuses the `-- <path>` form in the installed version, run `gh repo create ChiefGyk3D/hammunition-console --public --description "..." --license gpl-3.0 --clone` from `/home/chiefgyk3d/src`.

- [ ] **Step 2: Replace GitHub's licence with the tray's text and write the ignore file and tool config**

```bash
cd /home/chiefgyk3d/src/hammunition-console && cp /home/chiefgyk3d/src/hammunition-tray/LICENSE LICENSE && head -3 LICENSE
```
Expected: the first lines read `GNU GENERAL PUBLIC LICENSE` / `Version 3, 29 June 2007`.

Create `.gitignore`:

```gitignore
__pycache__/
*.pyc
/dist/
/.venv/
.venv
.mypy_cache/
.pytest_cache/
.ruff_cache/
```

Create `pyproject.toml`:

```toml
# Tool configuration only. hammunition-console is installed by copying its
# tree (install.sh, or the Hammunition catalog unit): there is no wheel, no
# pip step and no virtualenv at install time (D-014).

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra"
filterwarnings = ["error"]
markers = ["pty: drives the console inside a real pseudo-terminal"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
# No formatter and no line-length gate: hand-formatted code is the house style, and a
# reflow of files for no defect found is not a check anyone trusts. Import order is kept
# by `ruff check --fix`, which every commit step runs.
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["hammunition_console", "tests", "scripts"]
# Every widget subclasses an urwid class; if urwid is untyped in an archive
# the base is Any, which is not a defect in this code.
disallow_subclassing_any = false

[[tool.mypy.overrides]]
module = ["urwid", "urwid.*"]
ignore_missing_imports = true

# Tests poke at private widget state and urwid internals, whose types differ
# between urwid 2.6 and 3.x; an ignore that is needed on one is unused on the
# other, so unused-ignore warnings are off for tests only. The package itself
# stays fully strict.
[[tool.mypy.overrides]]
module = ["tests.*"]
warn_unused_ignores = false
```

Create `requirements-dev.txt`:

```text
pytest>=8
mypy>=1.10
ruff>=0.5
```

- [ ] **Step 3: Write the header tool and its test (failing first)**

Create `scripts/spdx.py`:

```python
#!/usr/bin/env python3
"""Add or check the two-line source header on every .py, .sh and bin/ file.

    python3 scripts/spdx.py --check   # exit 1 naming each file without it
    python3 scripts/spdx.py --fix     # prepend it (after a shebang) where missing
"""

from __future__ import annotations

import sys
from pathlib import Path

HEADER = [
    "# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC",
    "# SPDX-License-Identifier: GPL-3.0-or-later",
]
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "dist", ".mypy_cache", ".pytest_cache"}


def source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        parts = set(path.relative_to(root).parts)
        if parts & SKIP_DIRS or not path.is_file():
            continue
        in_bin = path.relative_to(root).parts[:1] == ("bin",)
        if path.suffix in {".py", ".sh"} or in_bin:
            found.append(path)
    return found


def has_header(text: str) -> bool:
    lines = text.splitlines()
    body = lines[1:] if lines and lines[0].startswith("#!") else lines
    return body[:2] == HEADER


def add_header(text: str) -> str:
    if has_header(text):
        return text
    lines = text.splitlines()
    shebang = [lines.pop(0)] if lines and lines[0].startswith("#!") else []
    out = [*shebang, *HEADER, *lines]
    return "\n".join(out) + "\n"


def missing(root: Path) -> list[Path]:
    return [p for p in source_files(root) if not has_header(p.read_text(encoding="utf-8"))]


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    if argv == ["--fix"]:
        for path in missing(root):
            path.write_text(add_header(path.read_text(encoding="utf-8")), encoding="utf-8")
            print(f"added header: {path.relative_to(root)}")
        return 0
    if argv == ["--check"]:
        bad = missing(root)
        for path in bad:
            print(f"missing header: {path.relative_to(root)} (run: python3 scripts/spdx.py --fix)")
        return 1 if bad else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Create `tests/__init__.py` (empty file) and `tests/test_spdx.py`:

```python
from pathlib import Path

from scripts import spdx

ROOT = Path(__file__).resolve().parent.parent


def test_every_source_file_has_the_header() -> None:
    assert spdx.missing(ROOT) == [], "run: python3 scripts/spdx.py --fix"


def test_add_header_is_idempotent_and_keeps_the_shebang() -> None:
    once = spdx.add_header("#!/bin/sh\necho hi\n")
    assert once.splitlines()[:3] == ["#!/bin/sh", *spdx.HEADER]
    assert spdx.add_header(once) == once


def test_add_header_without_a_shebang() -> None:
    text = spdx.add_header("x = 1\n")
    assert text.splitlines()[:2] == spdx.HEADER and text.endswith("x = 1\n")


def test_check_detects_a_file_without_it(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert [p.name for p in spdx.missing(tmp_path)] == ["a.py"]
```

- [ ] **Step 4: Run it; confirm it fails, then passes after the header pass**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_spdx.py -v`
Expected: FAIL (`test_every_source_file_has_the_header` lists `scripts/spdx.py` and `tests/test_spdx.py` as missing, or an import error before `scripts/spdx.py` exists).

Run: `python3 scripts/spdx.py --fix && python3 -m pytest tests/test_spdx.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Write the entry point's tests (failing first)**

Create `tests/conftest.py`:

```python
import socket
from collections.abc import Iterator
from typing import Any

import pytest
import urwid

urwid.set_encoding("utf-8")


@pytest.fixture(autouse=True)
def _block_remote_sockets(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test may talk to anything but a unix socket or loopback."""
    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: Any) -> Any:
        if self.family == socket.AF_UNIX:
            return real_connect(self, address)
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"test tried to connect to {address!r}; the console fetches nothing")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    yield
```

Create `tests/test_cli.py`:

```python
import io

import pytest

from hammunition_console import __version__
from hammunition_console.__main__ import main
from hammunition_console.helptext import KEYS, USAGE


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def run(args: list[str], *, tty: bool = True, term: str = "xterm", euid: int = 1000) -> tuple[int, str, str]:
    out, err = Tty() if tty else io.StringIO(), io.StringIO()
    import contextlib

    with contextlib.redirect_stderr(err):
        code = main(args, stdin=Tty() if tty else io.StringIO(), stdout=out,
                    environ={"TERM": term}, euid=euid)
    return code, out.getvalue(), err.getvalue()


def test_version() -> None:
    code, out, _ = run(["--version"], tty=False)
    assert (code, out.strip()) == (0, f"hammunition-console {__version__}")


def test_help_lists_every_key_and_the_exit_codes() -> None:
    code, out, _ = run(["--help"], tty=False)
    assert code == 0
    for keys, meaning in KEYS:
        assert keys in out and meaning in out
    assert "Exit codes" in out and USAGE.splitlines()[0] in out


def test_unknown_argument_is_refused() -> None:
    code, _, err = run(["--bogus"])
    assert code == 2 and "--bogus" in err and "--help" in err


def test_no_tty_is_refused_before_drawing() -> None:
    code, _, err = run([], tty=False)
    assert code == 2 and "terminal" in err


def test_dumb_terminal_is_refused() -> None:
    code, _, err = run([], term="dumb")
    assert code == 2 and "TERM" in err


def test_root_is_refused() -> None:
    code, _, err = run([], euid=0)
    assert code == 2 and "root" in err


@pytest.mark.parametrize("args", [["-y"], ["--yes"]])
def test_no_assume_yes_option_exists(args: list[str]) -> None:
    code, _, err = run(args)
    assert code == 2 and "unknown argument" in err
```

- [ ] **Step 6: Run it; confirm it fails**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hammunition_console'`. If urwid is not installed in the dev environment, create one first: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt "urwid==2.6.16"` (a dev virtualenv is allowed; the no-venv rule is about install time) and re-run.

- [ ] **Step 7: Implement the package skeleton**

Create `hammunition_console/__init__.py`:

```python
"""hammunition-console: a terminal front end for the Hammunition engine."""

__version__ = "0.1.0"
```

Create `hammunition_console/helptext.py`:

```python
"""Text the console shows and prints. Keep the literal consent tokens out of here:
tests/test_consent_guard.py fails if one appears anywhere in the package but guard.py."""

from __future__ import annotations

USAGE = """\
usage: hammunition-console [--help] [--version]

A full-screen terminal front end for the Hammunition engine. It reads the
engine's JSON documents and runs the engine's own commands in a terminal pane;
it never answers a consent prompt for you. Needs a terminal at least 80x24."""

# (keys, meaning). Every key listed here is handled somewhere; the README's
# keys table is generated from this tuple's content by hand and a test checks it.
KEYS: tuple[tuple[str, str], ...] = (
    ("1-5", "open the screen with that number (Home)"),
    ("Enter", "open the selected row"),
    ("b / Esc", "go back; changes nothing"),
    ("?", "help"),
    ("q", "quit"),
    ("r", "refresh this screen"),
    ("R", "run the planned command in a terminal pane (plan and confirm screens)"),
    ("Tab", "switch between profiles and single units (Install)"),
    ("U", "plan an uninstall of the selected profile (Install)"),
    ("i", "the selected profile's documentation (Install)"),
    ("v", "reveal or hide station values (Station)"),
    ("c", "clear the selected value, where the engine can (Station)"),
    ("u", "also ask upstream whether the catalog's pins are current (Update)"),
    ("A", "run the apt upgrade the report offers (Update)"),
    ("B", "plan the rebuilds the report offers (Update)"),
    ("s", "skip the selected first-run step (Home)"),
    ("D", "dismiss the first-run checklist (Home)"),
)

EXIT_CODES = (
    ("0", "normal exit"),
    ("1", "the console crashed (details, without any message text, in crash.log)"),
    ("2", "the console refused to start: no terminal, TERM=dumb, running as root, bad argument"),
)


def full_help() -> str:
    lines = [USAGE, "", "Keys:"]
    lines += [f"  {keys:<10} {meaning}" for keys, meaning in KEYS]
    lines += ["", "Exit codes:"]
    lines += [f"  {code:<10} {meaning}" for code, meaning in EXIT_CODES]
    return "\n".join(lines)
```

Create `hammunition_console/__main__.py`:

```python
from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from hammunition_console import __version__
from hammunition_console.helptext import full_help


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
    euid: int | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    env = os.environ if environ is None else environ
    uid = os.geteuid() if euid is None else euid
    if args in (["--help"], ["-h"]):
        print(full_help(), file=stdout)
        return 0
    if args == ["--version"]:
        print(f"hammunition-console {__version__}", file=stdout)
        return 0
    if args:
        print(f"hammunition-console: unknown argument {args[0]!r} (see --help)", file=sys.stderr)
        return 2
    if uid == 0:
        print(
            "hammunition-console: do not run this as root. It runs as you and asks for sudo "
            "itself, inside a terminal pane, only for the commands that need it.",
            file=sys.stderr,
        )
        return 2
    if not (stdin.isatty() and stdout.isatty()):
        print("hammunition-console needs a terminal (stdin and stdout must both be one).",
              file=sys.stderr)
        return 2
    if env.get("TERM", "dumb") == "dumb":
        print("hammunition-console: TERM is 'dumb' or unset; it cannot draw a screen.",
              file=sys.stderr)
        return 2
    from hammunition_console.app import run  # imported late: the refusals above need no urwid

    return run(env)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: Run the entry tests**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: PASS (8 passed). `test_no_tty_is_refused_before_drawing` passes without `hammunition_console.app` existing because the refusal returns first.

- [ ] **Step 9: Write the config tests (failing first)**

Create `tests/test_config.py`:

```python
import stat
from pathlib import Path

import pytest

from hammunition_console import config
from hammunition_console.config import Config


def env_for(tmp_path: Path) -> dict[str, str]:
    return {"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "xdg")}


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert config.load(config.config_path(env_for(tmp_path))) == Config()


def test_round_trip_and_modes(tmp_path: Path) -> None:
    path = config.config_path(env_for(tmp_path))
    assert config.save(Config(last_screen="logs", theme="light", walkthrough_dismissed=True), path)
    assert config.load(path) == Config("logs", "light", True)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert path.parent.name == "hammunition-console"


def test_xdg_config_home_wins_then_home(tmp_path: Path) -> None:
    assert config.config_dir({"HOME": "/h", "XDG_CONFIG_HOME": "/x"}) == Path("/x/hammunition-console")
    assert config.config_dir({"HOME": "/h"}) == Path("/h/.config/hammunition-console")


def test_the_file_holds_exactly_three_keys(tmp_path: Path) -> None:
    import tomllib

    path = config.config_path(env_for(tmp_path))
    config.save(Config(), path)
    assert set(tomllib.loads(path.read_text())) == {"last_screen", "theme", "walkthrough_dismissed"}


@pytest.mark.parametrize(
    "content",
    [
        b"\xff\xfe\x00garbage",
        b"last_screen = ",
        b"last_screen = 5\ntheme = true\nwalkthrough_dismissed = 'yes'\n",
        b"last_screen = 'no-such-screen'\ntheme = 'purple'\n",
        b"[[[[",
        b"",
    ],
)
def test_corrupt_or_hand_edited_config_gives_defaults_not_a_crash(tmp_path: Path, content: bytes) -> None:
    path = config.config_path(env_for(tmp_path))
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    assert config.load(path) == Config()


def test_partially_valid_config_keeps_the_valid_keys(tmp_path: Path) -> None:
    path = config.config_path(env_for(tmp_path))
    path.parent.mkdir(parents=True)
    path.write_text("last_screen = 'update'\ntheme = 'purple'\n")
    assert config.load(path) == Config(last_screen="update")


def test_save_failure_is_reported_not_raised(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert config.save(Config(), blocker / "sub" / "config.toml") is False
```

- [ ] **Step 10: Run it; confirm it fails, implement, confirm it passes**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: FAIL (`ImportError: cannot import name 'config'`).

Create `hammunition_console/config.py`:

```python
"""The console's own configuration. It holds the last screen, the colour theme and
whether the first-run checklist was dismissed, and nothing else: never a station
value (the engine's station config is where those live)."""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR_NAME = "hammunition-console"
SCREENS = ("home", "install", "station", "logs", "update", "help")
THEMES = ("dark", "light")


@dataclass
class Config:
    last_screen: str = "home"
    theme: str = "dark"
    walkthrough_dismissed: bool = False


def config_dir(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME") or Path.home()) / ".config")
    return Path(base) / CONFIG_DIR_NAME


def config_path(environ: Mapping[str, str] | None = None) -> Path:
    return config_dir(environ) / "config.toml"


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return Config()
    cfg = Config()
    screen, theme, dismissed = (data.get(k) for k in ("last_screen", "theme", "walkthrough_dismissed"))
    if isinstance(screen, str) and screen in SCREENS:
        cfg.last_screen = screen
    if isinstance(theme, str) and theme in THEMES:
        cfg.theme = theme
    if isinstance(dismissed, bool):
        cfg.walkthrough_dismissed = dismissed
    return cfg


def _dump(cfg: Config) -> str:
    return (
        f"last_screen = {json.dumps(cfg.last_screen)}\n"
        f"theme = {json.dumps(cfg.theme)}\n"
        f"walkthrough_dismissed = {'true' if cfg.walkthrough_dismissed else 'false'}\n"
    )


def save(cfg: Config, path: Path | None = None) -> bool:
    """Write atomically, 0600 in a 0700 directory. False when it could not (never raises)."""
    path = path or config_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_dump(cfg))
        os.replace(tmp, path)
    except OSError:
        return False
    return True
```

Run: `python3 -m pytest tests/test_config.py tests/test_cli.py tests/test_spdx.py -v`
Expected: PASS (all).

- [ ] **Step 11: Lint, type-check, commit**

Run: `python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy`
Expected: `All checks passed!` and `Success: no issues found`. (Fix real findings; if `mypy` reports urwid as untyped the override in `pyproject.toml` already handles it.)

```bash
cd /home/chiefgyk3d/src/hammunition-console && git add -A && git commit -m "Scaffold hammunition-console: entry point, config, header check, licence"
```

---

### Task 2: Recorded fixtures, capture script, leak scan, schema check

Fixtures are real documents recorded from a real engine run on a machine with placeholder station values, scrubbed, scanned for identifiers, and validated against the engine's published JSON Schemas. Hand-authored fixtures are allowed only where the engine cannot yet produce the shape (E2, the six `logs` result words, a refused `update`), and are named as such in `tests/fixtures/README.md`.

**Files:**
- Create: `tests/fixture_scan.py`, `tests/schema_check.py`, `scripts/capture_fixtures.py`
- Create: `tests/fixtures/` (recorded and hand-authored files), `tests/fixtures/README.md`, `tests/fixtures/schemas/`
- Test: `tests/test_fixture_scan.py`, `tests/test_schema_check.py`, `tests/test_fixtures.py`

**Interfaces:**
- Produces: `fixture_scan.findings(text: str) -> list[str]` (empty means clean); `schema_check.validate(instance: Any, schema: Mapping[str, Any]) -> list[str]` (empty means valid; the schema's `$defs` are read from the schema itself); `schema_check.ENVELOPE = frozenset({"schema", "kind", "engine"})`; `capture_fixtures.extract_schemas(markdown: str) -> dict[str, dict[str, Any]]` (kind to schema); fixture files named `<name>.json` plus optional `<name>.exit` (exit code as text, default 0); `tests/fixtures/manifest.json` with keys `profile`, `gated`, `refused`.

- [ ] **Step 1: Write the leak scan and its tests (failing first)**

Create `tests/test_fixture_scan.py`:

```python
import getpass
import socket

from tests.fixture_scan import findings


def test_placeholders_are_clean() -> None:
    assert findings('{"callsign": "N0CALL", "alt": "N0TST", "grid": "FN31pr", "path": "/home/user/x"}') == []


def test_a_real_looking_callsign_is_found() -> None:
    assert any("callsign" in f for f in findings('{"callsign": "ZZ9ZZ"}'))
    assert any("callsign" in f for f in findings("QQ1QQ"))


def test_a_real_looking_grid_is_found() -> None:
    assert any("grid" in f for f in findings('{"grid_square": "JJ00aa"}'))


def test_a_real_home_path_is_found() -> None:
    assert any("home" in f for f in findings("/home/someoneelse/.config"))


def test_this_machines_username_and_hostname_are_found() -> None:
    user = getpass.getuser()
    if len(user) >= 3:
        assert findings(f"owner {user}")
    host = socket.gethostname().split(".")[0]
    if len(host) >= 3:
        assert findings(f"on {host}")


def test_a_serial_by_id_path_is_found() -> None:
    assert findings("/dev/serial/by-id/usb-Silicon_Labs_CP2105_0123ABCD-if00")
    assert findings("/dev/serial/by-id/usb-FIXTURE-if00") == []
```

- [ ] **Step 2: Run it; confirm it fails; implement**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_fixture_scan.py -v`
Expected: FAIL (`ModuleNotFoundError: tests.fixture_scan`).

Create `tests/fixture_scan.py`:

```python
"""Find anything in a fixture that could identify a person or a machine.

A callsign and a grid square are never public; neither is a hostname, a
serial, a username or a real home path. Fixtures use N0CALL, N0TST, FN31pr,
/home/user and the host name `host`."""

from __future__ import annotations

import getpass
import re
import socket

ALLOWED_CALLSIGNS = {"N0CALL", "N0TST"}
ALLOWED_GRIDS = {"FN31pr"}
# Words that look like a callsign or a grid but are not one. Every addition must
# be reviewed by a person and say why in a comment.
ALLOWED_WORDS: set[str] = set()

CALL = re.compile(r"\b(?:[A-Z]{1,2}|[0-9][A-Z])[0-9][A-Z]{1,3}\b")
GRID = re.compile(r"\b[A-R]{2}[0-9]{2}(?:[a-x]{2})?\b")
HOME = re.compile(r"/home/([A-Za-z0-9._-]+)")
BY_ID = re.compile(r"/dev/serial/by-id/(\S+)")


def findings(text: str) -> list[str]:
    out: list[str] = []
    for m in CALL.finditer(text):
        word = m.group(0)
        if word not in ALLOWED_CALLSIGNS and word not in ALLOWED_WORDS:
            out.append(f"callsign-like token {word!r}")
    for m in GRID.finditer(text):
        word = m.group(0)
        if word not in ALLOWED_GRIDS and word not in ALLOWED_WORDS:
            out.append(f"grid-square-like token {word!r}")
    for m in HOME.finditer(text):
        if m.group(1) != "user":
            out.append(f"home path for {m.group(1)!r} (use /home/user)")
    for m in BY_ID.finditer(text):
        if "FIXTURE" not in m.group(1):
            out.append(f"serial-bearing device path {m.group(0)!r} (use usb-FIXTURE-if00)")
    lowered = text.lower()
    for label, value in (("username", getpass.getuser()), ("hostname", socket.gethostname().split(".")[0])):
        if len(value) >= 3 and value.lower() in lowered:
            out.append(f"this machine's {label}")
    return out
```

Run: `python3 -m pytest tests/test_fixture_scan.py -v`
Expected: PASS (6 passed). Note: if this machine's username or hostname is a common English word that appears in legitimate fixture text, that test still holds; the capture script reports the offending line so a person decides.

- [ ] **Step 3: Write the schema checker and its tests (failing first)**

The engine's documents are validated by the schemas in `docs/reference/json-interface.md`, which describe a document without the three envelope fields, so the checker strips them. It supports exactly the keywords those schemas use.

Create `tests/test_schema_check.py`:

```python
from typing import Any

from tests.schema_check import ENVELOPE, validate

SCHEMA: dict[str, Any] = {
    "$defs": {"Row": {"type": "object", "additionalProperties": False,
                      "properties": {"n": {"type": "integer"}, "s": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
                      "required": ["n", "s"]}},
    "type": "object", "additionalProperties": False,
    "properties": {"rows": {"type": "array", "items": {"$ref": "#/$defs/Row"}}},
    "required": ["rows"],
}


def test_valid_document_passes() -> None:
    assert validate({"rows": [{"n": 1, "s": None}, {"n": 2, "s": "x"}]}, SCHEMA) == []


def test_extra_field_is_rejected() -> None:
    assert validate({"rows": [{"n": 1, "s": None, "extra": 1}]}, SCHEMA)


def test_missing_required_field_is_rejected() -> None:
    assert validate({"rows": [{"n": 1}]}, SCHEMA)


def test_wrong_type_is_rejected_and_bool_is_not_an_integer() -> None:
    assert validate({"rows": [{"n": "1", "s": None}]}, SCHEMA)
    assert validate({"rows": [{"n": True, "s": None}]}, SCHEMA)


def test_the_envelope_names() -> None:
    assert ENVELOPE == {"schema", "kind", "engine"}
```

Run: `python3 -m pytest tests/test_schema_check.py -v`
Expected: FAIL (`ModuleNotFoundError: tests.schema_check`).

Create `tests/schema_check.py`:

```python
"""A small JSON Schema checker for exactly the keywords the engine's published
schemas use ($ref into $defs, anyOf, type, items, properties, required,
additionalProperties). Standard library only, so the test suite needs nothing
the console does not."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ENVELOPE = frozenset({"schema", "kind", "engine"})

_TYPES: dict[str, Any] = {
    "string": str, "integer": int, "number": (int, float), "boolean": bool,
    "array": list, "object": dict, "null": type(None),
}


def _type_ok(value: Any, name: str) -> bool:
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[name])


def validate(instance: Any, schema: Mapping[str, Any]) -> list[str]:
    root = schema
    out: list[str] = []

    def walk(value: Any, sub: Mapping[str, Any], path: str) -> list[str]:
        if "$ref" in sub:
            ref = str(sub["$ref"])
            assert ref.startswith("#/$defs/"), f"unsupported $ref {ref}"
            return walk(value, root["$defs"][ref.split("/")[-1]], path)
        if "anyOf" in sub:
            attempts = [walk(value, option, path) for option in sub["anyOf"]]
            return [] if any(not a for a in attempts) else [f"{path}: matches none of anyOf ({attempts[0][0] if attempts[0] else ''})"]
        errs: list[str] = []
        kind = sub.get("type")
        if kind is not None and not _type_ok(value, kind):
            return [f"{path}: expected {kind}, got {type(value).__name__}"]
        if kind == "array":
            for i, item in enumerate(value):
                if "items" in sub:
                    errs += walk(item, sub["items"], f"{path}[{i}]")
        if kind == "object":
            props: Mapping[str, Any] = sub.get("properties", {})
            for name in sub.get("required", []):
                if name not in value:
                    errs.append(f"{path}: missing required {name!r}")
            for name, item in value.items():
                if name in props:
                    errs += walk(item, props[name], f"{path}.{name}")
                elif sub.get("additionalProperties") is False:
                    errs.append(f"{path}: unexpected field {name!r}")
        return errs

    if isinstance(instance, dict):
        instance = {k: v for k, v in instance.items() if k not in ENVELOPE}
    out += walk(instance, schema, "$")
    return out
```

Run: `python3 -m pytest tests/test_schema_check.py -v`
Expected: PASS (5 passed).

- [ ] **Step 4: Write the capture script and the schema extractor (test first)**

Create `tests/test_capture_schemas.py`:

```python
from scripts.capture_fixtures import extract_schemas

MD = """### status

text

| field | type |

<details><summary>JSON Schema</summary>

```json
{"title": "StatusDocument", "type": "object", "properties": {}, "required": []}
```

</details>

### unit

```json
{"title": "UnitDocument", "type": "object"}
```
"""


def test_extract_schemas_maps_each_kind_to_its_first_json_block() -> None:
    schemas = extract_schemas(MD)
    assert schemas["status"]["title"] == "StatusDocument"
    assert schemas["unit"]["title"] == "UnitDocument"
```

Run: `python3 -m pytest tests/test_capture_schemas.py -v`
Expected: FAIL (`ModuleNotFoundError: scripts.capture_fixtures`).

Create `scripts/capture_fixtures.py`:

```python
#!/usr/bin/env python3
"""Record the documents the console reads from a real engine, safely.

Everything runs against a throwaway HOME and XDG tree, with the station set to
the placeholders N0CALL / FN31pr, so nothing real is read. Output is scrubbed
(the throwaway home becomes /home/user, this host becomes `host`, this user
`user`) and scanned by tests/fixture_scan.py; a finding aborts the write and
names the line, because a fixture must be reviewed by a person before commit.

  # the engine with E1 (branch profile-state), the shape the console targets:
  python3 scripts/capture_fixtures.py --engine "/path/to/profile-state/.venv/bin/hammunition" \\
      --docs /path/to/profile-state/docs/reference/json-interface.md

  # the same on main, for the shapes without E1: only the list document
  python3 scripts/capture_fixtures.py --engine hammunition --suffix=-without --only list-all \\
      --docs /path/to/main/docs/reference/json-interface.md
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.fixture_scan import findings  # noqa: E402

STATION = ["--callsign=N0CALL", "--grid-square=FN31pr", "--node-alias=TEST"]
REFUSED = "no-such-unit-xyz"
KINDS = ["status", "doctor", "catalog", "profile", "station", "logs", "update", "plan", "error",
         "regions", "books"]

# name -> (words, run before the station is set?)
READS: dict[str, tuple[list[str], bool]] = {
    "station-none": (["station", "show"], True),
    "status": (["status"], False),
    "doctor": (["doctor"], False),
    "list-all": (["list"], False),
    "logs-empty": (["logs"], False),
    "station-set": (["station", "show"], False),
    "show-station": (["show", "station"], False),
    "update-profile": (["update", "station"], False),
    "plan-station": (["install", "station", "--dry-run"], False),
    "plan-uninstall": (["uninstall", "station", "--dry-run"], False),
    "plan-refused": (["install", REFUSED, "--dry-run"], False),
    "books": (["reference", "books"], False),
}


def extract_schemas(markdown: str) -> dict[str, dict[str, Any]]:
    """kind -> the first JSON Schema block under `### <kind>` in json-interface.md."""
    out: dict[str, dict[str, Any]] = {}
    for m in re.finditer(r"^### ([a-z-]+)\n(.*?)(?=^### |\Z)", markdown, re.S | re.M):
        block = re.search(r"```json\n(.*?)\n```", m.group(2), re.S)
        if block:
            out[m.group(1)] = json.loads(block.group(1))
    return out


def scrub(text: str, home: str) -> str:
    text = text.replace(home, "/home/user")
    for real, fake in ((getpass.getuser(), "user"), (socket.gethostname().split(".")[0], "host")):
        if len(real) >= 3:
            text = re.sub(re.escape(real), fake, text, flags=re.I)
    return text


def run(engine: list[str], words: list[str], env: dict[str, str]) -> tuple[int, str]:
    proc = subprocess.run([*engine, *words, "--json"], capture_output=True, text=True, env=env,
                          timeout=900, stdin=subprocess.DEVNULL)
    return proc.returncode, proc.stdout


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", default="hammunition", help="the engine command (shell-quoted)")
    ap.add_argument("--out", default=str(ROOT / "tests" / "fixtures"))
    ap.add_argument("--suffix", default="", help="appended to the list/update/schema names, e.g. -without")
    ap.add_argument("--only", default="", help="comma-separated fixture names to record")
    ap.add_argument("--docs", default="", help="the engine's docs/reference/json-interface.md, for the schemas")
    args = ap.parse_args(argv)
    engine = shlex.split(args.engine)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    only = {n for n in args.only.split(",") if n}
    suffixed = {"list-all", "update-profile"}

    if args.docs:
        schemas = extract_schemas(Path(args.docs).read_text(encoding="utf-8"))
        (out / "schemas").mkdir(exist_ok=True)
        for kind in KINDS:
            (out / "schemas" / f"{kind}{args.suffix}.json").write_text(
                json.dumps(schemas[kind], indent=2) + "\n", encoding="utf-8")
        print(f"schemas written for {', '.join(KINDS)}")

    with tempfile.TemporaryDirectory() as tmp:
        home = tmp
        env = {**os.environ, "HOME": home, "XDG_CONFIG_HOME": f"{home}/.config",
               "XDG_STATE_HOME": f"{home}/.local/state", "XDG_CACHE_HOME": f"{home}/.cache",
               "XDG_DATA_HOME": f"{home}/.local/share"}
        for key in [k for k in env if k.startswith("HAMMUNITION_ACCEPT_")]:
            del env[key]
        problems: list[str] = []
        gated: str | None = None

        def record(name: str, words: list[str]) -> None:
            nonlocal gated
            code, stdout = run(engine, words, env)
            text = scrub(stdout, home)
            bad = findings(text)
            if bad:
                problems.append(f"{name}: {bad}")
                return
            suffix = args.suffix if name in suffixed else ""
            (out / f"{name}{suffix}.json").write_text(text, encoding="utf-8")
            exit_file = out / f"{name}{suffix}.exit"
            if code:
                exit_file.write_text(f"{code}\n", encoding="utf-8")
            elif exit_file.exists():
                exit_file.unlink()
            print(f"recorded {name}{suffix} (exit {code})")
            if name == "list-all" and not only:
                doc = json.loads(text)
                gated = next((p["name"] for p in doc["profiles"] if p.get("consent_gated")), None)

        for name, (words, before) in READS.items():
            if before and (not only or name in only):
                record(name, words)
        if not only or "station-set" in only or only - set(READS):
            code, _ = run(engine, ["station", "set", *STATION], env)
            if code:
                print(f"station set failed with exit {code}", file=sys.stderr)
                return 1
        for name, (words, before) in READS.items():
            if not before and (not only or name in only):
                record(name, words)
        if gated and not only:
            record("plan-gated", ["install", gated, "--dry-run"])
            record("show-gated", ["show", gated])
            (out / "manifest.json").write_text(
                json.dumps({"profile": "station", "gated": gated, "refused": REFUSED}, indent=2) + "\n",
                encoding="utf-8")
        if problems:
            print("NOT WRITTEN (identifier-like content; review each by hand):", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
    print("Review every new file in tests/fixtures by eye before committing: the scan is a net, not a guarantee.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Run: `python3 -m pytest tests/test_capture_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Record the fixtures from the real engine**

This step runs the real engine read-only against a throwaway HOME. It needs the engine's `profile-state` worktree for the E1 shape and the engine's `main` for the shape without. If the `profile-state` branch is not built yet, record the "with" set from the worktree anyway after it is, and until then stop here and ask the maintainer; do not hand-write the E1 fields.

```bash
cd /home/chiefgyk3d/src/hammunition-console
ENGINE_WITH=/home/chiefgyk3d/src/Hammunition-profile-state
ls $ENGINE_WITH/.venv/bin/hammunition || ls /home/chiefgyk3d/src/Hammunition/.venv/bin/hammunition
```
Expected: a path prints. Use the one that exists as `<WITH_BIN>` (the engine built from the `profile-state` worktree; if that worktree has no venv, run `./bootstrap.sh` there first or run the engine as `python3 -m hammunition` with `PYTHONPATH=$ENGINE_WITH/src`, quoting it in `--engine`).

```bash
python3 scripts/capture_fixtures.py --engine "<WITH_BIN>" --docs $ENGINE_WITH/docs/reference/json-interface.md
```
Expected: lines `schemas written for ...` then `recorded station-none (exit 0)` ... `recorded plan-gated (exit 0)` `recorded show-gated (exit 0)`, and the final reminder. `plan-refused` is recorded with `(exit 2)`. If it prints `NOT WRITTEN`, read each finding: a genuine identifier means stop and scrub the source; a harmless word (a unit named like a callsign) means add it to `ALLOWED_WORDS` in `tests/fixture_scan.py` with a one-line reason and re-run.

Now the shape without E1, from the engine's `main` (only `list-all`; its schema too):

```bash
python3 scripts/capture_fixtures.py --engine "/home/chiefgyk3d/src/Hammunition/.venv/bin/hammunition" --suffix=-without --only list-all --docs /home/chiefgyk3d/src/Hammunition/docs/reference/json-interface.md
```
Expected: `schemas written ...` and `recorded list-all-without (exit 0)`. Then confirm the two differ exactly in the E1 fields:

```bash
python3 - <<'PY'
import json
a = json.load(open("tests/fixtures/list-all.json"))["profiles"][0]
b = json.load(open("tests/fixtures/list-all-without.json"))["profiles"][0]
print(sorted(set(a) - set(b)))
PY
```
Expected: `['installed', 'installed_size_bytes', 'members']`.

- [ ] **Step 6: Add the hand-authored fixtures, and the README that names them**

These four cannot be recorded today. Each is validated against the engine's schema by the test in Step 7.

Create `tests/fixtures/regions.json` (the engine's own documented example, `docs/reference/cli.md` "maps regions"; recording it would fetch Geofabrik's index):

```json
{
  "schema": "hammunition/1",
  "kind": "regions",
  "engine": "0.19.0",
  "filter": "vermont",
  "regions": ["north-america/us/vermont"]
}
```

Create `tests/fixtures/logs.json` (a fresh machine has no runs; this carries all six `result` words the schema documents):

```json
{
  "schema": "hammunition/1",
  "kind": "logs",
  "engine": "0.19.0",
  "directory": "/home/user/.local/state/hammunition/logs",
  "total_bytes": 4096,
  "max_files": 30,
  "max_bytes": 209715200,
  "runs": [
    {"path": "/home/user/.local/state/hammunition/logs/20261003T140211Z-install-4242.log", "started": "2026-10-03T14:02:11Z", "command": "install", "pid": 4242, "size": 900, "result": "running", "exit_code": null},
    {"path": "/home/user/.local/state/hammunition/logs/20261003T120000Z-install-4100.log", "started": "2026-10-03T12:00:00Z", "command": "install", "pid": 4100, "size": 800, "result": "ok", "exit_code": 0},
    {"path": "/home/user/.local/state/hammunition/logs/20261003T110000Z-install-4000.log", "started": "2026-10-03T11:00:00Z", "command": "install", "pid": 4000, "size": 700, "result": "failed", "exit_code": 1},
    {"path": "/home/user/.local/state/hammunition/logs/20261003T100000Z-uninstall-3900.log", "started": "2026-10-03T10:00:00Z", "command": "uninstall", "pid": 3900, "size": 600, "result": "refused", "exit_code": 2},
    {"path": "/home/user/.local/state/hammunition/logs/20261003T090000Z-install-3800.log", "started": "2026-10-03T09:00:00Z", "command": "install", "pid": 3800, "size": 500, "result": "not confirmed", "exit_code": 3},
    {"path": "/home/user/.local/state/hammunition/logs/20261003T080000Z-hardware-apply-3700.log", "started": "2026-10-03T08:00:00Z", "command": "hardware-apply", "pid": 3700, "size": 400, "result": "incomplete", "exit_code": null}
  ]
}
```

Create `tests/fixtures/update-all.json` (the E2 shape: no names, a retired row, exit 0; the row's `state` word `retired` is the issue #239 proposal, not yet recorded):

```json
{
  "schema": "hammunition/1",
  "kind": "update",
  "engine": "0.19.0",
  "target": {"distro": "debian", "version": "13", "arch": "x86_64", "id_like": [], "pretty_name": "Debian GNU/Linux 13 (trixie)", "description": "Debian GNU/Linux 13 (trixie) (ID=debian, version=13, arch=x86_64)", "debian_family": true},
  "from_log": true,
  "rows": [
    {"unit": "a2d", "state": "up to date", "detail": "a2d 2.0.5-2", "strategy": "reinstall", "upgradable": []},
    {"unit": "fixture-apt", "state": "candidate differs", "detail": "1.0 installed, 1.1 candidate", "strategy": "reinstall", "upgradable": ["fixture-apt"]},
    {"unit": "acarsdec", "state": "behind the pin", "detail": "built at an earlier pin; `install acarsdec` rebuilds", "strategy": "reinstall", "upgradable": []},
    {"unit": "old-unit", "state": "retired", "detail": "retired in the catalog", "strategy": "reinstall", "upgradable": []}
  ],
  "counts": {"up_to_date": 1, "candidate_differs": 1, "behind_pin": 1, "not_installed": 0, "unknown": 0, "on_install": 0, "manual": 0},
  "lists_note": "apt lists: last refreshed 2026-10-01 06:38 UTC",
  "upgrade_command": "sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --only-upgrade --no-remove -- fixture-apt",
  "rebuild_command": "hammunition install acarsdec",
  "upstream_declared": [],
  "upstream": null
}
```

Create `tests/fixtures/update-all-without.json` and `update-all-without.exit` (what the engine 0.19.0 does with retired units in the log today: refuses with an `error` document and exit 2; the message text is representative, not recorded):

```json
{
  "schema": "hammunition/1",
  "kind": "error",
  "engine": "0.19.0",
  "command": "update",
  "exit_code": 2,
  "message": "update: 9 unit(s) the transaction log names are retired in the catalog: old-unit ... Name the units to compare.\n"
}
```

```text
2
```

(The `.exit` file contains the single line `2`.)

Create `tests/fixtures/README.md`:

```markdown
# Fixtures

Documents the console reads, one file per command, plus `<name>.exit` where the exit code is not 0.

Recorded from a real engine by `scripts/capture_fixtures.py` on a throwaway HOME with the station set to
`N0CALL` / `FN31pr`, scrubbed and scanned (`tests/fixture_scan.py`). Review every file by eye for
identifiers before committing: the scan is a net.

Hand-authored, because the engine cannot produce the shape today, each validated against the engine's own
JSON Schema (`schemas/`) by `tests/test_fixtures.py`:

- `regions.json`: the engine's documented example; recording it fetches Geofabrik's index.
- `logs.json`: a fresh machine has no runs; this carries every `result` word the schema documents.
- `update-all.json`: the E2 shape (issue #239): a retired unit as a row and exit 0. The `retired` state word
  is the proposal in that issue. Replace with a recording when #239 lands.
- `update-all-without.json` + `.exit`: engine 0.19.0 refusing `update` with exit 2 when the log names retired
  units. The message text is representative, not recorded.

`list-all.json` carries the E1 fields (`members`, `installed`, `installed_size_bytes`);
`list-all-without.json` is the engine without them (recorded from `main`).
`schemas/<kind>[-without].json` are extracted from the engine's `docs/reference/json-interface.md`.
```

- [ ] **Step 7: Write the fixture tests (they must pass on what Steps 5 and 6 produced)**

Create `tests/test_fixtures.py`:

```python
import json
from pathlib import Path
from typing import Any

import pytest

from tests.fixture_scan import findings
from tests.schema_check import validate

FIX = Path(__file__).parent / "fixtures"
FILES = sorted(p for p in FIX.glob("*.json") if p.name != "manifest.json")


def schema_for(path: Path, kind: str) -> dict[str, Any]:
    suffixed = FIX / "schemas" / f"{kind}-without.json"
    plain = FIX / "schemas" / f"{kind}.json"
    chosen = suffixed if path.stem.endswith("-without") and suffixed.exists() else plain
    assert chosen.exists(), f"no schema for {path.name}: run scripts/capture_fixtures.py --docs <json-interface.md>"
    return json.loads(chosen.read_text())  # type: ignore[no-any-return]


def test_there_are_fixtures() -> None:
    assert len(FILES) >= 15, "run scripts/capture_fixtures.py (Task 2, Step 5)"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_fixture_validates_against_the_engines_schema(path: Path) -> None:
    doc = json.loads(path.read_text())
    assert doc["schema"] == "hammunition/1"
    problems = validate(doc, schema_for(path, doc["kind"]))
    assert problems == [], f"{path.name} disagrees with the published schema: {problems[:3]}"


@pytest.mark.parametrize("path", [*FILES, *FIX.glob("*.exit"), FIX / "manifest.json", FIX / "README.md"],
                         ids=lambda p: p.name)
def test_fixture_carries_no_identifier(path: Path) -> None:
    assert findings(path.read_text()) == [], f"{path.name}: review and scrub by hand"


def test_e1_fields_are_present_with_and_absent_without() -> None:
    with_e1 = json.loads((FIX / "list-all.json").read_text())["profiles"][0]
    without = json.loads((FIX / "list-all-without.json").read_text())["profiles"][0]
    assert {"members", "installed", "installed_size_bytes"} <= set(with_e1)
    assert not {"members", "installed", "installed_size_bytes"} & set(without)


def test_the_station_fixtures_use_only_placeholders() -> None:
    doc = json.loads((FIX / "station-set.json").read_text())
    assert (doc["callsign"], doc["grid_square"]) == ("N0CALL", "FN31pr")
    assert json.loads((FIX / "station-none.json").read_text())["callsign"] is None
```

The only `# type: ignore` here is on the `json.loads` return; if mypy accepts it without, delete it (`warn_unused_ignores` is on under `strict`).

Run: `python3 -m pytest tests/test_fixtures.py -v`
Expected: PASS. If `test_fixture_validates_against_the_engines_schema` fails for `list-all.json`, the schema extracted from the branch lacks the E1 fields: re-run the capture with `--docs` pointing at the `profile-state` worktree's document, which that branch regenerates.

- [ ] **Step 8: Falsify the leak scan against a real fixture, then commit**

Run: `python3 - <<'PY'
import json, pathlib
p = pathlib.Path("tests/fixtures/station-set.json")
d = json.loads(p.read_text()); d["callsign"] = "ZZ9ZZ"
pathlib.Path("/tmp/fx-leak.json").write_text(json.dumps(d))
from tests.fixture_scan import findings
print(findings(pathlib.Path("/tmp/fx-leak.json").read_text()))
PY`
Expected: `["callsign-like token 'ZZ9ZZ'"]`. (Then `rm /tmp/fx-leak.json`.)

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add recorded fixtures, capture script, identifier scan and schema check"
```
Expected: ruff and mypy clean, all tests pass, one commit.

---

### Task 3: The fake `hammunition` and the test helpers

A script on `PATH` named `hammunition` answers `--json` reads from the fixtures and, for a real `install`, behaves like the engine's consent gate: it calls `input()` only when stdin is a tty, prompts, and exits 0 on `yes` and 3 otherwise (3 is the engine's "consent declined or could not be presented"; the spec says 1, the real exit code table in `docs/reference/cli.md` says 3). Its answers come from a pure `respond()` function the in-process `FakeEngine` also uses, so there is one mapping.

**Files:**
- Create: `tests/fake_hammunition.py`, `tests/helpers.py`
- Test: `tests/test_fake_hammunition.py`

**Interfaces:**
- Produces: `tests.fake_hammunition.respond(argv: Sequence[str], fixtures: Path = FIXTURES, suffix: str = "", station: str = "set") -> tuple[str, int] | None` (stdout text and exit code for a `--json` read, `None` when unmapped); `tests.helpers.make_shim(directory: Path) -> Path` (a directory with an executable `hammunition` to put first on `PATH`); `tests.helpers.render(widget, cols=80, rows=24) -> str`; `tests.helpers.load(name: str) -> dict[str, Any]` (a fixture's JSON); later tasks add `FakeEngine`, `FakeContext` to `helpers.py`.

- [ ] **Step 1: Write the fake's tests (failing first)**

Create `tests/test_fake_hammunition.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

from tests import fake_hammunition as fake
from tests.helpers import load, make_shim

FAKE = Path(fake.__file__)


def test_status_comes_from_its_fixture() -> None:
    out, code = fake.respond(["hammunition", "status", "--json"]) or ("", -1)
    assert code == 0 and json.loads(out) == load("status")


def test_exit_codes_come_from_the_sidecar() -> None:
    out, code = fake.respond(["hammunition", "update", "--json"], suffix="-without") or ("", -1)
    assert code == 2 and json.loads(out)["kind"] == "error"


def test_install_dry_run_returns_a_plan_and_refused_names_return_the_refusal() -> None:
    out, code = fake.respond(["hammunition", "install", "station", "--dry-run", "--json"]) or ("", -1)
    assert json.loads(out)["kind"] == "plan" and code == 0
    out, code = fake.respond(["hammunition", "install", "no-such-unit-xyz", "--dry-run", "--json"]) or ("", -1)
    assert json.loads(out)["outcome"] == "refused" and code == 2


def test_station_show_follows_the_station_variant() -> None:
    out, _ = fake.respond(["hammunition", "station", "show", "--json"], station="none") or ("", -1)
    assert json.loads(out)["callsign"] is None


def test_an_unmapped_argv_is_none() -> None:
    assert fake.respond(["hammunition", "hardware", "list", "--json"]) is None


def run_shim(tmp: Path, *args: str, stdin: int | None = subprocess.DEVNULL) -> subprocess.CompletedProcess[str]:
    shim = make_shim(tmp)
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"}
    return subprocess.run(["hammunition", *args], capture_output=True, text=True, env=env, stdin=stdin)


def test_a_real_install_without_a_tty_is_refused_like_the_engine(tmp_path: Path) -> None:
    done = run_shim(tmp_path, "install", "station")
    assert done.returncode == 3 and "no interactive terminal" in done.stderr


def test_an_unmapped_read_fails_loudly(tmp_path: Path) -> None:
    done = run_shim(tmp_path, "hardware", "list", "--json")
    assert done.returncode == 99 and "FAKE: unmapped" in done.stderr


def test_the_invocation_log_records_argv_tty_and_consent_looking_variables(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    shim = make_shim(tmp_path)
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}", "FAKE_HAMMUNITION_LOG": str(log),
           "HAMMUNITION_ACCEPT_RF_RESEARCH": "1"}
    subprocess.run(["hammunition", "status", "--json"], env=env, capture_output=True, stdin=subprocess.DEVNULL)
    entry = json.loads(log.read_text().splitlines()[0])
    assert entry["argv"] == ["status", "--json"] and entry["tty"] is False
    assert "HAMMUNITION_ACCEPT_RF_RESEARCH" in entry["env"]


def test_the_script_runs_standalone_with_the_current_interpreter() -> None:
    done = subprocess.run([sys.executable, str(FAKE), "--version"], capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.startswith("hammunition ")
```

- [ ] **Step 2: Run it; confirm it fails**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_fake_hammunition.py -v`
Expected: FAIL (`ModuleNotFoundError: tests.fake_hammunition`).

- [ ] **Step 3: Implement the fake and the helpers**

Create `tests/fake_hammunition.py`:

```python
#!/usr/bin/env python3
"""A stand-in for `hammunition`, for tests only.

--json reads are answered from tests/fixtures (see respond()). A real `install`
or `hardware apply` behaves like the engine's consent gate: it reads an answer
with input() ONLY when stdin is a tty, prints a prompt, exits 0 on `yes` and 3
otherwise (the engine's "consent declined or not presented"). Nothing here ever
reads the environment for consent. Environment knobs: FAKE_HAMMUNITION_FIXTURES,
FAKE_HAMMUNITION_SUFFIX ("" or "-without": the engine with or without E1/E2),
FAKE_HAMMUNITION_STATION ("set" or "none"), FAKE_HAMMUNITION_LOG (a file that
gets one JSON line per invocation: argv, whether stdin is a tty, and the names
of any HAMMUNITION_ variables it saw).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

FIXTURES = Path(os.environ.get("FAKE_HAMMUNITION_FIXTURES", Path(__file__).parent / "fixtures"))
VERSION = "0.19.0"


def _read(fixtures: Path, name: str) -> tuple[str, int] | None:
    path = fixtures / f"{name}.json"
    if not path.exists():
        return None
    exit_file = fixtures / f"{name}.exit"
    code = int(exit_file.read_text().strip()) if exit_file.exists() else 0
    return path.read_text(), code


def respond(
    argv: Sequence[str], fixtures: Path = FIXTURES, suffix: str = "", station: str = "set"
) -> tuple[str, int] | None:
    """The stdout and exit code for a `--json` read, or None when nobody mapped it."""
    words = [w for w in argv[1:] if w != "--json"]
    manifest = json.loads((fixtures / "manifest.json").read_text())
    if words == ["status"]:
        return _read(fixtures, "status")
    if words == ["doctor"]:
        return _read(fixtures, "doctor")
    if words == ["logs"]:
        return _read(fixtures, "logs")
    if words[:1] == ["list"]:
        return _read(fixtures, f"list-all{suffix}")
    if words[:2] == ["station", "show"]:
        return _read(fixtures, "station-set" if station == "set" else "station-none")
    if words[:1] == ["update"]:
        names = [w for w in words[1:] if not w.startswith("-")]
        return _read(fixtures, f"update-all{suffix}" if not names else "update-profile")
    if words[:2] == ["maps", "regions"]:
        return _read(fixtures, "regions")
    if words[:2] == ["reference", "books"]:
        return _read(fixtures, "books")
    if words[:1] == ["show"] and len(words) == 2:
        name = words[1]
        if name == manifest["gated"]:
            return _read(fixtures, "show-gated")
        return _read(fixtures, "show-station") if name == manifest["profile"] else None
    if words[:1] in (["install"], ["uninstall"]) and "--dry-run" in words:
        names = [w for w in words[1:] if not w.startswith("-")]
        if words[0] == "uninstall":
            return _read(fixtures, "plan-uninstall")
        if names and names[0] == manifest["refused"]:
            return _read(fixtures, "plan-refused")
        if names and names[0] == manifest["gated"]:
            return _read(fixtures, "plan-gated")
        return _read(fixtures, "plan-station")
    return None


def _ask(prompt: str) -> int:
    if not sys.stdin.isatty():
        print("hammunition: no interactive terminal; a consent gate cannot be answered", file=sys.stderr)
        return 3
    print(prompt, end="", flush=True)
    try:
        answer = input()
    except EOFError:
        return 3
    if answer.strip() == "yes":
        print("confirmed")
        return 0
    print("declined")
    return 3


def main(argv: list[str]) -> int:
    log = os.environ.get("FAKE_HAMMUNITION_LOG")
    if log:
        entry = {
            "argv": argv,
            "tty": sys.stdin.isatty(),
            "env": sorted(k for k in os.environ if k.startswith("HAMMUNITION_") or k.endswith("_CONSENT")),
        }
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    if argv == ["--version"]:
        print(f"hammunition {VERSION}")
        return 0
    suffix = os.environ.get("FAKE_HAMMUNITION_SUFFIX", "")
    station = os.environ.get("FAKE_HAMMUNITION_STATION", "set")
    if "--json" in argv:
        answered = respond(["hammunition", *argv], FIXTURES, suffix, station)
        if answered is None:
            print(f"FAKE: unmapped argv {argv!r}", file=sys.stderr)
            return 99
        sys.stdout.write(answered[0])
        return answered[1]
    if argv[:1] == ["install"] and "--dry-run" not in argv:
        print(f"Installing {' '.join(argv[1:])}")
        code = _ask("Type 'yes' to continue: ")
        if code == 0:
            print("installed")
        return code
    if argv[:2] == ["hardware", "apply"]:
        print("plan: write udev rules, add groups")
        return _ask("Type 'yes' to apply: ")
    if argv[:2] == ["station", "set"]:
        print("saved")
        return 0
    print(f"FAKE: unmapped argv {argv!r}", file=sys.stderr)
    return 99


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Create `tests/helpers.py`:

```python
"""Shared test helpers. FakeEngine and FakeContext are added in later tasks."""

from __future__ import annotations

import json
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

import urwid

FIXTURES = Path(__file__).parent / "fixtures"
FAKE = Path(__file__).parent / "fake_hammunition.py"


def load(name: str) -> dict[str, Any]:
    """A recorded fixture's document, by file stem."""
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    assert isinstance(data, dict)
    return data


def make_shim(directory: Path) -> Path:
    """A directory holding an executable `hammunition` that runs the fake with this interpreter."""
    bin_dir = directory / "shim-bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "hammunition"
    shim.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} \"$@\"\n")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def render(widget: urwid.Widget, cols: int = 80, rows: int = 24) -> str:
    """A box widget drawn to text, trailing blanks trimmed."""
    canvas = widget.render((cols, rows), focus=True)
    return "\n".join(line.decode("utf-8").rstrip() for line in canvas.text)
```

- [ ] **Step 4: Run the tests; they pass**

Run: `python3 -m pytest tests/test_fake_hammunition.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the fake hammunition: fixture reads and a tty-only consent prompt"
```
Expected: clean, all pass.

---

### Task 4: Consent guard, JSON verb table, and the engine reader

The three small modules every other task depends on. The guard is the only place the consent tokens may appear.

**Files:**
- Create: `hammunition_console/guard.py`, `hammunition_console/verbs.py`, `hammunition_console/engine.py`
- Test: `tests/test_guard.py`, `tests/test_verbs.py`, `tests/test_engine.py`, `tests/test_consent_guard.py`

**Interfaces:**
- Produces (guard): `guard.Refused(Exception)`; `guard.FORBIDDEN_ARGS: frozenset[str]`; `guard.is_consent_variable(name: str) -> bool`; `guard.scrubbed_environ(environ: Mapping[str, str]) -> dict[str, str]`; `guard.checked_argv(argv: Sequence[str]) -> list[str]` (raises `Refused`; allows only `hammunition install|uninstall|station set|hardware apply ...` and the one `sudo apt-get install --only-upgrade --no-remove -- PKG...` shape); `guard.apt_upgrade_argv(command: str | None) -> list[str] | None`; `guard.assert_clean_read(words: Sequence[str]) -> None` (raises `Refused` on a forbidden word in a read).
- Produces (verbs): `verbs.JSON_VERBS: frozenset[tuple[str, ...]]`; `verbs.NotAJsonVerb(Exception)`; `verbs.verb_of(words) -> tuple[str, ...]`; `verbs.require_json_verb(words) -> None`.
- Produces (engine): `engine.ENGINE_FLOOR = (0, 19, 0)`; `engine.EngineError`, `EngineMissing`, `EngineTooOld`, `UnknownSchema`, `BadDocument`, `EngineRefused(exit_code: int, message: str)`; `engine.Document(kind, engine, schema, exit_code, body)` frozen dataclass (`body: Mapping[str, Any]`, the whole document); `engine.parse_version(text) -> tuple[int, int, int]`; `engine.parse_document(stdout, exit_code, stderr="") -> Document`; `engine.accept(doc, floor=ENGINE_FLOOR) -> Document` (floor check, then raises `EngineRefused` for kind `error`); `engine.Engine(binary="hammunition", environ=None, run=subprocess.run)` with `.binary`, `.command(*words) -> list[str]`, `.read(*words, timeout=180.0) -> Document`.

- [ ] **Step 1: Write the guard's tests (failing first)**

Create `tests/test_guard.py`:

```python
import pytest

from hammunition_console import guard
from hammunition_console.guard import Refused

APT = "sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --only-upgrade --no-remove -- a b"


@pytest.mark.parametrize("bad", [["hammunition", "install", "x", "--yes"], ["hammunition", "install", "-y"],
                                 ["hammunition", "install", "--yes=1"]])
def test_assume_yes_in_any_spelling_is_refused(bad: list[str]) -> None:
    with pytest.raises(Refused, match="never passes"):
        guard.checked_argv(bad)


@pytest.mark.parametrize("ok", [["hammunition", "install", "station"], ["hammunition", "uninstall", "station"],
                                ["hammunition", "station", "set", "--callsign=N0CALL"],
                                ["hammunition", "hardware", "apply"],
                                ["/usr/bin/hammunition", "install", "station"]])
def test_the_commands_the_console_runs_pass(ok: list[str]) -> None:
    assert guard.checked_argv(ok) == ok


@pytest.mark.parametrize("bad", [[], ["rm", "-rf", "/"], ["hammunition"], ["hammunition", "doctor"],
                                 ["hammunition", "services", "start", "gpsd"], ["sudo", "rm", "x"],
                                 ["sudo", "apt-get", "remove", "x"], ["bash", "-c", "hammunition install x"]])
def test_anything_else_is_refused(bad: list[str]) -> None:
    with pytest.raises(Refused):
        guard.checked_argv(bad)


def test_a_value_that_merely_contains_the_word_is_not_the_flag() -> None:
    argv = ["hammunition", "station", "set", "--callsign=--yes"]
    assert guard.checked_argv(argv) == argv


def test_the_environment_is_scrubbed_of_every_consent_variable() -> None:
    env = {"PATH": "/bin", "HAMMUNITION_ACCEPT_RF_RESEARCH": "1", "HAMMUNITION_ACCEPT_APT_REPO_KISMET_TRIXIE": "AB",
           "MY_CONSENT": "1", "HAMMUNITION_CATALOG": "/c", "HOME": "/h"}
    assert guard.scrubbed_environ(env) == {"PATH": "/bin", "HAMMUNITION_CATALOG": "/c", "HOME": "/h"}


def test_apt_upgrade_command_is_reduced_to_a_pane_argv_without_the_assume_yes() -> None:
    argv = guard.apt_upgrade_argv(APT)
    assert argv == ["sudo", "apt-get", "install", "--only-upgrade", "--no-remove", "--", "a", "b"]
    assert argv is not None and guard.checked_argv(argv) == argv


@pytest.mark.parametrize("bad", [None, "", "sudo apt-get install -- a", "sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --only-upgrade --no-remove --",
                                 APT + " ; rm -rf /", APT + " $(id)", APT + " --purge", "hammunition install a"])
def test_an_unexpected_apt_command_shape_is_not_runnable(bad: str | None) -> None:
    assert guard.apt_upgrade_argv(bad) is None


def test_reads_refuse_a_forbidden_word() -> None:
    with pytest.raises(Refused):
        guard.assert_clean_read(["install", "x", "--dry-run", "-y"])
    guard.assert_clean_read(["install", "x", "--dry-run"])
```

- [ ] **Step 2: Run it; confirm it fails; implement the guard**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_guard.py -v`
Expected: FAIL (`ImportError: cannot import name 'guard'`).

Create `hammunition_console/guard.py`:

```python
"""The consent guard: the one module that may name the engine's assume-yes flag
and its scripted-consent variables, and only to refuse them.

D-021: a gate a convenience flag or an exported variable walks through is not a
gate. The console therefore (1) refuses any argv carrying the flag, (2) strips
every scripted-consent variable from the environment of every child, and (3)
only ever runs the few commands listed here. Lines naming a forbidden token end
with the tag below; tests/test_consent_guard.py fails on any other mention in
the package.
"""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Mapping, Sequence

CONSENT_PREFIX = "HAMMUNITION_ACCEPT_"  # consent-guard
CONSENT_SUFFIX = "_CONSENT"  # consent-guard
FORBIDDEN_ARGS = frozenset({"--yes", "-y"})  # consent-guard
# apt's own assume-yes, which the engine's `update` report prints in its upgrade
# command. The console drops it, so apt asks the operator in the pane.
_APT_REPORT_PREFIX = ["sudo", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "--yes", "--only-upgrade", "--no-remove", "--"]  # consent-guard
_APT_RUN_PREFIX = ["sudo", "apt-get", "install", "--only-upgrade", "--no-remove", "--"]
_APT_PACKAGE = re.compile(r"^[a-z0-9][a-z0-9+.:_-]*$")
# The engine verbs the console runs in a pane; everything else is refused.
WRITE_VERBS: frozenset[tuple[str, ...]] = frozenset(
    {("install",), ("uninstall",), ("station", "set"), ("hardware", "apply")}
)


class Refused(Exception):
    """A command or read the console will not run."""


def is_consent_variable(name: str) -> bool:
    return name.startswith(CONSENT_PREFIX) or name.endswith(CONSENT_SUFFIX)


def scrubbed_environ(environ: Mapping[str, str]) -> dict[str, str]:
    """A copy of the environment with every scripted-consent variable removed."""
    return {k: v for k, v in environ.items() if not is_consent_variable(k)}


def _forbidden(word: str) -> bool:
    return word in FORBIDDEN_ARGS or word.startswith("--yes=")  # consent-guard


def assert_clean_read(words: Sequence[str]) -> None:
    for word in words:
        if _forbidden(word):
            raise Refused(f"the console never passes {word!r}; a read must not carry it")


def checked_argv(argv: Sequence[str]) -> list[str]:
    """The argv to run in a pane, or Refused. Never contains the assume-yes flag."""
    out = list(argv)
    if not out:
        raise Refused("empty command")
    for word in out:
        if _forbidden(word):
            raise Refused(
                f"the console never passes {word!r}: a consent gate is answered by a person, "
                "typing into the real prompt (D-021)"
            )
    head = os.path.basename(out[0])
    if head == "hammunition":
        verb = next((v for v in sorted(WRITE_VERBS, key=len, reverse=True) if tuple(out[1:1 + len(v)]) == v), None)
        if verb is None:
            raise Refused(f"the console does not run `hammunition {' '.join(out[1:3])}` in a pane")
        return out
    if head == "sudo" and out[: len(_APT_RUN_PREFIX)] == _APT_RUN_PREFIX and len(out) > len(_APT_RUN_PREFIX):
        if all(_APT_PACKAGE.match(p) for p in out[len(_APT_RUN_PREFIX):]):
            return out
    raise Refused(f"the console does not run {out[0]!r} in a pane")


def apt_upgrade_argv(command: str | None) -> list[str] | None:
    """The pane argv for the engine's apt upgrade command, or None when it is not exactly that shape.

    The report prints `sudo env DEBIAN_FRONTEND=noninteractive apt-get install
    <apt's assume-yes> --only-upgrade --no-remove -- PKG...`. The console runs the same
    command with the frontend left interactive and without apt's assume-yes, so apt
    shows what it will change and asks.
    """
    if not command:
        return None
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    n = len(_APT_REPORT_PREFIX)
    packages = words[n:]
    if words[:n] != _APT_REPORT_PREFIX or not packages:
        return None
    if not all(_APT_PACKAGE.match(p) for p in packages):
        return None
    return [*_APT_RUN_PREFIX, *packages]
```

Run: `python3 -m pytest tests/test_guard.py -v`
Expected: PASS (all). If `test_anything_else_is_refused[['hammunition']]` fails, the verb search ran on an empty tail; `checked_argv(["hammunition"])` must raise `Refused` (it does: `verb is None`).

- [ ] **Step 3: Write the verb table tests, then implement it**

Create `tests/test_verbs.py`:

```python
import re
from pathlib import Path

import pytest

from hammunition_console import verbs
from hammunition_console.verbs import NotAJsonVerb

ENGINE_DOC = Path("/home/chiefgyk3d/src/Hammunition/docs/reference/json-interface.md")


@pytest.mark.parametrize("words,expected", [
    (["status"], ("status",)), (["station", "show"], ("station", "show")),
    (["maps", "regions", "vermont"], ("maps", "regions")), (["reference", "books"], ("reference", "books")),
    (["list", "profiles"], ("list",)), (["install", "x", "--dry-run"], ("install",)),
])
def test_verb_of(words: list[str], expected: tuple[str, ...]) -> None:
    assert verbs.verb_of(words) == expected


@pytest.mark.parametrize("words", [["hardware", "list"], ["station", "set", "--callsign=X"], ["time"],
                                   ["menus", "apply"], ["hardware", "apply"], []])
def test_a_verb_with_no_json_form_is_refused(words: list[str]) -> None:
    with pytest.raises(NotAJsonVerb):
        verbs.require_json_verb(words)


@pytest.mark.parametrize("verb", ["install", "uninstall"])
def test_install_and_uninstall_are_only_ever_read_as_a_dry_run(verb: str) -> None:
    with pytest.raises(NotAJsonVerb, match="dry-run"):
        verbs.require_json_verb([verb, "station"])
    verbs.require_json_verb([verb, "station", "--dry-run"])


def test_every_verb_is_one_the_engine_lists_under_commands() -> None:
    """The authority is the engine's own list. Skipped only where that checkout is absent."""
    if not ENGINE_DOC.exists():
        pytest.skip("engine checkout not present")
    text = ENGINE_DOC.read_text()
    listed = {tuple(m.group(1).split()) for m in re.finditer(r"^- `hammunition ([a-z ]+?)`", text, re.M)}
    for verb in verbs.JSON_VERBS:
        assert verb in listed, f"{verb} is not under Commands in json-interface.md: it has no JSON form"
```

Run: `python3 -m pytest tests/test_verbs.py -v`
Expected: FAIL (`ImportError`).

Create `hammunition_console/verbs.py`:

```python
"""The only verbs the console ever reads with --json: the engine's "Commands" list
(docs/reference/json-interface.md) restricted to what the console uses. A command
with no JSON form refuses --json and runs nothing; reading one is a bug in a screen,
so it fails loudly here, before anything is spawned."""

from __future__ import annotations

from collections.abc import Sequence

JSON_VERBS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("status",),
        ("doctor",),
        ("list",),
        ("show",),
        ("logs",),
        ("update",),
        ("station", "show"),
        ("install",),
        ("uninstall",),
        ("maps", "regions"),
        ("reference", "books"),
    }
)
DRY_RUN_ONLY: frozenset[tuple[str, ...]] = frozenset({("install",), ("uninstall",)})


class NotAJsonVerb(Exception):
    """A screen asked for a document the engine does not print."""


def verb_of(words: Sequence[str]) -> tuple[str, ...]:
    for n in (2, 1):
        head = tuple(words[:n])
        if len(head) == n and head in JSON_VERBS:
            return head
    raise NotAJsonVerb(f"{' '.join(words[:2])!r} has no --json form; this is a bug in the screen table")


def require_json_verb(words: Sequence[str]) -> None:
    verb = verb_of(words)
    if verb in DRY_RUN_ONLY and "--dry-run" not in words:
        raise NotAJsonVerb(f"`{verb[0]}` is only ever read with --dry-run: a real run is never driven through JSON")
```

Run: `python3 -m pytest tests/test_verbs.py -v`
Expected: PASS.

- [ ] **Step 4: Write the engine reader's tests (failing first)**

Create `tests/test_engine.py`:

```python
import json
import subprocess
from typing import Any

import pytest

from hammunition_console import engine
from hammunition_console.engine import (
    ENGINE_FLOOR, BadDocument, Engine, EngineMissing, EngineRefused, EngineTooOld, UnknownSchema,
)
from hammunition_console.verbs import NotAJsonVerb
from tests.helpers import load


def doc(**over: Any) -> str:
    base = {"schema": "hammunition/1", "kind": "status", "engine": "0.19.0"}
    return json.dumps({**base, **over})


@pytest.mark.parametrize("text,expected", [("0.19.0", (0, 19, 0)), ("1.2.3+dev", (1, 2, 3)), ("v0.20.1", (0, 20, 1))])
def test_parse_version(text: str, expected: tuple[int, int, int]) -> None:
    assert engine.parse_version(text) == expected


def test_unparsable_version_is_a_bad_document() -> None:
    with pytest.raises(BadDocument):
        engine.parse_version("banana")


def test_the_floor_is_the_measured_spike_version() -> None:
    assert ENGINE_FLOOR == (0, 19, 0)


def test_parse_a_recorded_document() -> None:
    d = engine.parse_document(json.dumps(load("status")), 0)
    assert (d.kind, d.schema, d.exit_code) == ("status", "hammunition/1", 0) and d.body["target"]


@pytest.mark.parametrize("stdout", ["", "not json", "[1]", '{"kind": "x"}'])
def test_garbage_is_a_bad_document(stdout: str) -> None:
    with pytest.raises(BadDocument):
        engine.parse_document(stdout, 0, "boom")


@pytest.mark.parametrize("schema", ["hammunition/2", "other/1", "hammunition/1.5", "hammunition"])
def test_an_unknown_schema_is_refused_by_name(schema: str) -> None:
    with pytest.raises(UnknownSchema, match=schema.replace(".", r"\.")):
        engine.parse_document(doc(schema=schema), 0)


def test_the_floor_names_both_versions_and_the_update_command() -> None:
    with pytest.raises(EngineTooOld) as info:
        engine.accept(engine.parse_document(doc(engine="0.18.9"), 0))
    text = str(info.value)
    assert "0.18.9" in text and "0.19.0" in text and "git pull" in text and "bootstrap.sh" in text


def test_an_error_document_raises_with_the_engines_words() -> None:
    d = engine.parse_document(json.dumps(load("update-all-without")), 2)
    with pytest.raises(EngineRefused) as info:
        engine.accept(d)
    assert info.value.exit_code == 2 and "retired" in info.value.message


def test_a_refused_plan_is_a_plan_not_an_error() -> None:
    d = engine.accept(engine.parse_document(json.dumps(load("plan-refused")), 2))
    assert d.kind == "plan" and d.body["outcome"] == "refused" and d.exit_code == 2


class Recorder:
    def __init__(self, stdout: str = "", code: int = 0, error: BaseException | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.stdout, self.code, self.error = stdout, code, error

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((argv, kw))
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(argv, self.code, self.stdout, "")


def test_read_builds_a_fixed_argv_and_scrubs_the_environment() -> None:
    rec = Recorder(json.dumps(load("status")))
    eng = Engine(environ={"PATH": "/bin", "HAMMUNITION_ACCEPT_RF_RESEARCH": "1", "X_CONSENT": "1"}, run=rec)
    eng.read("status")
    argv, kw = rec.calls[0]
    assert argv == ["hammunition", "status", "--json"]
    assert kw["env"] == {"PATH": "/bin"} and kw["stdin"] == subprocess.DEVNULL
    assert kw.get("shell") in (None, False)


def test_names_stay_single_argv_elements() -> None:
    rec = Recorder(json.dumps(load("plan-station")))
    Engine(run=rec).read("install", "a b", "--dry-run")
    assert rec.calls[0][0] == ["hammunition", "install", "a b", "--dry-run", "--json"]


def test_a_missing_engine_names_the_command_and_the_install_page() -> None:
    with pytest.raises(EngineMissing, match="hammunition"):
        Engine(run=Recorder(error=FileNotFoundError())).read("status")


def test_a_timeout_is_an_engine_error_not_a_hang() -> None:
    with pytest.raises(engine.EngineError, match="timed out"):
        Engine(run=Recorder(error=subprocess.TimeoutExpired("hammunition", 1))).read("status", timeout=1)


def test_a_verb_with_no_json_form_never_spawns() -> None:
    rec = Recorder()
    with pytest.raises(NotAJsonVerb):
        Engine(run=rec).read("hardware", "list")
    assert rec.calls == []


def test_the_floor_is_checked_on_every_document() -> None:
    eng = Engine(run=Recorder(doc(engine="0.1.0")))
    with pytest.raises(EngineTooOld):
        eng.read("status")


def test_command_prefixes_the_binary() -> None:
    assert Engine(binary="hammunition").command("install", "station") == ["hammunition", "install", "station"]
```

- [ ] **Step 5: Run it; confirm it fails; implement**

Run: `python3 -m pytest tests/test_engine.py -v`
Expected: FAIL (`ImportError: cannot import name 'engine'`).

Create `hammunition_console/engine.py`:

```python
"""Read the engine's JSON documents. The only module that spawns `hammunition --json`.

The version floor is read from the `engine` field of a document, never from
`hammunition --version` (which prints to stderr and emits no document under
--json). ENGINE_FLOOR is a single constant; raise it when the engine release that
ships E1 and E2 is tagged.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hammunition_console import guard, verbs

ENGINE_FLOOR: tuple[int, int, int] = (0, 19, 0)
SUPPORTED_SCHEMA = "hammunition/1"
INSTALL_PAGE = "https://chiefgyk3d.github.io/Hammunition/getting-started/install/"


class EngineError(Exception):
    """Anything that stops a read."""


class EngineMissing(EngineError):
    pass


class EngineTooOld(EngineError):
    pass


class UnknownSchema(EngineError):
    pass


class BadDocument(EngineError):
    pass


class EngineRefused(EngineError):
    """The engine printed an `error` document: it has no JSON form or refused before planning."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message


@dataclass(frozen=True)
class Document:
    kind: str
    engine: str
    schema: str
    exit_code: int
    body: Mapping[str, Any]


def parse_version(text: str) -> tuple[int, int, int]:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    if not m:
        raise BadDocument(f"the engine reported a version the console cannot read: {text!r}")
    return int(m[1]), int(m[2]), int(m[3])


def parse_document(stdout: str, exit_code: int, stderr: str = "") -> Document:
    if not stdout.strip():
        raise BadDocument(f"the engine printed no document (exit {exit_code}): {stderr.strip()[:300]}")
    try:
        body = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BadDocument(f"the engine printed something that is not JSON (exit {exit_code}): {exc.msg}") from exc
    if not isinstance(body, dict) or not all(isinstance(body.get(k), str) for k in ("schema", "kind", "engine")):
        raise BadDocument("the engine's document lacks schema, kind or engine")
    schema = str(body["schema"])
    if schema != SUPPORTED_SCHEMA:
        raise UnknownSchema(
            f"the engine printed a document of schema {schema!r}; this console knows only "
            f"{SUPPORTED_SCHEMA!r}. Update hammunition-console."
        )
    return Document(str(body["kind"]), str(body["engine"]), schema, exit_code, body)


def accept(doc: Document, floor: tuple[int, int, int] = ENGINE_FLOOR) -> Document:
    have = parse_version(doc.engine)
    if have < floor:
        want = ".".join(str(n) for n in floor)
        raise EngineTooOld(
            f"Hammunition {doc.engine} is older than this console needs ({want} or later). "
            "Update the engine (in its checkout: git pull, then ./bootstrap.sh) and start the console again."
        )
    if doc.kind == "error":
        raise EngineRefused(int(doc.body.get("exit_code", doc.exit_code)), str(doc.body.get("message", "")))
    return doc


Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class Engine:
    def __init__(
        self,
        binary: str = "hammunition",
        environ: Mapping[str, str] | None = None,
        run: Runner = subprocess.run,
    ) -> None:
        self.binary = binary
        self._environ = environ
        self._run = run

    def command(self, *words: str) -> list[str]:
        return [self.binary, *words]

    def read(self, *words: str, timeout: float = 180.0) -> Document:
        verbs.require_json_verb(words)
        guard.assert_clean_read(words)
        argv = [self.binary, *words, "--json"]
        env = guard.scrubbed_environ(os.environ if self._environ is None else self._environ)
        try:
            done = self._run(argv, capture_output=True, text=True, timeout=timeout, env=env,
                             stdin=subprocess.DEVNULL, check=False)
        except FileNotFoundError as exc:
            raise EngineMissing(
                f"{self.binary!r} was not found on PATH. The console runs the engine's own commands and "
                f"cannot work without it. Install the engine first: {INSTALL_PAGE} (run ./bootstrap.sh)."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise EngineError(f"`{' '.join(words)}` timed out after {int(timeout)} s") from exc
        return accept(parse_document(done.stdout, done.returncode, done.stderr))


def command_words(argv: Sequence[str]) -> str:
    """For messages: the verb words of an argv, never its values."""
    return " ".join(w for w in argv if not w.startswith("-"))[:80]
```

Run: `python3 -m pytest tests/test_engine.py -v`
Expected: PASS (all).

- [ ] **Step 6: The package-wide consent grep (write, run, then FALSIFY it)**

Create `tests/test_consent_guard.py`:

```python
"""No file in the package but guard.py may mention the assume-yes flag or a
scripted-consent variable, and guard.py only on lines tagged `# consent-guard`.
This is a grep, so it is falsified on purpose (see the plan)."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "hammunition_console"
TOKENS = ("--yes", '"-y"', "'-y'", "HAMMUNITION_ACCEPT", "_CONSENT")
TAG = "# consent-guard"


def offenders() -> list[str]:
    found: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if any(token in line for token in TOKENS):
                if not (path.name == "guard.py" and TAG in line):
                    found.append(f"{path.relative_to(PACKAGE.parent)}:{number}: {line.strip()}")
    return found


def test_the_package_never_names_the_assume_yes_flag_or_a_consent_variable() -> None:
    assert offenders() == [], (
        "only hammunition_console/guard.py may name these tokens, on lines tagged "
        f"'{TAG}'; the console must never pass the flag or set the variable (D-021)"
    )


def test_the_scan_itself_sees_the_guard_file() -> None:
    assert any(p.name == "guard.py" for p in PACKAGE.rglob("*.py"))
    guard_lines = [l for l in (PACKAGE / "guard.py").read_text().splitlines() if "HAMMUNITION_ACCEPT" in l]
    assert guard_lines and all(TAG in l for l in guard_lines)
```

Run: `python3 -m pytest tests/test_consent_guard.py -v`
Expected: PASS (the docstring in `guard.py` mentions no token literally; its constants carry the tag). If it reports a `guard.py` line, add the tag or reword the comment.

Falsify: add a line to `hammunition_console/engine.py`: `_BAD = "--yes"`. Run: `python3 -m pytest tests/test_consent_guard.py -v`
Expected: FAIL naming `hammunition_console/engine.py:<n>` and the message "only hammunition_console/guard.py may name these tokens". Remove the line; re-run: PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the consent guard, the JSON verb table and the engine reader"
```
Expected: clean, all pass.

---

### Task 5: UI foundations: clean text, background work, context, base screens

**Files:**
- Create: `hammunition_console/fmt.py`, `hammunition_console/worker.py`, `hammunition_console/context.py`, `hammunition_console/screens/__init__.py` (empty), `hammunition_console/screens/base.py`
- Modify: `tests/helpers.py` (add `FakeEngine`, `FakeContext`)
- Test: `tests/test_fmt.py`, `tests/test_worker.py`, `tests/test_base_screens.py`

**Interfaces:**
- Consumes: `engine.Document`, `engine.accept`, `engine.parse_document`, `engine.EngineRefused/EngineMissing/EngineTooOld/UnknownSchema`, `verbs.require_json_verb`, `guard.assert_clean_read`, `guard.checked_argv`, `config.Config`, `tests.fake_hammunition.respond`.
- Produces: `fmt.clean(text: object) -> str`; `fmt.human_size(n: int) -> str`; `fmt.mask(value: str | None) -> str`; `fmt.first_line(text: str) -> str`; `worker.Background` (Protocol: `submit(call: Callable[[], T], done: Callable[[T | None, BaseException | None], None]) -> None`); `worker.SyncBackground()`; `worker.ThreadBackground()` with `.attach(loop: urwid.MainLoop)`; `context.Shared` dataclass (`engine_version="?"`, `target="?"`, `doctor: tuple[int, int, int] | None`, `station_set: bool | None`, `header_text() -> str`); `context.Context` Protocol with attributes `engine`, `config`, `bg`, `shared` and methods `push(screen)`, `pop(count: int = 1)`, `replace(screen)`, `open_screen(name: str, **kwargs: Any)`, `run_pane(argv: Sequence[str], title: str, on_exit: Callable[[int | None], None])`, `fatal(exc: BaseException)`, `refresh_header()`, `after(seconds: float, fn: Callable[[], None])`, `save_config()`; `screens.base.FATAL: tuple[type[Exception], ...]`; `screens.base.describe_error(exc: BaseException) -> str`; `screens.base.text(content: str, attr: str | None = None) -> urwid.Widget`; `screens.base.Row(text, value=None, *, attr=None, selectable=True)` with `.value`, `.set_text`, signal `activate`; `screens.base.Screen(ctx)` with `name`, `title`, `widget()`, `on_show()`, `on_hide()`, `keypress(key) -> str | None`, `redraw()`, `set_rows(rows)`, `load(key, call, done)`, `status`/`errors` dicts; `screens.base.PromptScreen(ctx, title, label, on_submit, *, note="")`; `screens.base.ConfirmScreen(ctx, title, lines, on_confirm)`; `screens.base.MessageScreen(ctx, title, lines)`; test doubles `helpers.FakeEngine(suffix="")` (`.calls`, `.set(words, result)`, `.read`, `.command`, `.binary`) and `helpers.FakeContext(engine=None, config=None)` (`.pushed`, `.popped`, `.replaced`, `.opened`, `.panes`, `.timers`, `.fatals`, `.saved`).

- [ ] **Step 1: Write the text-safety tests (failing first)**

Create `tests/test_fmt.py`:

```python
import pytest

from hammunition_console.fmt import clean, first_line, human_size, mask


@pytest.mark.parametrize("raw", ["\x1b[2J\x1b[31mred", "a\x1b]0;title\x07b", "x\x00y", "a\x7fb", "c\x9b31md", "bell\x07"])
def test_clean_removes_every_control_character(raw: str) -> None:
    out = clean(raw)
    assert not any(ord(c) < 32 and c != "\n" or 0x7F <= ord(c) <= 0x9F for c in out)


def test_clean_keeps_text_newlines_and_expands_tabs() -> None:
    assert clean("a\tb\nc") == "a    b\nc"
    assert clean("plain text 123") == "plain text 123"


def test_clean_accepts_non_strings_and_none() -> None:
    assert clean(None) == "None" and clean(7) == "7"


def test_human_size() -> None:
    assert [human_size(n) for n in (0, 512, 2048, 5 * 1024**2, 3 * 1024**3)] == ["0 B", "512 B", "2.0 KiB", "5.0 MiB", "3.0 GiB"]


def test_mask_never_reveals_and_says_not_set() -> None:
    assert mask(None) == "not set" and mask("N0CALL") == "********" and "N0CALL" not in mask("N0CALL")


def test_first_line() -> None:
    assert first_line("one\ntwo") == "one" and first_line("") == "" and len(first_line("x" * 500)) <= 120
```

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_fmt.py -v`
Expected: FAIL (`ImportError`).

Create `hammunition_console/fmt.py`:

```python
"""Text from outside (an engine message, a log line, a unit summary) is data, not
terminal commands: clean() removes every control character so an embedded escape
sequence is shown as inert text and never reaches the terminal as a sequence."""

from __future__ import annotations

import re

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def clean(text: object) -> str:
    return _CONTROL.sub("", str(text).replace("\t", "    "))


def human_size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def mask(value: str | None) -> str:
    return "not set" if value is None else "********"


def first_line(text: str, limit: int = 120) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return clean(line)[:limit]
```

Run: `python3 -m pytest tests/test_fmt.py -v`
Expected: PASS. Note: `\r` (0x0d) is inside `\x0b-\x1f`, so it is removed too.

- [ ] **Step 2: Write the background-work tests, then implement**

Create `tests/test_worker.py`:

```python
import threading
import time

import urwid

from hammunition_console.worker import SyncBackground, ThreadBackground


def test_sync_background_delivers_a_result_or_an_error() -> None:
    got: list[tuple[object, object]] = []
    SyncBackground().submit(lambda: 41 + 1, lambda r, e: got.append((r, e)))
    bad = ValueError("x")

    def boom() -> int:
        raise bad

    SyncBackground().submit(boom, lambda r, e: got.append((r, e)))
    assert got == [(42, None), (None, bad)]


def test_thread_background_runs_off_the_ui_thread_and_delivers_on_the_loop() -> None:
    event_loop = urwid.SelectEventLoop()
    loop = urwid.MainLoop(urwid.SolidFill(" "), event_loop=event_loop)
    bg = ThreadBackground()
    bg.attach(loop)
    main = threading.get_ident()
    seen: dict[str, object] = {}

    def work() -> str:
        seen["worker"] = threading.get_ident()
        time.sleep(0.05)
        return "done"

    def done(result: str | None, error: BaseException | None) -> None:
        seen["delivered_on"] = threading.get_ident()
        seen["result"], seen["error"] = result, error
        raise urwid.ExitMainLoop

    def give_up(*_: object) -> None:
        raise urwid.ExitMainLoop

    bg.submit(work, done)
    event_loop.alarm(5, give_up)  # a hung worker fails the test instead of hanging it
    try:
        event_loop.run()  # the event loop alone: no screen, no terminal needed
    except urwid.ExitMainLoop:
        pass
    assert seen["worker"] != main and seen["delivered_on"] == main
    assert (seen["result"], seen["error"]) == ("done", None)
```

Run: `python3 -m pytest tests/test_worker.py -v`
Expected: FAIL (`ImportError`).

Create `hammunition_console/worker.py`:

```python
"""Run blocking work (the engine's reads) off the UI thread and hand the result
back on it. The urwid loop's own file watching is the hand-off, so nothing but
the main thread ever touches a widget."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

import urwid

T = TypeVar("T")
Done = Callable[[Any, "BaseException | None"], None]


class Background(Protocol):
    def submit(self, call: Callable[[], T], done: Callable[[T | None, BaseException | None], None]) -> None: ...


class SyncBackground:
    """Runs the call at once, in the caller's thread. For tests."""

    def submit(self, call: Callable[[], T], done: Callable[[T | None, BaseException | None], None]) -> None:
        try:
            result = call()
        except Exception as exc:
            done(None, exc)
            return
        done(result, None)


class ThreadBackground:
    def __init__(self) -> None:
        self._loop: urwid.MainLoop | None = None

    def attach(self, loop: urwid.MainLoop) -> None:
        self._loop = loop

    def submit(self, call: Callable[[], T], done: Callable[[T | None, BaseException | None], None]) -> None:
        loop = self._loop
        if loop is None:
            raise RuntimeError("ThreadBackground.attach(loop) was not called")
        outcome: list[tuple[Any, BaseException | None]] = []
        read_fd, write_fd = os.pipe()
        handle: Any = None

        def on_readable() -> None:
            os.read(read_fd, 1)
            loop.remove_watch_file(handle)
            os.close(read_fd)
            os.close(write_fd)
            result, error = outcome[0]
            done(result, error)

        handle = loop.watch_file(read_fd, on_readable)

        def work() -> None:
            try:
                outcome.append((call(), None))
            except Exception as exc:
                outcome.append((None, exc))
            finally:
                os.write(write_fd, b"x")

        threading.Thread(target=work, daemon=True).start()
```

Run: `python3 -m pytest tests/test_worker.py -v`
Expected: PASS (2 passed). A `ResourceWarning` for the pipe must not appear (filterwarnings=error would fail it); the fds are closed in `on_readable`.

- [ ] **Step 3: Context, shared state and base screens: tests first**

Create `tests/test_base_screens.py`:

```python
import urwid

from hammunition_console.context import Shared
from hammunition_console.engine import EngineMissing, EngineRefused, EngineTooOld
from hammunition_console.screens.base import (
    ConfirmScreen, MessageScreen, PromptScreen, Row, Screen, describe_error, text,
)
from tests.helpers import FakeContext, render


def test_shared_header_text_says_unknown_until_known_and_never_a_value() -> None:
    s = Shared()
    assert s.header_text() == "hammunition ? | ? | doctor ? | station ?"
    s.engine_version, s.target, s.doctor, s.station_set = "0.19.0", "Debian 13", (1, 2, 20), True
    assert s.header_text() == "hammunition 0.19.0 | Debian 13 | doctor 1F 2W | station set"
    s.station_set = False
    assert s.header_text().endswith("station not set")


def test_row_cleans_its_text_and_activates_on_enter() -> None:
    row = Row("a\x1b[2Jb", value=7)
    seen: list[object] = []
    urwid.connect_signal(row, "activate", lambda r: seen.append(r.value))
    assert row.keypress((20,), "enter") is None and seen == [7]
    assert row.keypress((20,), "x") == "x"
    assert "\x1b" not in render(urwid.Filler(row, "top"), 20, 3)


def test_a_non_selectable_row_ignores_enter() -> None:
    assert Row("x", selectable=False).keypress((5,), "enter") == "enter"


def test_describe_error() -> None:
    assert "exit 2" in describe_error(EngineRefused(2, "nope\nmore")) and "nope" in describe_error(EngineRefused(2, "nope\nmore"))
    assert "\x1b" not in describe_error(EngineRefused(2, "\x1b[2Jbad"))
    assert describe_error(ValueError("v")) == "ValueError: v"


class Demo(Screen):
    name = "demo"
    title = "Demo"

    def __init__(self, ctx: FakeContext) -> None:
        super().__init__(ctx)
        self.values: list[int] = []

    def redraw(self) -> None:
        self.set_rows([text(f"values: {self.values} state: {self.status.get('n')}")])


def test_load_runs_the_call_and_redraws() -> None:
    ctx = FakeContext()
    demo = Demo(ctx)
    demo.load("n", lambda: 5, lambda v: demo.values.append(v))
    assert demo.values == [5] and demo.status["n"] == "ok"
    assert "values: [5]" in render(demo.widget())


def test_load_records_an_error_and_never_retries() -> None:
    ctx = FakeContext()
    demo = Demo(ctx)
    calls: list[int] = []

    def boom() -> int:
        calls.append(1)
        raise EngineRefused(2, "refused here")

    demo.load("n", boom, lambda v: None)
    assert demo.status["n"] == "error" and "refused here" in demo.errors["n"] and calls == [1]


def test_a_fatal_engine_error_goes_to_the_context_not_the_screen() -> None:
    ctx = FakeContext()
    demo = Demo(ctx)
    demo.load("n", lambda: (_ for _ in ()).throw(EngineMissing("no engine")), lambda v: None)
    assert [type(e) for e in ctx.fatals] == [EngineMissing]
    ctx2 = FakeContext()
    Demo(ctx2).load("n", lambda: (_ for _ in ()).throw(EngineTooOld("old")), lambda v: None)
    assert [type(e) for e in ctx2.fatals] == [EngineTooOld]


def test_prompt_submits_the_trimmed_text_and_pops_first() -> None:
    ctx = FakeContext()
    got: list[str] = []
    prompt = PromptScreen(ctx, "Set", "value: ", got.append)
    edit = prompt._edit
    edit.set_edit_text("  hello  ")
    assert prompt.keypress("enter") is None
    assert got == ["hello"] and ctx.popped == 1


def test_confirm_runs_only_on_capital_r() -> None:
    ctx = FakeContext()
    ran: list[int] = []
    screen = ConfirmScreen(ctx, "Run?", ["this runs a command"], lambda: ran.append(1))
    assert screen.keypress("r") == "r" and ran == []
    assert screen.keypress("R") is None and ran == [1] and ctx.popped == 1
    assert "changes nothing" in render(screen.widget())


def test_message_screen_shows_its_lines() -> None:
    assert "line two" in render(MessageScreen(FakeContext(), "Title", ["line one", "line two"]).widget())
```

Run: `python3 -m pytest tests/test_base_screens.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 4: Implement the context, the base screens and the test doubles**

Create `hammunition_console/context.py`:

```python
"""What a screen may ask of the application, as a Protocol, so screens are
tested against a fake and never import the Shell."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from hammunition_console.config import Config
from hammunition_console.engine import Document
from hammunition_console.worker import Background

if TYPE_CHECKING:
    from hammunition_console.screens.base import Screen


@dataclass
class Shared:
    """What the one-line header shows. Never a station value: only whether it is set."""

    engine_version: str = "?"
    target: str = "?"
    doctor: tuple[int, int, int] | None = None
    station_set: bool | None = None

    def header_text(self) -> str:
        doctor = "?" if self.doctor is None else f"{self.doctor[0]}F {self.doctor[1]}W"
        station = "?" if self.station_set is None else ("set" if self.station_set else "not set")
        return f"hammunition {self.engine_version} | {self.target} | doctor {doctor} | station {station}"


class EngineLike(Protocol):
    binary: str

    def command(self, *words: str) -> list[str]: ...

    def read(self, *words: str, timeout: float = ...) -> Document: ...


class Context(Protocol):
    engine: EngineLike
    config: Config
    bg: Background
    shared: Shared

    def push(self, screen: Screen) -> None: ...
    def pop(self, count: int = 1) -> None: ...
    def replace(self, screen: Screen) -> None: ...
    def open_screen(self, name: str, **kwargs: Any) -> None: ...
    def run_pane(self, argv: Sequence[str], title: str, on_exit: Callable[[int | None], None]) -> None: ...
    def fatal(self, exc: BaseException) -> None: ...
    def refresh_header(self) -> None: ...
    def after(self, seconds: float, fn: Callable[[], None]) -> None: ...
    def save_config(self) -> None: ...


def header_target(target: Mapping[str, Any] | None) -> str:
    """A short target name for the header from a TargetView."""
    if not target:
        return "?"
    pretty = target.get("pretty_name")
    if isinstance(pretty, str) and pretty:
        return pretty
    return f"{target.get('distro', '?')} {target.get('version', '')}".strip()
```

Create `hammunition_console/screens/__init__.py` (empty) and `hammunition_console/screens/base.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar, cast

import urwid

from hammunition_console.context import Context
from hammunition_console.engine import EngineMissing, EngineRefused, EngineTooOld, UnknownSchema
from hammunition_console.fmt import clean

T = TypeVar("T")
FATAL: tuple[type[Exception], ...] = (EngineMissing, EngineTooOld, UnknownSchema)


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, EngineRefused):
        return clean(f"the engine refused (exit {exc.exit_code}): {exc.message.strip()}")
    return clean(f"{type(exc).__name__}: {exc}")


def text(content: str, attr: str | None = None) -> urwid.Widget:
    return urwid.AttrMap(urwid.Text(clean(content)), attr)


class Row(urwid.WidgetWrap):
    """One line of a list. Enter emits `activate` with the row; `value` is the caller's."""

    signals = ["activate"]

    def __init__(self, content: str, value: object = None, *, attr: str | None = None, selectable: bool = True) -> None:
        self.value = value
        self._selectable = selectable
        self._text = urwid.Text(clean(content), wrap="clip")
        super().__init__(urwid.AttrMap(self._text, attr, focus_map="focus"))

    def selectable(self) -> bool:
        return self._selectable

    def set_text(self, content: str) -> None:
        self._text.set_text(clean(content))

    def keypress(self, size: Any, key: str) -> str | None:
        if key == "enter" and self._selectable:
            urwid.emit_signal(self, "activate", self)
            return None
        return key


class Screen:
    """A screen: rows in a list, loaded from the engine, redrawn from state."""

    name = ""
    title = ""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.status: dict[str, str] = {}
        self.errors: dict[str, str] = {}
        self._walker: urwid.SimpleFocusListWalker[urwid.Widget] = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)

    def widget(self) -> urwid.Widget:
        return self._list

    def on_show(self) -> None:
        """Called on first show and again whenever the screen is returned to or refreshed."""

    def on_hide(self) -> None:
        pass

    def keypress(self, key: str) -> str | None:
        """Keys the focused widget did not take. Return None when handled."""
        return key

    def redraw(self) -> None:
        pass

    def set_rows(self, rows: Sequence[urwid.Widget]) -> None:
        position = self._walker.focus if len(self._walker) else 0
        self._walker[:] = list(rows)
        if rows:
            self._walker.set_focus(min(position or 0, len(rows) - 1))

    def focused_value(self) -> object:
        widget = self._walker.focus if len(self._walker) else None
        return getattr(widget, "value", None)

    def load(self, key: str, call: Callable[[], T], done: Callable[[T], None]) -> None:
        self.status[key] = "loading"
        self.errors.pop(key, None)

        def finished(result: T | None, error: BaseException | None) -> None:
            if error is None:
                self.status[key] = "ok"
                done(cast(T, result))
            elif isinstance(error, FATAL):
                self.ctx.fatal(error)
                return
            else:
                self.status[key] = "error"
                self.errors[key] = describe_error(error)
            self.redraw()

        self.ctx.bg.submit(call, finished)


class PromptScreen(Screen):
    """One line of typed input. Enter submits (empty means the caller treats it as cancel)."""

    name = "prompt"

    def __init__(self, ctx: Context, title: str, label: str, on_submit: Callable[[str], None], *, note: str = "") -> None:
        super().__init__(ctx)
        self.title = title
        self._on_submit = on_submit
        self._edit = urwid.Edit(label)
        rows: list[urwid.Widget] = [text(note), self._edit, text("Enter accepts; Esc or b cancels. Nothing is saved by the console itself.")]
        self._walker[:] = rows
        self._walker.set_focus(1)

    def keypress(self, key: str) -> str | None:
        if key == "enter":
            value = self._edit.edit_text.strip()
            self.ctx.pop()
            self._on_submit(value)
            return None
        return key


class ConfirmScreen(Screen):
    """Shows what will run. Capital R runs it in a pane; Back changes nothing."""

    name = "confirm"

    def __init__(self, ctx: Context, title: str, lines: Sequence[str], on_confirm: Callable[[], None]) -> None:
        super().__init__(ctx)
        self.title = title
        self._on_confirm = on_confirm
        self._walker[:] = [text(line) for line in lines] + [
            text(""),
            text("R run this in a terminal pane   b back (changes nothing)", "key"),
        ]

    def keypress(self, key: str) -> str | None:
        if key == "R":
            self.ctx.pop()
            self._on_confirm()
            return None
        return key


class MessageScreen(Screen):
    name = "message"

    def __init__(self, ctx: Context, title: str, lines: Sequence[str]) -> None:
        super().__init__(ctx)
        self.title = title
        self._walker[:] = [text(line) for line in lines]
```

Append to `tests/helpers.py` (add imports `from collections.abc import Callable, Mapping, Sequence`, `from dataclasses import dataclass, field`, and the project imports at the top of the file):

```python
from hammunition_console import guard
from hammunition_console.config import Config
from hammunition_console.context import Shared
from hammunition_console.engine import Document, accept, parse_document
from hammunition_console.verbs import require_json_verb
from hammunition_console.worker import SyncBackground
from tests.fake_hammunition import respond


class FakeEngine:
    """Answers reads from the fixtures through the same mapping the fake script uses."""

    binary = "hammunition"

    def __init__(self, suffix: str = "", station: str = "set") -> None:
        self.suffix, self.station = suffix, station
        self.calls: list[tuple[str, ...]] = []
        self._overrides: dict[tuple[str, ...], Document | BaseException] = {}

    def command(self, *words: str) -> list[str]:
        return [self.binary, *words]

    def set(self, words: Sequence[str], result: Document | BaseException) -> None:
        self._overrides[tuple(words)] = result

    def read(self, *words: str, timeout: float = 0.0) -> Document:
        require_json_verb(words)
        guard.assert_clean_read(words)
        self.calls.append(tuple(words))
        override = self._overrides.get(tuple(words))
        if isinstance(override, BaseException):
            raise override
        if override is not None:
            return override
        answered = respond(["hammunition", *words, "--json"], FIXTURES, self.suffix, self.station)
        assert answered is not None, f"no fixture maps {words}"
        return accept(parse_document(answered[0], answered[1]))


def document(kind: str, body: Mapping[str, Any] | None = None, *, exit_code: int = 0, engine: str = "0.19.0") -> Document:
    """A Document built in a test (for a shape no fixture has)."""
    full = {"schema": "hammunition/1", "kind": kind, "engine": engine, **(body or {})}
    return Document(kind, engine, "hammunition/1", exit_code, full)


@dataclass
class PaneRequest:
    argv: list[str]
    title: str
    on_exit: Callable[[int | None], None]


@dataclass
class FakeContext:
    engine: Any = field(default_factory=FakeEngine)
    config: Config = field(default_factory=Config)
    bg: SyncBackground = field(default_factory=SyncBackground)
    shared: Shared = field(default_factory=Shared)
    pushed: list[Any] = field(default_factory=list)
    replaced: list[Any] = field(default_factory=list)
    opened: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    panes: list[PaneRequest] = field(default_factory=list)
    timers: list[tuple[float, Callable[[], None]]] = field(default_factory=list)
    fatals: list[BaseException] = field(default_factory=list)
    popped: int = 0
    saved: int = 0
    header_refreshes: int = 0

    def push(self, screen: Any) -> None:
        self.pushed.append(screen)
        screen.on_show()

    def pop(self, count: int = 1) -> None:
        self.popped += count

    def replace(self, screen: Any) -> None:
        self.replaced.append(screen)
        screen.on_show()

    def open_screen(self, name: str, **kwargs: Any) -> None:
        self.opened.append((name, kwargs))

    def run_pane(self, argv: Sequence[str], title: str, on_exit: Callable[[int | None], None]) -> None:
        self.panes.append(PaneRequest(guard.checked_argv(argv), title, on_exit))

    def fatal(self, exc: BaseException) -> None:
        self.fatals.append(exc)

    def refresh_header(self) -> None:
        self.header_refreshes += 1

    def after(self, seconds: float, fn: Callable[[], None]) -> None:
        self.timers.append((seconds, fn))

    def save_config(self) -> None:
        self.saved += 1
```

Run: `python3 -m pytest tests/test_base_screens.py tests/test_fmt.py tests/test_worker.py -v`
Expected: PASS. If `FakeEngine` complains it needs the manifest: it uses `respond`, which reads `tests/fixtures/manifest.json` written in Task 2.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add UI foundations: clean text, background work, context, base screens, test doubles"
```
Expected: clean, all pass.


---

### Task 6: The shell: navigation stack, header, keys, size guard, fatal screens, crash log

**Files:**
- Create: `hammunition_console/app.py`
- Test: `tests/test_shell.py`

**Interfaces:**
- Consumes: `context.Shared`, `context.header_target`, `screens.base.Screen/MessageScreen`, `engine.Engine`, `worker.ThreadBackground`, `config.*`, `helpers.FakeEngine`, `helpers.render`.
- Produces: `app.MIN_COLS = 80`, `app.MIN_ROWS = 24`; `app.palette(theme: str) -> list[tuple[str, ...]]`; `app.SizeGuard(inner)`; `app.Shell(engine, config, bg, *, pane_factory, after, registry=None, save=None)` implementing `context.Context` plus `.stack: list[Screen]`, `.root: urwid.Widget`, `.handle_key(key) -> None`, `.hangup() -> NoReturn`; `app.SCREEN_CLASSES: dict[str, str]`; `app.build_registry() -> dict[str, Callable[..., Screen]]`; `app.write_crash_log(exc, directory) -> Path | None`; `app.run(environ) -> int`. Every `Screen.on_show()` must end by calling its own `redraw()` so the loading state shows at once (the Shell calls only `on_show()`).

- [ ] **Step 1: Write the shell's tests (failing first)**

Create `tests/test_shell.py`:

```python
from pathlib import Path
from typing import Any

import pytest
import urwid

from hammunition_console import __version__
from hammunition_console.app import MIN_COLS, MIN_ROWS, SizeGuard, Shell, palette, write_crash_log
from hammunition_console.config import Config
from hammunition_console.engine import EngineMissing, EngineTooOld
from hammunition_console.screens.base import Screen, text
from hammunition_console.worker import SyncBackground
from tests.helpers import FakeEngine, render


class Stub(Screen):
    def __init__(self, ctx: Any, name: str = "stub", **kw: Any) -> None:
        super().__init__(ctx)
        self.name, self.title = name, name.title()
        self.shown = self.hidden = 0
        self.kw = kw
        self.keys: list[str] = []

    def on_show(self) -> None:
        self.shown += 1
        self.redraw()

    def on_hide(self) -> None:
        self.hidden += 1

    def redraw(self) -> None:
        self.set_rows([text(f"{self.name} screen")])

    def keypress(self, key: str) -> str | None:
        self.keys.append(key)
        return None if key == "x" else key


def make(saved: list[Config] | None = None) -> Shell:
    registry: dict[str, Any] = {n: (lambda ctx, n=n, **kw: Stub(ctx, n, **kw)) for n in ("home", "install", "help")}
    sh = Shell(FakeEngine(), Config(), SyncBackground(),
               pane_factory=lambda argv, title, on_exit: Stub(sh, "pane"),
               after=lambda s, f: None, registry=registry,
               save=(saved.append if saved is not None else lambda c: None))
    return sh


def test_open_screen_pushes_and_back_pops_and_reshows() -> None:
    sh = make()
    sh.open_screen("home")
    sh.open_screen("install")
    assert [s.name for s in sh.stack] == ["home", "install"]
    sh.handle_key("b")
    assert [s.name for s in sh.stack] == ["home"] and sh.stack[0].shown == 2  # type: ignore[attr-defined]


def test_pop_can_unwind_several_screens_and_shows_only_the_last() -> None:
    sh = make()
    sh.open_screen("home")
    sh.open_screen("install")
    sh.open_screen("help")
    home: Stub = sh.stack[0]  # type: ignore[assignment]
    install: Stub = sh.stack[1]  # type: ignore[assignment]
    sh.pop(2)
    assert [s.name for s in sh.stack] == ["home"] and home.shown == 2 and install.shown == 1
    sh.pop(5)
    assert len(sh.stack) == 1 and home.shown == 2  # nothing popped, nothing re-shown


def test_back_on_the_root_screen_does_nothing() -> None:
    sh = make()
    sh.open_screen("home")
    sh.handle_key("b")
    sh.handle_key("esc")
    assert len(sh.stack) == 1


def test_open_home_resets_the_stack_and_kwargs_reach_the_factory() -> None:
    sh = make()
    sh.open_screen("home")
    sh.open_screen("install", highlight="station")
    assert sh.stack[-1].kw == {"highlight": "station"}  # type: ignore[attr-defined]
    sh.open_screen("home")
    assert [s.name for s in sh.stack] == ["home"]


def test_last_screen_is_saved_when_a_top_level_screen_opens() -> None:
    saved: list[Config] = []
    sh = make(saved)
    sh.open_screen("install")
    assert sh.config.last_screen == "install" and saved and saved[-1].last_screen == "install"


def test_the_screen_gets_the_first_chance_at_a_key_then_the_globals() -> None:
    sh = make()
    sh.open_screen("home")
    top: Stub = sh.stack[-1]  # type: ignore[assignment]
    sh.handle_key("x")
    assert top.keys == ["x"] and len(sh.stack) == 1
    sh.handle_key("?")
    assert sh.stack[-1].name == "help" and sh.stack[-1].kw == {"about": "home"}  # type: ignore[attr-defined]


def test_q_quits() -> None:
    sh = make()
    sh.open_screen("home")
    with pytest.raises(urwid.ExitMainLoop):
        sh.handle_key("q")


def test_r_refreshes_the_current_screen() -> None:
    sh = make()
    sh.open_screen("home")
    sh.handle_key("r")
    assert sh.stack[-1].shown == 2  # type: ignore[attr-defined]


def test_mouse_events_are_ignored() -> None:
    sh = make()
    sh.open_screen("home")
    sh.handle_key(("mouse press", 1, 2, 3))  # type: ignore[arg-type]


def test_the_header_is_one_line_and_never_a_station_value() -> None:
    sh = make()
    sh.open_screen("home")
    sh.shared.engine_version, sh.shared.target, sh.shared.doctor, sh.shared.station_set = "0.19.0", "Debian 13", (0, 1, 9), True
    sh.refresh_header()
    first = render(sh.root, 80, 24).splitlines()[0]
    assert first == "hammunition 0.19.0 | Debian 13 | doctor 0F 1W | station set"
    assert len(first) <= 80


def test_the_size_guard_asks_for_a_bigger_terminal_below_80x24() -> None:
    sh = make()
    sh.open_screen("home")
    assert f"{MIN_COLS}x{MIN_ROWS}" in render(sh.root, 79, 24)
    assert f"{MIN_COLS}x{MIN_ROWS}" in render(sh.root, 80, 23)
    assert f"{MIN_COLS}x{MIN_ROWS}" not in render(sh.root, 80, 24)
    assert isinstance(sh.root, SizeGuard) and sh.root.keypress((79, 24), "x") == "x"


@pytest.mark.parametrize("exc,needle", [(EngineMissing("hammunition was not found on PATH"), "not found on PATH"),
                                        (EngineTooOld("Hammunition 0.18.9 is older than 0.19.0"), "0.18.9")])
def test_a_fatal_engine_error_replaces_everything_with_one_screen(exc: Exception, needle: str) -> None:
    sh = make()
    sh.open_screen("home")
    sh.open_screen("install")
    sh.fatal(exc)
    assert len(sh.stack) == 1 and needle in render(sh.root, 100, 24)
    assert "q to quit" in render(sh.root, 100, 24)


def test_a_pane_is_pushed_and_hangup_notifies_every_screen() -> None:
    sh = make()
    sh.open_screen("home")
    called: list[str] = []
    for s in sh.stack:
        s.on_hangup = lambda: called.append("h")  # type: ignore[attr-defined]
    sh.run_pane(["hammunition", "install", "station"], "install station", lambda code: None)
    assert sh.stack[-1].name == "pane"
    with pytest.raises(urwid.ExitMainLoop):
        sh.hangup()
    assert called == ["h"]


def test_palettes_cover_every_attribute_the_screens_use() -> None:
    needed = {"header", "footer", "title", "focus", "key", "warn", "fail", "ok", "dim"}
    for theme in ("dark", "light"):
        assert needed <= {entry[0] for entry in palette(theme)}


def test_crash_log_has_the_exception_type_and_frames_but_no_message(tmp_path: Path) -> None:
    sentinel = "ZZ9SENTINEL"

    def inner() -> None:
        raise RuntimeError(f"callsign {sentinel}")

    try:
        inner()
    except RuntimeError as exc:
        path = write_crash_log(exc, tmp_path / "cfg")
    assert path is not None
    content = path.read_text()
    assert "RuntimeError" in content and "inner" in content and __version__ in content
    assert sentinel not in content
    assert oct(path.stat().st_mode & 0o777) == "0o600"
```

- [ ] **Step 2: Run it; confirm it fails**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_shell.py -v`
Expected: FAIL (`ImportError: cannot import name 'app'`).

- [ ] **Step 3: Implement the shell**

Create `hammunition_console/app.py`:

```python
"""The application shell: the screen stack, the one-line header, global keys,
the size guard, fatal-error screens, the crash log and the main loop."""

from __future__ import annotations

import importlib
import os
import signal
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

import urwid

from hammunition_console import __version__
from hammunition_console import config as config_mod
from hammunition_console.config import SCREENS, Config
from hammunition_console.context import EngineLike, Shared
from hammunition_console.engine import Engine
from hammunition_console.fmt import clean
from hammunition_console.screens.base import MessageScreen, Screen
from hammunition_console.worker import Background, ThreadBackground

MIN_COLS, MIN_ROWS = 80, 24
FOOTER = "b back   ? help   q quit   r refresh   Enter open"
SCREEN_CLASSES = {
    "home": "hammunition_console.screens.home:HomeScreen",
    "install": "hammunition_console.screens.install:InstallScreen",
    "station": "hammunition_console.screens.station:StationScreen",
    "logs": "hammunition_console.screens.logs:LogsScreen",
    "update": "hammunition_console.screens.update:UpdateScreen",
    "help": "hammunition_console.screens.help:HelpScreen",
}


def palette(theme: str) -> list[tuple[str, ...]]:
    if theme == "light":
        return [("header", "white", "dark blue"), ("footer", "black", "light gray"),
                ("title", "black,bold", "light gray"), ("focus", "white", "dark blue"),
                ("key", "dark blue,bold", "default"), ("warn", "brown", "default"),
                ("fail", "dark red", "default"), ("ok", "dark green", "default"),
                ("dim", "dark gray", "default")]
    return [("header", "white", "dark blue"), ("footer", "black", "light gray"),
            ("title", "white,bold", "dark gray"), ("focus", "black", "light cyan"),
            ("key", "yellow", "default"), ("warn", "yellow", "default"),
            ("fail", "light red", "default"), ("ok", "light green", "default"),
            ("dim", "dark gray", "default")]


class SizeGuard(urwid.WidgetWrap):
    """Draws a one-line request instead of the screen when the terminal is under 80x24."""

    def __init__(self, inner: urwid.Widget) -> None:
        self._inner = inner
        super().__init__(inner)

    @staticmethod
    def _too_small(size: tuple[int, int]) -> bool:
        return size[0] < MIN_COLS or size[1] < MIN_ROWS

    def render(self, size: Any, focus: bool = False) -> Any:
        if self._too_small(size):
            message = f"Please enlarge the terminal to at least {MIN_COLS}x{MIN_ROWS} (it is {size[0]}x{size[1]})."
            return urwid.Filler(urwid.Text(message), "top").render(size, focus)
        return self._inner.render(size, focus)

    def keypress(self, size: Any, key: str) -> str | None:
        return key if self._too_small(size) else self._inner.keypress(size, key)


class Shell:
    def __init__(
        self,
        engine: EngineLike,
        config: Config,
        bg: Background,
        *,
        pane_factory: Callable[[Sequence[str], str, Callable[[int | None], None]], Screen],
        after: Callable[[float, Callable[[], None]], None],
        registry: Mapping[str, Callable[..., Screen]] | None = None,
        save: Callable[[Config], Any] | None = None,
    ) -> None:
        self.engine = engine
        self.config = config
        self.bg = bg
        self.shared = Shared()
        self.stack: list[Screen] = []
        self.registry = dict(registry or {})
        self._pane_factory = pane_factory
        self._after = after
        self._save = save or (lambda cfg: config_mod.save(cfg))
        self._header = urwid.Text("", wrap="clip")
        self._frame = urwid.Frame(
            urwid.SolidFill(" "),
            header=urwid.AttrMap(self._header, "header"),
            footer=urwid.AttrMap(urwid.Text(FOOTER, wrap="clip"), "footer"),
        )
        self.root: urwid.Widget = SizeGuard(self._frame)
        self.refresh_header()

    # -- Context ---------------------------------------------------------
    def _show(self, screen: Screen) -> None:
        title = urwid.AttrMap(urwid.Text(" " + clean(screen.title), wrap="clip"), "title")
        self._frame.body = urwid.Frame(screen.widget(), header=title)
        screen.on_show()

    def push(self, screen: Screen) -> None:
        self.stack.append(screen)
        self._show(screen)

    def pop(self, count: int = 1) -> None:
        popped = False
        for _ in range(count):
            if len(self.stack) > 1:
                self.stack.pop().on_hide()
                popped = True
        if popped:
            self._show(self.stack[-1])

    def replace(self, screen: Screen) -> None:
        if self.stack:
            self.stack.pop().on_hide()
        self.push(screen)

    def open_screen(self, name: str, **kwargs: Any) -> None:
        if name == "home":
            for screen in self.stack:
                screen.on_hide()
            self.stack.clear()
        screen_class = self.registry[name]
        screen = screen_class(self, **kwargs)
        if name in SCREENS:
            self.config.last_screen = name
            self.save_config()
        self.push(screen)

    def run_pane(self, argv: Sequence[str], title: str, on_exit: Callable[[int | None], None]) -> None:
        self.push(self._pane_factory(argv, title, on_exit))

    def fatal(self, exc: BaseException) -> None:
        for screen in self.stack:
            screen.on_hide()
        self.stack.clear()
        self.push(MessageScreen(self, "Cannot continue", [str(exc), "", "Press q to quit."]))

    def refresh_header(self) -> None:
        self._header.set_text(clean(self.shared.header_text()))

    def after(self, seconds: float, fn: Callable[[], None]) -> None:
        self._after(seconds, fn)

    def save_config(self) -> None:
        self._save(self.config)

    # -- keys ------------------------------------------------------------
    def handle_key(self, key: Any) -> None:
        if not isinstance(key, str) or not self.stack:
            return
        top = self.stack[-1]
        if top.keypress(key) is None:
            return
        if key == "q":
            raise urwid.ExitMainLoop
        if key in ("b", "esc"):
            self.pop()
        elif key == "?":
            self.open_screen("help", about=top.name)
        elif key == "r":
            top.on_show()

    def hangup(self) -> NoReturn:
        for screen in self.stack:
            getattr(screen, "on_hangup", lambda: None)()
        raise urwid.ExitMainLoop


def _lazy(path: str) -> Callable[..., Screen]:
    def factory(ctx: Any, **kwargs: Any) -> Screen:
        module, _, cls = path.partition(":")
        screen: Screen = getattr(importlib.import_module(module), cls)(ctx, **kwargs)
        return screen

    return factory


def build_registry() -> dict[str, Callable[..., Screen]]:
    return {name: _lazy(path) for name, path in SCREEN_CLASSES.items()}


def write_crash_log(exc: BaseException, directory: Path) -> Path | None:
    """The exception's type and its frames (file:line in function). Never its message
    and never source lines: a message can carry a station value or plan content."""
    frames = traceback.extract_tb(exc.__traceback__)
    lines = [f"hammunition-console {__version__}", f"exception: {type(exc).__name__}",
             "frames (file:line in function; no message, no source):"]
    lines += [f"  {Path(f.filename).name}:{f.lineno} in {f.name}" for f in frames]
    path = directory / "crash.log"
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        return None
    return path


def run(environ: Mapping[str, str]) -> int:
    cfg = config_mod.load(config_mod.config_path(environ))
    engine = Engine(environ=environ)
    bg = ThreadBackground()
    loop_box: list[urwid.MainLoop] = []

    def after(seconds: float, fn: Callable[[], None]) -> None:
        loop_box[0].set_alarm_in(seconds, lambda *_: fn())

    def pane_factory(argv: Sequence[str], title: str, on_exit: Callable[[int | None], None]) -> Screen:
        from hammunition_console.pane import PaneScreen

        return PaneScreen(shell, argv, title, on_exit, loop=loop_box[0], environ=environ)

    shell = Shell(engine, cfg, bg, pane_factory=pane_factory, after=after, registry=build_registry(),
                  save=lambda c: config_mod.save(c, config_mod.config_path(environ)))
    loop = urwid.MainLoop(shell.root, palette(cfg.theme), unhandled_input=shell.handle_key)
    loop_box.append(loop)
    bg.attach(loop)
    signal.signal(signal.SIGHUP, lambda *_: shell.hangup())
    shell.open_screen("home")
    if cfg.last_screen != "home":
        shell.open_screen(cfg.last_screen)
    try:
        loop.run()
    except Exception as exc:
        path = write_crash_log(exc, config_mod.config_dir(environ))
        where = f" Details (no message text) are in {path}." if path else ""
        print(f"hammunition-console crashed: {type(exc).__name__}.{where}", file=sys.stderr)
        return 1
    return 0
```


- [ ] **Step 4: Run it; passes; commit**

Run: `python3 -m pytest tests/test_shell.py -v`
Expected: PASS (all). If the header test's first line differs, `Frame` rendered the header at row 0; read `render(sh.root, 80, 24)` and adjust only if urwid adds padding (it does not for a Text header).

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the shell: stack, header, keys, size guard, fatal screens, crash log"
```
Expected: clean, all pass.

---

### Task 7: The pane: a real pty child, its exit status, and the consent environment

The pane runs the real command inside `urwid.Terminal`. A tiny stdlib `runner.py` sits between the terminal and the command: it ignores Ctrl-C itself (so the keystroke reaches the child, which is in the same foreground group, and the console never kills it), runs the command with the tty inherited, and writes the child's exit status to a file, so the console never depends on how any urwid version reports a child's death. The tests drive it in a real pseudo-terminal against the fake `hammunition`.

**Files:**
- Create: `hammunition_console/runner.py`, `hammunition_console/pane.py`, `tests/pty_driver.py`, `tests/pane_harness.py`
- Test: `tests/test_runner.py`, `tests/test_pane_spec.py`, `tests/test_pane_pty.py`

**Interfaces:**
- Consumes: `guard.checked_argv`, `guard.scrubbed_environ`, `screens.base.Screen`, `helpers.make_shim`, `helpers.FakeContext`.
- Produces: `runner.main(argv: list[str]) -> int` (usage: `runner.py STATUS_FILE -- COMMAND...`); `pane.RUNNER: Path`; `pane.PaneSpec(command: list[str], env: dict[str, str])`; `pane.build_pane_spec(argv, status_path, environ) -> PaneSpec`; `pane.read_exit_status(path) -> int | None`; `pane.PaneScreen(ctx, argv, title, on_exit, *, loop, environ=None)` with `.finished: bool`, `.exit_code: int | None`, `.finish()`, `.on_hangup()`; `tests.pty_driver.PtyProcess(argv, env, *, rows=30, cols=100)` with `.send(text)`, `.expect(needle, timeout=20.0)`, `.wait(timeout=15.0) -> int`, `.close()`.

- [ ] **Step 1: Write the runner's tests (failing first)**

Create `tests/test_runner.py`:

```python
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from hammunition_console.pane import RUNNER


def run_runner(status: Path, *command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(RUNNER), str(status), "--", *command],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)


def test_it_reports_the_childs_exit_code_in_the_file_and_as_its_own(tmp_path: Path) -> None:
    status = tmp_path / "status"
    done = run_runner(status, sys.executable, "-c", "import sys; sys.exit(7)")
    assert done.returncode == 7 and status.read_text().strip() == "7"


def test_a_missing_command_is_127(tmp_path: Path) -> None:
    status = tmp_path / "status"
    done = run_runner(status, "no-such-command-xyz")
    assert done.returncode == 127 and status.read_text().strip() == "127"
    assert "not found" in done.stderr


def test_usage_error_is_2(tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, str(RUNNER), str(tmp_path / "s")], capture_output=True, text=True)
    assert done.returncode == 2


def test_ctrl_c_reaches_the_child_and_does_not_kill_the_runner(tmp_path: Path) -> None:
    """SIGINT goes to the whole foreground group, as a terminal's Ctrl-C does. The runner must
    ignore it (its handler is a no-op) and report what the child did with it."""
    status = tmp_path / "status"
    child = ("import signal, sys, time\n"
             "signal.signal(signal.SIGINT, lambda *a: sys.exit(5))\n"
             "print('ready', flush=True)\n"
             "time.sleep(30)\n")
    proc = subprocess.Popen([sys.executable, str(RUNNER), str(status), "--", sys.executable, "-c", child],
                            stdout=subprocess.PIPE, text=True, start_new_session=True)
    assert proc.stdout is not None and proc.stdout.readline().strip() == "ready"
    os.killpg(proc.pid, signal.SIGINT)
    deadline = time.monotonic() + 10
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert proc.poll() == 5 and status.read_text().strip() == "5"


def test_a_child_killed_by_a_signal_is_reported_as_128_plus_the_signal(tmp_path: Path) -> None:
    status = tmp_path / "status"
    done = run_runner(status, sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)")
    assert done.returncode == 128 + signal.SIGTERM
```

- [ ] **Step 2: Run it; confirm it fails; implement the runner and the pure parts of the pane**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_runner.py -v`
Expected: FAIL (`ImportError: cannot import name 'RUNNER'`).

Create `hammunition_console/runner.py`:

```python
"""Run one command with this process's terminal, and record how it ended.

    runner.py STATUS_FILE -- COMMAND...

Started by the pane inside urwid.Terminal. It exists for two reasons: the
console must learn the child's exit status without relying on how any urwid
version reports a child's death, and Ctrl-C must reach the child, not kill the
thing watching it. A *handler* (not SIG_IGN) is installed for SIGINT: handlers
are reset to the default across exec, so the child still gets the default
action, while this process just waits.
"""

from __future__ import annotations

import signal
import subprocess
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "--":
        print("usage: runner.py STATUS_FILE -- COMMAND...", file=sys.stderr)
        return 2
    status_path, command = argv[0], argv[2:]
    signal.signal(signal.SIGINT, lambda *_: None)
    try:
        code = subprocess.Popen(command).wait()
    except FileNotFoundError:
        print(f"{command[0]}: command not found", file=sys.stderr)
        code = 127
    except OSError as exc:
        print(f"{command[0]}: cannot run ({exc.strerror})", file=sys.stderr)
        code = 126
    if code < 0:
        code = 128 + (-code)
    try:
        with open(status_path, "w", encoding="utf-8") as handle:
            handle.write(f"{code}\n")
    except OSError:
        pass
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Create `tests/test_pane_spec.py`:

```python
import sys
from pathlib import Path

import pytest

from hammunition_console.guard import Refused
from hammunition_console.pane import RUNNER, build_pane_spec, read_exit_status


def test_the_command_is_the_runner_around_the_checked_argv() -> None:
    spec = build_pane_spec(["hammunition", "install", "station"], "/tmp/s/status", {"PATH": "/bin", "TERM": "xterm"})
    assert spec.command == [sys.executable, str(RUNNER), "/tmp/s/status", "--", "hammunition", "install", "station"]
    assert RUNNER.exists()


def test_the_consent_environment_never_reaches_the_child() -> None:
    env = {"PATH": "/bin", "HAMMUNITION_ACCEPT_RF_RESEARCH": "1", "X_CONSENT": "1"}
    spec = build_pane_spec(["hammunition", "install", "station"], "/s", env)
    assert "HAMMUNITION_ACCEPT_RF_RESEARCH" not in spec.env and "X_CONSENT" not in spec.env
    assert spec.env["PATH"] == "/bin"


def test_term_defaults_when_absent() -> None:
    assert build_pane_spec(["hammunition", "install", "x"], "/s", {}).env["TERM"] == "xterm-256color"


@pytest.mark.parametrize("bad", [["hammunition", "install", "x", "--yes"], ["hammunition", "install", "-y"],
                                 ["hammunition", "services", "start", "gpsd"], ["rm", "-rf", "/"]])
def test_a_command_the_guard_refuses_never_becomes_a_pane(bad: list[str]) -> None:
    with pytest.raises(Refused):
        build_pane_spec(bad, "/s", {})


def test_read_exit_status(tmp_path: Path) -> None:
    ok = tmp_path / "a"
    ok.write_text("3\n")
    assert read_exit_status(str(ok)) == 3
    assert read_exit_status(str(tmp_path / "missing")) is None
    bad = tmp_path / "b"
    bad.write_text("three")
    assert read_exit_status(str(bad)) is None
```

Create `hammunition_console/pane.py`:

```python
"""An embedded terminal that runs the real engine command, so sudo's password
prompt, the group choice and any consent `yes` reach the engine untouched, typed
by a person. The console does not read the pane's input, echo it or inject keys."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import urwid

from hammunition_console import guard
from hammunition_console.context import Context
from hammunition_console.screens.base import Screen

RUNNER = Path(__file__).with_name("runner.py")


@dataclass(frozen=True)
class PaneSpec:
    command: list[str]
    env: dict[str, str]


def build_pane_spec(argv: Sequence[str], status_path: str, environ: Mapping[str, str]) -> PaneSpec:
    checked = guard.checked_argv(argv)
    env = guard.scrubbed_environ(environ)
    env.setdefault("TERM", "xterm-256color")
    return PaneSpec([sys.executable, str(RUNNER), status_path, "--", *checked], env)


def read_exit_status(path: str) -> int | None:
    try:
        return int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


class _PaneFrame(urwid.WidgetWrap):
    """All keys go to the program until it exits; then Enter continues."""

    def __init__(self, owner: PaneScreen, inner: urwid.Widget) -> None:
        self._owner = owner
        super().__init__(inner)

    def keypress(self, size: Any, key: str) -> str | None:
        if self._owner.finished:
            if key == "enter":
                self._owner.finish()
                return None
            return key
        return super().keypress(size, key)  # type: ignore[no-any-return]


class PaneScreen(Screen):
    name = "pane"

    def __init__(
        self,
        ctx: Context,
        argv: Sequence[str],
        title: str,
        on_exit: Callable[[int | None], None],
        *,
        loop: urwid.MainLoop,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(ctx)
        self.title = title
        self.finished = False
        self.exit_code: int | None = None
        self._on_exit = on_exit
        self._dir = tempfile.mkdtemp(prefix="hammunition-console-")
        self._status = os.path.join(self._dir, "status")
        spec = build_pane_spec(argv, self._status, os.environ if environ is None else environ)
        self._banner = urwid.Text("Every key goes to the program until it exits; Ctrl-C reaches it, not the console.")
        self._terminal = urwid.Terminal(spec.command, env=spec.env, main_loop=loop)
        urwid.connect_signal(self._terminal, "closed", self._closed)
        self._frame = _PaneFrame(self, urwid.Frame(self._terminal, footer=urwid.AttrMap(self._banner, "footer")))

    def widget(self) -> urwid.Widget:
        return self._frame

    def _closed(self, *_: object) -> None:
        self.exit_code = read_exit_status(self._status)
        self.finished = True
        said = f"exit code {self.exit_code}" if self.exit_code is not None else "no exit code (the program was cut off)"
        self._banner.set_text(f"Finished with {said}. Press Enter to continue.")

    def finish(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)
        self._on_exit(self.exit_code)

    def on_hangup(self) -> None:
        """The console's own terminal closed: close the pty, as the terminal closing would."""
        terminate = getattr(self._terminal, "terminate", None)
        if callable(terminate):
            terminate()
```

The `# type: ignore[no-any-return]` on `super().keypress` is only needed when urwid is untyped; remove it if mypy reports it unused.

Run: `python3 -m pytest tests/test_runner.py tests/test_pane_spec.py -v`
Expected: PASS (all 10).

- [ ] **Step 3: The pty driver, a one-pane harness, and the real-terminal test**

Create `tests/pty_driver.py`:

```python
"""Drive a program in a real pseudo-terminal and wait for text on its screen.

urwid redraws with cursor movement, so spaces and the order of partial updates are
not reliable: matching ignores all whitespace and escape sequences, and each
expect() looks only past what the previous one matched."""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import termios
import time
from collections.abc import Mapping, Sequence

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[=>78]")


def squash(text: str) -> str:
    return re.sub(r"\s+", "", ANSI.sub("", text))


class PtyProcess:
    def __init__(self, argv: Sequence[str], env: Mapping[str, str], *, rows: int = 30, cols: int = 100) -> None:
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.proc = subprocess.Popen(list(argv), stdin=slave, stdout=slave, stderr=slave, env=dict(env),
                                     start_new_session=True, close_fds=True)
        os.close(slave)
        self.raw = ""
        self._consumed = 0

    def send(self, text: str) -> None:
        os.write(self.master, text.encode())

    def _pump(self, timeout: float) -> None:
        ready, _, _ = select.select([self.master], [], [], timeout)
        if not ready:
            return
        try:
            data = os.read(self.master, 65536)
        except OSError:  # EIO once the child side closes
            return
        self.raw += data.decode("utf-8", "replace")

    def expect(self, needle: str, timeout: float = 20.0) -> None:
        want = squash(needle)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            seen = squash(self.raw)
            at = seen.find(want, self._consumed)
            if at >= 0:
                self._consumed = at + len(want)
                return
            self._pump(0.2)
        tail = ANSI.sub("", self.raw)[-1500:]
        raise AssertionError(f"timed out waiting for {needle!r}; last output:\n{tail}")

    def wait(self, timeout: float = 15.0) -> int:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            code = self.proc.poll()
            if code is not None:
                return code
            self._pump(0.1)
        raise AssertionError(f"process did not exit; last output:\n{ANSI.sub('', self.raw)[-1500:]}")

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        os.close(self.master)
```

Create `tests/pane_harness.py`:

```python
"""One PaneScreen in a real urwid loop, for tests/test_pane_pty.py only.

Usage: python -m tests.pane_harness -- ARGV...   Writes the pane's exit code to
the file named by HARNESS_RESULT when the operator presses Enter after it ends."""

from __future__ import annotations

import os
import sys

import urwid

from hammunition_console.pane import PaneScreen
from tests.helpers import FakeContext


def main(argv: list[str]) -> int:
    result_path = os.environ["HARNESS_RESULT"]
    ctx = FakeContext()
    box: list[urwid.MainLoop] = []

    def on_exit(code: int | None) -> None:
        with open(result_path, "w", encoding="utf-8") as handle:
            handle.write(f"{code}\n")
        raise urwid.ExitMainLoop

    loop = urwid.MainLoop(urwid.SolidFill(" "))
    box.append(loop)
    pane = PaneScreen(ctx, argv, "harness", on_exit, loop=loop)
    loop.widget = pane.widget()
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:]))
```

Create `tests/test_pane_pty.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import make_shim
from tests.pty_driver import PtyProcess

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.pty


def env_for(tmp: Path) -> dict[str, str]:
    return {
        "PATH": f"{make_shim(tmp)}:{os.environ['PATH']}",
        "HOME": str(tmp), "TERM": "xterm-256color", "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_HAMMUNITION_LOG": str(tmp / "fake.log"), "HARNESS_RESULT": str(tmp / "result"),
        "HAMMUNITION_ACCEPT_RF_RESEARCH": "1",  # a canary: it must not reach the child
    }


def harness(env: dict[str, str]) -> PtyProcess:
    return PtyProcess([sys.executable, "-m", "tests.pane_harness", "--", "hammunition", "install", "station"], env)


def test_a_person_typing_yes_into_a_real_tty_is_what_confirms(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    proc = harness(env)
    try:
        proc.expect("continue:")
        proc.send("yes\r")
        proc.expect("Finished with exit code 0")
        proc.send("\r")
        assert proc.wait() == 0
    finally:
        proc.close()
    assert (tmp_path / "result").read_text().strip() == "0"
    entry = json.loads((tmp_path / "fake.log").read_text().splitlines()[0])
    assert entry["argv"] == ["install", "station"] and entry["tty"] is True
    assert "HAMMUNITION_ACCEPT_RF_RESEARCH" not in entry["env"], "the consent variable leaked into the pane's child"


def test_anything_but_yes_is_declined_and_the_exit_code_is_the_engines(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    proc = harness(env)
    try:
        proc.expect("continue:")
        proc.send("no\r")
        proc.expect("Finished with exit code 3")
        proc.send("\r")
        proc.wait()
    finally:
        proc.close()
    assert (tmp_path / "result").read_text().strip() == "3"


def test_the_same_fake_refuses_without_a_tty_so_the_tty_above_was_real(tmp_path: Path) -> None:
    shim = make_shim(tmp_path)
    done = subprocess.run(["hammunition", "install", "station"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, env={**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"})
    assert done.returncode == 3 and "no interactive terminal" in done.stderr
```

- [ ] **Step 4: Run the pty tests; fix what a real urwid forces**

Run: `python3 -m pytest tests/test_pane_pty.py -v`
Expected: PASS (3 passed, a few seconds each). This is the first time `urwid.Terminal` runs. If `expect("continue:")` times out, the failure message prints the last screen output: read it. Two likely adjustments, both in `pane.py` or the harness and neither in a test's intent: (a) `urwid.Terminal(...)` may need the loop's widget set before its first render (the harness sets `loop.widget` after construction, which is what the code does); (b) if `closed` fires but `exit_code` is `None`, the runner's status file path or the `-P` flag is wrong: run `python3 tests/pane_harness.py` is not the way; instead `echo` the `PaneSpec.command` and run it by hand in a terminal. Do not make `read_exit_status` guess.

- [ ] **Step 5: Falsify the pane's tty and its env scrub, then commit**

Falsify the scrub: in `hammunition_console/pane.py` change `env = guard.scrubbed_environ(environ)` in `build_pane_spec` to `env = dict(environ)`. Run: `python3 -m pytest tests/test_pane_spec.py tests/test_pane_pty.py -v`
Expected: FAIL in `test_the_consent_environment_never_reaches_the_child` and in `test_a_person_typing_yes_...` with "the consent variable leaked into the pane's child". Restore the line; re-run: PASS.

Falsify the tty claim: in `tests/fake_hammunition.py` temporarily make `_ask` skip the `isatty` check; the third test `test_the_same_fake_refuses_without_a_tty...` goes red. Restore.

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the pane: a real pty child, its recorded exit status, and the scrubbed environment"
```
Expected: clean, all pass.

---

### Task 8: Home

Home shows the doctor summary, whether the station is set (never its values), the most recent run, and how many units are behind their pin; Enter on the doctor line lists the checks with their `fix` text, which is text and is never run (the engine's `fix` is prose, spec 4.1).

**Files:**
- Create: `hammunition_console/screens/home.py`
- Test: `tests/test_home.py`

**Interfaces:**
- Consumes: `screens.base.{Screen, Row, text, describe_error}`, `context.header_target`, `fmt.first_line`, `FakeContext/FakeEngine/document/render/load`.
- Produces: `home.READS: dict[str, tuple[str, ...]]`; `home.MENU: tuple[tuple[str, str, str], ...]`; `home.doctor_text/station_text/last_run_text/behind_text(doc_or_none, error_or_none) -> str`; `home.HomeScreen(ctx)` (`name = "home"`, `.docs: dict[str, Document]`, `._walkthrough_rows() -> list[urwid.Widget]` returning `[]` until Task 15); `home.ChecksScreen(ctx, checks: Sequence[Mapping[str, Any]])`.

- [ ] **Step 1: Write the tests (failing first)**

Create `tests/test_home.py`:

```python
from typing import Any

import pytest

from hammunition_console.engine import EngineMissing, EngineRefused
from hammunition_console.screens.home import ChecksScreen, HomeScreen
from tests.helpers import FakeContext, FakeEngine, document, load, render


def shown(ctx: FakeContext) -> str:
    home = HomeScreen(ctx)
    home.on_show()
    return render(home.widget(), 100, 30)


def test_home_summarises_each_document() -> None:
    ctx = FakeContext()
    out = shown(ctx)
    d = load("doctor")
    assert f"Doctor: {d['fails']} fail, {d['warns']} warn, {d['healthy']} healthy" in out
    assert "Station: set" in out
    run = load("logs")["runs"][0]
    assert f"Last run: {run['command']} - {run['result']}" in out
    update = load("update-all")
    assert f"Behind the pin: {update['counts']['behind_pin']}" in out
    assert "retired in the catalog: 1" in out


def test_home_never_prints_a_station_value() -> None:
    out = shown(FakeContext())
    station = load("station-set")
    for value in (station["callsign"], station["grid_square"], station["node_alias"]):
        assert value not in out


def test_the_shared_header_is_fed_from_the_documents() -> None:
    ctx = FakeContext()
    shown(ctx)
    assert ctx.shared.engine_version == load("status")["engine"]
    assert ctx.shared.station_set is True
    d = load("doctor")
    assert ctx.shared.doctor == (d["fails"], d["warns"], d["healthy"])
    assert ctx.header_refreshes > 0 and ctx.shared.target != "?"


def test_a_station_that_is_not_set_says_so() -> None:
    ctx = FakeContext(engine=FakeEngine(station="none"))
    assert "Station: not set" in shown(ctx)
    assert ctx.shared.station_set is False


def test_an_engine_without_e2_refusing_update_leaves_the_rest_working() -> None:
    ctx = FakeContext(engine=FakeEngine(suffix="-without"))
    out = shown(ctx)
    assert "Behind the pin: unknown" in out and "the engine refused (exit 2)" in out
    assert "Doctor:" in out and "Station: set" in out


def test_each_read_fails_alone() -> None:
    engine = FakeEngine()
    engine.set(("station", "show"), ValueError("boom"))
    out = shown(FakeContext(engine=engine))
    assert "Station: unknown" in out and "ValueError: boom" in out and "Doctor: " in out


def test_a_fatal_engine_error_is_handed_to_the_shell() -> None:
    engine = FakeEngine()
    engine.set(("status",), EngineMissing("no engine"))
    ctx = FakeContext(engine=engine)
    HomeScreen(ctx).on_show()
    assert [type(e) for e in ctx.fatals] == [EngineMissing]


def test_missing_fields_and_an_empty_log_never_crash_or_say_none() -> None:
    engine = FakeEngine()
    engine.set(("doctor",), document("doctor", {"checks": []}))
    engine.set(("logs",), document("logs", {"directory": "/x", "runs": []}))
    engine.set(("update",), document("update", {"rows": [], "counts": {}}))
    out = shown(FakeContext(engine=engine))
    assert "Doctor: ? fail, ? warn, ? healthy" in out and "Last run: no runs yet" in out
    assert "Behind the pin: ?" in out and "None" not in out


def test_engine_text_is_cleaned_of_control_sequences() -> None:
    engine = FakeEngine()
    engine.set(("doctor",), EngineRefused(2, "\x1b[2Jmalicious"))
    out = shown(FakeContext(engine=engine))
    assert "\x1b" not in out and "malicious" in out


def test_digits_open_the_screens_in_order() -> None:
    ctx = FakeContext()
    home = HomeScreen(ctx)
    home.on_show()
    for digit, name in zip("12345", ("install", "station", "logs", "update", "help")):
        assert home.keypress(digit) is None
        assert ctx.opened[-1] == (name, {})
    assert home.keypress("9") == "9"


def test_enter_on_a_menu_row_opens_it() -> None:
    ctx = FakeContext()
    home = HomeScreen(ctx)
    home.on_show()
    row = next(r for r in home._walker if getattr(r, "value", None) == "logs")
    row.keypress((80,), "enter")
    assert ctx.opened[-1] == ("logs", {})


def checks(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return list(items)


def test_the_checks_list_shows_the_fix_text_and_never_runs_it() -> None:
    ctx = FakeContext()
    engine = FakeEngine()
    engine.set(("doctor",), document("doctor", {"fails": 1, "warns": 0, "healthy": 1, "checks": checks(
        {"name": "udev", "status": "fail", "detail": "rules missing\x1b[2J", "fix": "hammunition hardware apply"},
        {"name": "disk", "status": "ok", "detail": "plenty", "fix": None})}))
    ctx.engine = engine
    home = HomeScreen(ctx)
    home.on_show()
    row = next(r for r in home._walker if getattr(r, "value", None) == "doctor")
    row.keypress((80,), "enter")
    screen = ctx.pushed[-1]
    assert isinstance(screen, ChecksScreen)
    out = render(screen.widget(), 100, 20)
    assert "fix: hammunition hardware apply" in out and "rules missing" in out and "\x1b" not in out
    assert "never runs" in out and "None" not in out
    assert ctx.panes == []


@pytest.mark.parametrize("state", ["fail", "warn", "ok", "info", "future-state"])
def test_every_check_state_renders(state: str) -> None:
    screen = ChecksScreen(FakeContext(), [{"name": "n", "status": state, "detail": "d", "fix": None}])
    assert f"[{state}] n: d" in render(screen.widget(), 100, 10)
```

- [ ] **Step 2: Run it; confirm it fails; implement**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_home.py -v`
Expected: FAIL (`ModuleNotFoundError: ...screens.home`).

Create `hammunition_console/screens/home.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import urwid

from hammunition_console.context import Context, header_target
from hammunition_console.engine import Document
from hammunition_console.fmt import first_line
from hammunition_console.screens.base import Row, Screen, text

READS: dict[str, tuple[str, ...]] = {
    "status": ("status",),
    "doctor": ("doctor",),
    "station": ("station", "show"),
    "logs": ("logs",),
    "update": ("update",),
    "list": ("list",),  # the first-run checklist reads the starter profile's installed state from it
}
MENU = (
    ("install", "Install", "pick a profile or unit, read the plan, run it"),
    ("station", "Station", "your callsign, grid square, maps and rig"),
    ("logs", "Logs", "what each run did"),
    ("update", "Update", "installed versus the catalog"),
    ("help", "Help", "keys, and what each profile is for"),
)


def _count(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else "?"


def doctor_text(doc: Document | None, error: str | None) -> str:
    if doc is not None:
        b = doc.body
        return (f"Doctor: {_count(b, 'fails')} fail, {_count(b, 'warns')} warn, "
                f"{_count(b, 'healthy')} healthy  (Enter lists the checks)")
    if error:
        return f"Doctor: unavailable - {first_line(error)}"
    return "Doctor: checking (a few seconds)..."


def station_text(doc: Document | None, error: str | None) -> str:
    if doc is not None:
        both = doc.body.get("callsign") is not None and doc.body.get("grid_square") is not None
        return "Station: set" if both else "Station: not set  (open Station to set it)"
    if error:
        return f"Station: unknown - {first_line(error)}"
    return "Station: checking..."


def last_run_text(doc: Document | None, error: str | None) -> str:
    if doc is not None:
        runs = doc.body.get("runs")
        if not isinstance(runs, list):
            return "Last run: unknown"
        if not runs or not isinstance(runs[0], dict):
            return "Last run: no runs yet"
        r = runs[0]
        code = r.get("exit_code")
        tail = f" (exit {code})" if isinstance(code, int) and not isinstance(code, bool) else ""
        return f"Last run: {r.get('command', '?')} - {r.get('result', '?')}{tail}  {r.get('started') or ''}".rstrip()
    if error:
        return f"Last run: unknown - {first_line(error)}"
    return "Last run: checking..."


def behind_text(doc: Document | None, error: str | None) -> str:
    if doc is not None:
        counts = doc.body.get("counts")
        behind = _count(counts, "behind_pin") if isinstance(counts, dict) else "?"
        rows = doc.body.get("rows")
        retired = sum(1 for r in rows if isinstance(r, dict) and r.get("state") == "retired") if isinstance(rows, list) else 0
        extra = f"; retired in the catalog: {retired}" if retired else ""
        return f"Behind the pin: {behind}{extra}"
    if error:
        return f"Behind the pin: unknown ({first_line(error)})"
    return "Behind the pin: checking..."


class ChecksScreen(Screen):
    name = "checks"
    title = "Doctor checks"

    def __init__(self, ctx: Context, checks: Sequence[Mapping[str, Any]]) -> None:
        super().__init__(ctx)
        rows: list[urwid.Widget] = [text("The fixes below are text to read; the console never runs one.", "dim"), text("")]
        for check in checks:
            state = str(check.get("status", "?"))
            attr = {"fail": "fail", "warn": "warn", "ok": "ok"}.get(state)
            rows.append(text(f"[{state}] {check.get('name', '?')}: {check.get('detail') or ''}", attr))
            if check.get("fix"):
                rows.append(text(f"      fix: {check['fix']}", "dim"))
        self._walker[:] = rows


class HomeScreen(Screen):
    name = "home"
    title = "Home"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.docs: dict[str, Document] = {}

    def on_show(self) -> None:
        for key, words in READS.items():
            self._start(key, words)
        self.redraw()

    def _start(self, key: str, words: tuple[str, ...]) -> None:
        self.docs.pop(key, None)
        self.load(key, lambda: self.ctx.engine.read(*words), lambda doc: self._store(key, doc))

    def _store(self, key: str, doc: Document) -> None:
        self.docs[key] = doc
        shared, body = self.ctx.shared, doc.body
        shared.engine_version = doc.engine
        if key == "status":
            shared.target = header_target(body.get("target") if isinstance(body.get("target"), dict) else None)
        elif key == "doctor":
            counts = [body.get(k) for k in ("fails", "warns", "healthy")]
            if all(isinstance(c, int) and not isinstance(c, bool) for c in counts):
                shared.doctor = (int(counts[0]), int(counts[1]), int(counts[2]))
        elif key == "station":
            shared.station_set = body.get("callsign") is not None and body.get("grid_square") is not None
        self.ctx.refresh_header()

    def _walkthrough_rows(self) -> list[urwid.Widget]:
        return []  # filled in by Task 15 (the first-run checklist)

    def redraw(self) -> None:
        doc, err = self.docs.get, self.errors.get
        rows: list[urwid.Widget] = [text("The engine's own commands, one screen at a time.", "dim"), text("")]
        rows += self._walkthrough_rows()
        doctor = Row(doctor_text(doc("doctor"), err("doctor")), "doctor")
        urwid.connect_signal(doctor, "activate", self._open_checks)
        rows += [doctor, text(station_text(doc("station"), err("station"))),
                 text(last_run_text(doc("logs"), err("logs"))), text(behind_text(doc("update"), err("update"))),
                 text(""), text("Where to next (press the number, or Enter):", "dim")]
        for number, (name, label, blurb) in enumerate(MENU, 1):
            row = Row(f" {number}  {label:<9} {blurb}", name)
            urwid.connect_signal(row, "activate", self._open_row)
            rows.append(row)
        self.set_rows(rows)

    def _open_checks(self, _row: Row) -> None:
        doctor = self.docs.get("doctor")
        checks = doctor.body.get("checks") if doctor else None
        if isinstance(checks, list):
            self.ctx.push(ChecksScreen(self.ctx, [c for c in checks if isinstance(c, dict)]))

    def _open_row(self, row: Row) -> None:
        self.ctx.open_screen(str(row.value))

    def keypress(self, key: str) -> str | None:
        if key in ("1", "2", "3", "4", "5"):
            self.ctx.open_screen(MENU[int(key) - 1][0])
            return None
        return key
```

Run: `python3 -m pytest tests/test_home.py -v`
Expected: PASS (all). If `test_home_summarises_each_document` fails on `Behind the pin:` the fixture `update-all.json` is the E2 shape, which Task 2 created by hand; check its `counts.behind_pin` is 1.

- [ ] **Step 3: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the Home screen"
```
Expected: clean, all pass.

---

### Task 9: The plan view, the run, and the result

The plan always comes first; no path reaches the real command without it (spec section 5). This task builds the plan screen (every section of `InstallPlanView` and `RemovalPlanView`, hidden when empty, in the plan's own order), the pane run behind capital `R`, and the result screen that re-reads the engine's log and status.

**Files:**
- Create: `hammunition_console/screens/plan.py`
- Test: `tests/test_plan.py`

**Interfaces:**
- Consumes: `screens.base.{Screen, text, Row}`, `fmt.{clean, first_line}`, `ctx.engine.command(*words)`, `ctx.run_pane(argv, title, on_exit)`, `ctx.replace`, `ctx.pop(count)`.
- Produces: `plan.Section(title: str, lines: tuple[str, ...])`; `plan.install_sections(view: Mapping[str, Any]) -> list[Section]`; `plan.removal_sections(view: Mapping[str, Any]) -> list[Section]`; `plan.blocker_lines(blockers: Sequence[Mapping[str, Any]]) -> list[str]`; `plan.PlanScreen(ctx, action: str, names: Sequence[str])` (`action` is `"install"` or `"uninstall"`; `.names`, `.doc`, `.runnable`); `plan.ResultScreen(ctx, action, names, code: int | None)`.

- [ ] **Step 1: Write the tests (failing first)**

Create `tests/test_plan.py`:

```python
from typing import Any

import pytest

from hammunition_console.engine import EngineRefused
from hammunition_console.screens.plan import (
    PlanScreen, ResultScreen, Section, blocker_lines, install_sections, removal_sections,
)
from tests.helpers import FakeContext, FakeEngine, document, load, render


def view(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"packages": [], "displaced": [], "apt_release": None, "no_recommends": None, "repos": [],
                            "mirror": None, "data": [], "maps": None, "memberships": [], "consent_gates": [],
                            "config_files": [], "user_services": [], "desktops_read": None, "deferrals": [],
                            "notes": [], "records": None, "sudo": None, "commands": [],
                            "suggestion_notes": [], "region_notes": []}
    return {**base, **over}


def titles(sections: list[Section]) -> list[str]:
    return [s.title for s in sections]


def test_an_empty_view_has_no_sections() -> None:
    assert install_sections(view()) == []


def test_the_recorded_plan_lists_its_units_in_order_with_method_state_and_requester() -> None:
    plan = load("plan-station")["install"]
    sections = install_sections(plan)
    units = sections[0]
    assert units.title == "Units, in install order"
    first = plan["packages"][0]
    assert units.lines[0].startswith(f"{first['name']}  {first['method']}  {first['state']}")
    assert all(s.lines for s in sections), "a section with no lines must be hidden"


def test_the_gated_plan_says_you_will_type_yes_and_lists_each_risk() -> None:
    plan = load("plan-gated")["install"]
    gate = next(s for s in install_sections(plan) if s.title.startswith("You will be asked to type yes"))
    risk = plan["consent_gates"][0]["risk_lines"][0]
    assert any(risk in line for line in gate.lines) and gate.lines[0].startswith(plan["consent_gates"][0]["profile"])


def test_every_section_the_spec_names_is_built_from_the_documents_real_field_names() -> None:
    v = view(
        packages=[{"name": "u1", "method": "apt", "state": "will install", "requested_by": ["requested"], "apt": []}],
        displaced=[{"package": "librtlsdr0", "declared_by": "u1"}],
        apt_release={"release": "trixie-backports", "packages": ["p1"]},
        no_recommends={"units": ["u1"], "packages": ["p2"]},
        repos=[{"name": "r", "unit": "u1", "packages": ["p3"], "uri": "https://example.org/apt", "suites": ["s"],
                "components": ["main"], "key_fingerprint": "AB CD", "sources": "/etc/apt/sources.list.d/r.sources",
                "keyring": "/etc/apt/keyrings/r.gpg", "consent_env_var": "X"}],
        mirror={"url": "http://lan/", "ignored": False, "text": "mirror text"},
        data=[{"unit": "d1", "total_size": 5, "total_human": "5 MiB", "licence": "CC0", "licence_url": "u",
               "artifacts": [{"url": "https://e/x", "size": 5, "size_human": "5 MiB"}], "installs_under": "share/d1",
               "verified_by": "sha256, pinned by Hammunition", "approximate": False}],
        memberships=[{"user": "me", "group": "dialout", "package": "u1", "detail": "serial ports", "reverse_hint": "gpasswd -d"}],
        config_files=[{"unit": "u1", "path": "/etc/x.conf", "mode": "0644", "append": False, "backup_existing": True, "fills": ["callsign"]}],
        user_services=[{"unit": "u1", "name": "svc", "path": "/p", "exec": "/bin/x", "fills": [], "listen": "127.0.0.1:4532", "starts_now": False}],
        deferrals=[{"kind": "config", "subject": "/etc/y", "what": "not written", "why": "no callsign", "remedy": "station set"}],
        notes=["a note"], records={"log": "/home/user/tx.jsonl", "handed_to": None},
        sudo={"keepalive": True, "interval_seconds": 240, "text": "sudo is asked once"},
        commands=[{"description": "d", "display": "sudo apt-get install u1", "argv": [], "action": None, "requires_root": True, "sources": []}],
    )
    flat = "\n".join(line for s in install_sections(v) for line in [s.title, *s.lines])
    for needle in ("u1  apt  will install  (requested by requested)", "librtlsdr0", "trixie-backports", "p2",
                   "https://example.org/apt", "key fingerprint AB CD", "/etc/apt/keyrings/r.gpg", "mirror text",
                   "d1: 5 MiB, licence CC0", "sha256, pinned by Hammunition", "me is added to group dialout",
                   "/etc/x.conf", "fills: callsign", "svc", "127.0.0.1:4532", "no callsign", "station set", "a note",
                   "/home/user/tx.jsonl", "sudo is asked once", "$ sudo apt-get install u1  (root)"):
        assert needle in flat, needle
    assert "None" not in flat


def test_map_regions_show_sizes_and_never_the_region_names() -> None:
    v = view(maps={"fetch": [{"region": "north-america/us/sentinelregion", "snapshot": "s", "size": 1, "size_human": "1 B",
                              "verified_by": "md5", "nothing_to_do": False}], "current": [], "convert": [], "kept": [],
                   "licence": "ODbL", "licence_url": "u", "download_total": 1, "download_total_human": "1 B",
                   "disk_total": 9, "disk_total_human": "9 B", "estimate_note": "measured", "terrain": None,
                   "boundaries": None, "unknown_country": False})
    flat = "\n".join(line for s in install_sections(v) for line in s.lines)
    assert "sentinelregion" not in flat and "1 region(s) to download" in flat and "download 1 B, disk 9 B" in flat


def test_station_values_are_named_never_shown() -> None:
    v = view(config_files=[{"unit": "u", "path": "/etc/a", "mode": "0600", "append": False, "backup_existing": False, "fills": ["callsign", "grid_square"]}])
    flat = "\n".join(line for s in install_sections(v) for line in s.lines)
    assert "callsign, grid_square" in flat and "N0CALL" not in flat


def test_null_fields_are_tolerated() -> None:
    v = view(packages=[{"name": "u", "method": None, "state": None, "requested_by": None, "apt": None}],
             deferrals=[{"kind": "package", "subject": "s", "what": "w", "why": "y", "remedy": None}])
    flat = "\n".join(line for s in install_sections(v) for line in s.lines)
    assert "None" not in flat


def test_removal_sections() -> None:
    plan = load("plan-uninstall")["removal"]
    sections = removal_sections(plan)
    assert sections and all(s.lines for s in sections)
    flat = [s.title for s in sections]
    assert any("Steps" in t for t in flat) or plan["commands"] == []


def test_blocker_lines_show_subject_reason_and_the_remedy_only_when_there_is_one() -> None:
    lines = blocker_lines([{"subject": "x", "reason": "because", "remedy": None},
                           {"subject": "y", "reason": "r\x1b[2J", "remedy": "do z"}])
    assert lines[0] == "x: because" and lines[2] == "   remedy: do z" and len(lines) == 3
    assert "\x1b" not in "".join(lines) and not any("None" in line for line in lines)


def test_a_planned_install_shows_its_sections_and_says_nothing_changed_yet() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["station"])
    screen.on_show()
    out = render(screen.widget(), 100, 40)
    assert "Nothing has been changed yet" in out and "Units, in install order" in out
    assert "b back" in out and "changes nothing" in out
    assert screen.runnable and ctx.panes == []


def test_capital_r_runs_the_real_command_in_a_pane_without_dry_run_or_json() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["station"])
    screen.on_show()
    assert screen.keypress("r") == "r" and ctx.panes == []
    assert screen.keypress("R") is None
    pane = ctx.panes[0]
    assert pane.argv == ["hammunition", "install", "station"] and pane.title == "install station"
    assert "--dry-run" not in pane.argv and "--json" not in pane.argv


def test_uninstall_plans_and_runs_the_uninstall_verb() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "uninstall", ["station"])
    screen.on_show()
    assert ctx.engine.calls[-1] == ("uninstall", "station", "--dry-run")
    screen.keypress("R")
    assert ctx.panes[0].argv == ["hammunition", "uninstall", "station"]


def test_a_refused_plan_shows_blockers_and_cannot_be_run() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["no-such-unit-xyz"])
    screen.on_show()
    out = render(screen.widget(), 100, 30)
    assert "refused" in out and "Nothing will be run" in out and "Units, in install order" not in out
    blocker = load("plan-refused")["blockers"][0]
    assert blocker["subject"] in out and blocker["reason"][:20] in out
    assert screen.runnable is False and screen.keypress("R") == "R" and ctx.panes == []


def test_an_engine_error_is_shown_and_runs_nothing() -> None:
    engine = FakeEngine()
    engine.set(("install", "x", "--dry-run"), EngineRefused(2, "no catalog"))
    ctx = FakeContext(engine=engine)
    screen = PlanScreen(ctx, "install", ["x"])
    screen.on_show()
    out = render(screen.widget(), 100, 20)
    assert "no catalog" in out and "Nothing was run" in out
    screen.keypress("R")
    assert ctx.panes == []


def test_a_malicious_reason_never_reaches_the_terminal() -> None:
    engine = FakeEngine()
    engine.set(("install", "x", "--dry-run"), document("plan", {"action": "install", "requested": ["x"], "outcome": "refused",
               "blockers": [{"subject": "s", "reason": "\x1b]0;pwned\x07bad", "remedy": None}], "install": None, "removal": None}, exit_code=2))
    ctx = FakeContext(engine=engine)
    screen = PlanScreen(ctx, "install", ["x"])
    screen.on_show()
    assert "\x1b" not in render(screen.widget(), 100, 20)


def test_when_the_pane_ends_the_result_replaces_it_and_back_returns_to_the_list() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["station"])
    screen.on_show()
    screen.keypress("R")
    ctx.panes[0].on_exit(0)
    result = ctx.replaced[-1]
    assert isinstance(result, ResultScreen)
    out = render(result.widget(), 100, 20)
    assert "Exit code: 0" in out
    run = next(r for r in load("logs")["runs"] if r["command"] == "install")
    assert f"Engine log: {run['result']} (exit {run['exit_code']})" in out or "Engine log: running" in out
    assert "Latest transaction:" in out
    assert result.keypress("b") is None and ctx.popped == 2


def test_a_cut_off_program_has_no_exit_code_and_says_so() -> None:
    result = ResultScreen(FakeContext(), "install", ["station"], None)
    result.on_show()
    assert "Exit code: unknown" in render(result.widget(), 100, 20)


def test_the_result_survives_a_failing_log_read() -> None:
    engine = FakeEngine()
    engine.set(("logs",), ValueError("unreadable"))
    result = ResultScreen(FakeContext(engine=engine), "install", ["station"], 1)
    result.on_show()
    out = render(result.widget(), 100, 20)
    assert "Exit code: 1" in out and "Engine log: unknown" in out and "unreadable" in out
```

- [ ] **Step 2: Run it; confirm it fails; implement**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_plan.py -v`
Expected: FAIL (`ModuleNotFoundError`).

Create `hammunition_console/screens/plan.py`:

```python
"""The plan (D-016): what the engine will do, section by section as the engine
groups it, hidden when empty, shown before any real command can run."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import urwid

from hammunition_console.context import Context
from hammunition_console.engine import Document
from hammunition_console.fmt import clean, first_line
from hammunition_console.screens.base import Screen, text


@dataclass(frozen=True)
class Section:
    title: str
    lines: tuple[str, ...]


def _s(value: Any) -> str:
    return "" if value is None else clean(value)


def _names(value: Any) -> str:
    return ", ".join(_s(v) for v in value) if isinstance(value, list) else ""


def _dicts(value: Any) -> list[Mapping[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def blocker_lines(blockers: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    for b in blockers:
        out.append(f"{_s(b.get('subject'))}: {_s(b.get('reason'))}")
        if b.get("remedy"):
            out.append(f"   remedy: {_s(b['remedy'])}")
    return out


def _steps(commands: Any) -> list[str]:
    out = []
    for c in _dicts(commands):
        out.append(f"$ {_s(c.get('display'))}" + ("  (root)" if c.get("requires_root") else ""))
    return out


def install_sections(view: Mapping[str, Any]) -> list[Section]:
    out: list[Section] = []

    def add(title: str, lines: Sequence[str]) -> None:
        if lines:
            out.append(Section(title, tuple(lines)))

    add("Units, in install order", [
        f"{_s(p.get('name'))}  {_s(p.get('method'))}  {_s(p.get('state'))}  (requested by {_names(p.get('requested_by')) or '-'})"
        for p in _dicts(view.get("packages"))])
    add("Distribution packages that stay installed (displaced or shadowed)", [
        f"{_s(d.get('package'))}  (declared by {_s(d.get('declared_by'))})" for d in _dicts(view.get("displaced"))])
    release = view.get("apt_release")
    if isinstance(release, dict):
        add("apt takes some packages from another release", [f"{_s(release.get('release'))}: {_names(release.get('packages'))}"])
    norec = view.get("no_recommends")
    if isinstance(norec, dict):
        add("apt installs these without Recommends", [f"units: {_names(norec.get('units'))}", f"packages: {_names(norec.get('packages'))}"])
    repo_lines: list[str] = []
    for r in _dicts(view.get("repos")):
        repo_lines += [f"{_s(r.get('name'))} for {_s(r.get('unit'))}: {_s(r.get('uri'))}  suites {_names(r.get('suites'))}",
                       f"   key fingerprint {_s(r.get('key_fingerprint'))}",
                       f"   writes {_s(r.get('sources'))} and {_s(r.get('keyring'))}"]
    add("Third-party apt repositories (each asks for its own typed confirmation)", repo_lines)
    mirror = view.get("mirror")
    if isinstance(mirror, dict):
        add("LAN mirror", [_s(mirror.get("text"))])
    data_lines: list[str] = []
    for d in _dicts(view.get("data")):
        data_lines.append(f"{_s(d.get('unit'))}: {_s(d.get('total_human'))}, licence {_s(d.get('licence'))}, {_s(d.get('verified_by'))}")
        data_lines += [f"   {_s(a.get('size_human'))}  {_s(a.get('url'))}" for a in _dicts(d.get("artifacts"))]
        data_lines.append(f"   installs under {_s(d.get('installs_under'))}")
    add("Offline data downloaded (size and licence)", data_lines)
    maps = view.get("maps")
    if isinstance(maps, dict):
        fetch, current = len(_dicts(maps.get("fetch"))), len(_dicts(maps.get("current")))
        add("Map regions (their names are in the CLI's own plan, not shown here)", [
            f"{fetch} region(s) to download, {current} already current",
            f"download {_s(maps.get('download_total_human'))}, disk {_s(maps.get('disk_total_human'))}",
            f"licence {_s(maps.get('licence'))}", _s(maps.get("estimate_note"))])
    add("Group memberships", [
        f"{_s(m.get('user'))} is added to group {_s(m.get('group'))} (for {_s(m.get('package'))}): {_s(m.get('detail'))}"
        + (f"  undo: {_s(m['reverse_hint'])}" if m.get("reverse_hint") else "") for m in _dicts(view.get("memberships"))])
    add("Configuration files written (station values are filled in by name; the values are not shown)", [
        f"{_s(c.get('path'))}  ({_s(c.get('unit'))}, mode {_s(c.get('mode'))})"
        + (f"  fills: {_names(c.get('fills'))}" if c.get("fills") else "") for c in _dicts(view.get("config_files"))])
    add("User services written and enabled", [
        f"{_s(u.get('name'))}: {_s(u.get('exec'))}  (listens {_s(u.get('listen'))})" for u in _dicts(view.get("user_services"))])
    deferral_lines: list[str] = []
    for d in _dicts(view.get("deferrals")):
        deferral_lines.append(f"{_s(d.get('kind'))} {_s(d.get('subject'))}: {_s(d.get('what'))} - {_s(d.get('why'))}")
        if d.get("remedy"):
            deferral_lines.append(f"   {_s(d['remedy'])}")
    add("What will NOT happen", deferral_lines)
    add("Notes", [_s(n) for n in view.get("notes") or [] if isinstance(n, str)])
    records = view.get("records")
    if isinstance(records, dict):
        add("Records", [f"transaction log: {_s(records.get('log'))}"])
    gate_lines: list[str] = []
    for g in _dicts(view.get("consent_gates")):
        gate_lines.append(f"{_s(g.get('profile'))}:")
        gate_lines += [f"   {_s(r)}" for r in g.get("risk_lines") or []]
    add("You will be asked to type yes for each of these.", gate_lines)
    sudo = view.get("sudo")
    if isinstance(sudo, dict):
        add("sudo", [_s(sudo.get("text"))])
    add("Steps, exactly as they will run", _steps(view.get("commands")))
    return out


def removal_sections(view: Mapping[str, Any]) -> list[Section]:
    out: list[Section] = []

    def add(title: str, lines: Sequence[str]) -> None:
        if lines:
            out.append(Section(title, tuple(lines)))

    add("apt packages removed", [f"{_s(u.get('unit'))}: {_names(u.get('packages'))}" for u in _dicts(view.get("to_remove"))])
    add("Files and trees removed", [f"{_s(a.get('unit'))}: {_s(a.get('kind'))} {_s(a.get('path'))}  ({_s(a.get('basis'))})"
                                    for a in _dicts(view.get("artifacts"))])
    add("Present, but not attributed to this engine: left alone", [f"{_s(u.get('unit'))}: {_names(u.get('paths'))}" for u in _dicts(view.get("left_unattributed"))])
    add("Installed, but not by this engine: left alone", [f"{_s(u.get('unit'))}: {_names(u.get('packages'))}" for u in _dicts(view.get("left_foreign"))])
    add("Nothing to remove", [f"{_s(u.get('unit'))}: {_names(u.get('packages'))}" for u in _dicts(view.get("already_absent"))])
    if view.get("not_reversed"):
        add("What uninstall does not undo, by design", [_s(view["not_reversed"])])
    add("Steps, exactly as they will run", _steps(view.get("commands")))
    return out


class PlanScreen(Screen):
    name = "plan"

    def __init__(self, ctx: Context, action: str, names: Sequence[str]) -> None:
        super().__init__(ctx)
        self.action = action
        self.names = list(names)
        self.title = f"Plan: {action} {' '.join(self.names)}"
        self.doc: Document | None = None
        self.runnable = False

    def on_show(self) -> None:
        self.doc, self.runnable = None, False
        self.load("plan", lambda: self.ctx.engine.read(self.action, *self.names, "--dry-run"), self._store)
        self.redraw()

    def _store(self, doc: Document) -> None:
        self.doc = doc
        self.runnable = doc.kind == "plan" and doc.body.get("outcome") == "planned"

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self.status.get("plan") == "loading":
            rows.append(text("Planning (the engine resolves everything first; this can take a while)..."))
        elif self.status.get("plan") == "error":
            rows += [text(self.errors["plan"], "fail"), text(""), text("Nothing was run.")]
        elif self.doc is not None and not self.runnable:
            rows += [text("The engine refused this transaction. Nothing will be run.", "fail"), text("")]
            rows += [text(line) for line in blocker_lines(_dicts(self.doc.body.get("blockers")))]
        elif self.doc is not None:
            rows += [text(f"{self.action} {' '.join(self.names)}: planned. Nothing has been changed yet.", "ok"),
                     text("R run this in a terminal pane (you will be asked to type any consent yourself)   b back: changes nothing", "key"),
                     text("")]
            view = self.doc.body.get("install") if self.action == "install" else self.doc.body.get("removal")
            sections = install_sections(view) if self.action == "install" and isinstance(view, dict) else (
                removal_sections(view) if isinstance(view, dict) else [])
            for section in sections:
                rows.append(text(section.title, "key"))
                rows += [text("  " + line) for line in section.lines]
                rows.append(text(""))
            rows.append(text("R run this in a terminal pane   b back: changes nothing", "key"))
        self.set_rows(rows)

    def keypress(self, key: str) -> str | None:
        if key == "R" and self.runnable:
            argv = self.ctx.engine.command(self.action, *self.names)
            self.ctx.run_pane(argv, f"{self.action} {' '.join(self.names)}", self._after_pane)
            return None
        return key

    def _after_pane(self, code: int | None) -> None:
        self.ctx.replace(ResultScreen(self.ctx, self.action, self.names, code))


class ResultScreen(Screen):
    name = "result"

    def __init__(self, ctx: Context, action: str, names: Sequence[str], code: int | None) -> None:
        super().__init__(ctx)
        self.action, self.names, self.code = action, list(names), code
        self.title = f"{action} finished"
        self._logs: Document | None = None
        self._state: Document | None = None

    def on_show(self) -> None:
        self.load("logs", lambda: self.ctx.engine.read("logs"), lambda d: setattr(self, "_logs", d))
        self.load("status", lambda: self.ctx.engine.read("status"), lambda d: setattr(self, "_state", d))
        self.redraw()

    def _log_line(self) -> str:
        if self._logs is not None:
            runs = _dicts(self._logs.body.get("runs"))
            run = next((r for r in runs if r.get("command") == self.action), None)
            if run is None:
                return "Engine log: no run of this command is listed"
            code = run.get("exit_code")
            tail = f" (exit {code})" if isinstance(code, int) else ""
            return f"Engine log: {_s(run.get('result'))}{tail}  {_s(run.get('path'))}"
        if "logs" in self.errors:
            return f"Engine log: unknown ({first_line(self.errors['logs'])})"
        return "Engine log: reading..."

    def _state_lines(self) -> list[str]:
        if self._state is not None:
            latest = self._state.body.get("latest")
            if not isinstance(latest, dict):
                return ["Latest transaction: none recorded"]
            lines = [f"Latest transaction: {_s(latest.get('outcome'))}"]
            lines += [f"Not confirmed: {_s(c.get('subject'))} - {_s(c.get('detail'))}" for c in _dicts(latest.get("unconfirmed"))]
            lines += [f"Deferred: {_s(d.get('subject'))} - {_s(d.get('why'))}" for d in _dicts(latest.get("deferred"))]
            return lines
        if "status" in self.errors:
            return [f"Latest transaction: unknown ({first_line(self.errors['status'])})"]
        return ["Latest transaction: reading..."]

    def redraw(self) -> None:
        code = f"Exit code: {self.code}" if self.code is not None else "Exit code: unknown (the program was cut off)"
        self.set_rows([text(f"{self.action} {' '.join(self.names)}: the program finished."), text(code),
                       text(self._log_line()), *[text(line) for line in self._state_lines()], text(""),
                       text("b back to the list (the engine's word above is the result; the console adds none of its own)", "key")])

    def keypress(self, key: str) -> str | None:
        if key == "b":
            self.ctx.pop(2)
            return None
        return key
```

Run: `python3 -m pytest tests/test_plan.py -v`
Expected: PASS. Likely adjustments: the recorded `plan-station` may have no `consent_gates`/`sudo` (those assertions are on built dicts, not on the fixture), and `test_the_gated_plan...` requires `plan-gated` to carry at least one gate line, which `capture_fixtures.py` guarantees by choosing a `consent_gated` profile.

- [ ] **Step 3: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the plan view, the pane run and the result screen"
```
Expected: clean, all pass.

---

### Task 10: Install: profiles, units, install by name, and the end-to-end install through a real pty

**Files:**
- Create: `hammunition_console/screens/install.py`, `tests/test_pty_install.py`
- Test: `tests/test_install_screen.py`

**Interfaces:**
- Consumes: `screens.plan.PlanScreen`, `screens.base.{Screen, Row, text}`, `fmt.human_size`, `FakeContext/FakeEngine/document/load/render`, `tests.pty_driver.PtyProcess`, `helpers.make_shim`.
- Produces: `install.profile_state(entry: Mapping[str, Any]) -> str`; `install.profile_text(entry) -> str`; `install.unit_text(entry) -> str`; `install.InstallScreen(ctx, highlight: str | None = None)` (`name = "install"`, `.mode: "profiles" | "units"`, `.note: str`, `._name_edit: urwid.Edit`).

- [ ] **Step 1: Write the screen's tests (failing first)**

Create `tests/test_install_screen.py`:

```python
import pytest

from hammunition_console.engine import EngineRefused
from hammunition_console.screens.install import InstallScreen, profile_state, profile_text, unit_text
from hammunition_console.screens.plan import PlanScreen
from tests.helpers import FakeContext, FakeEngine, document, load, render


def shown(ctx: FakeContext | None = None, **kw: object) -> tuple[InstallScreen, FakeContext, str]:
    ctx = ctx or FakeContext()
    screen = InstallScreen(ctx, **kw)  # type: ignore[arg-type]
    screen.on_show()
    return screen, ctx, render(screen.widget(), 110, 30)


def test_profile_rows_carry_name_stage_state_gate_and_summary_with_e1() -> None:
    _, _, out = shown()
    first = load("list-all")["profiles"][0]
    assert first["name"] in out and f"{first['installed']} of {first['members']} installed" in out
    assert first["summary"][:30] in out
    gated = next(p for p in load("list-all")["profiles"] if p["consent_gated"])
    line = next(l for l in out.splitlines() if l.startswith(gated["name"]))
    assert " G " in line


def test_without_e1_the_state_is_unknown_and_nothing_crashes() -> None:
    _, _, out = shown(FakeContext(engine=FakeEngine(suffix="-without")))
    first = load("list-all-without")["profiles"][0]
    assert f"{len(first['packages'])} units, state unknown" in out and "None" not in out


@pytest.mark.parametrize("entry,expected", [
    ({"packages": ["a", "b"], "members": 2, "installed": 1, "installed_size_bytes": 5 * 1024**2}, "1 of 2 installed, 5.0 MiB"),
    ({"packages": ["a"], "members": 1, "installed": 0, "installed_size_bytes": None}, "0 of 1 installed"),
    ({"packages": ["a", "b", "c"]}, "3 units, state unknown"),
    ({"packages": None}, "0 units, state unknown"),
    ({"members": "2", "installed": None, "packages": ["a"]}, "1 units, state unknown"),
])
def test_profile_state_degrades_to_unknown(entry: dict[str, object], expected: str) -> None:
    assert profile_state(entry) == expected


def test_null_summary_and_missing_fields_render_blank_not_none() -> None:
    entry = {"name": "p", "stage": None, "summary": None, "packages": [], "consent_gated": None, "documentation": None}
    assert "None" not in profile_text(entry) and profile_text(entry).startswith("p")
    assert "None" not in unit_text({"name": "u", "status": None, "summary": None, "resolves_here": None})
    assert "not here" in unit_text({"name": "u", "status": "supported", "summary": "s", "resolves_here": None})


def test_control_characters_in_a_summary_are_removed() -> None:
    engine = FakeEngine()
    cat = load("list-all")
    cat["profiles"][0]["summary"] = "evil\x1b[2Jsummary"
    engine.set(("list",), document("catalog", cat))
    _, _, out = shown(FakeContext(engine=engine))
    assert "\x1b" not in out and "evilsummary" in out.replace("[2J", "")


def test_a_failed_list_is_shown() -> None:
    engine = FakeEngine()
    engine.set(("list",), EngineRefused(2, "no catalog here"))
    assert "no catalog here" in shown(FakeContext(engine=engine))[2]


def test_tab_switches_between_profiles_and_units() -> None:
    screen, _, out = shown()
    assert "Profiles" in out and "Units" not in out.replace("units", "")
    assert screen.keypress("tab") is None and screen.mode == "units"
    out = render(screen.widget(), 110, 30)
    unit = load("list-all")["packages"][0]
    assert unit["name"] in out
    assert screen.keypress("tab") is None and screen.mode == "profiles"


def first_row(screen: InstallScreen, kind: str) -> object:
    return next(r for r in screen._walker if getattr(r, "value", None) and r.value[0] == kind)  # type: ignore[attr-defined]


def test_enter_on_a_profile_opens_its_plan_and_capital_u_plans_the_uninstall() -> None:
    screen, ctx, _ = shown()
    name = load("list-all")["profiles"][0]["name"]
    row = first_row(screen, "profile")
    row.keypress((100,), "enter")  # type: ignore[attr-defined]
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and (plan.action, plan.names) == ("install", [name])
    screen._walker.set_focus(screen._walker.index(row))  # type: ignore[attr-defined]
    assert screen.keypress("U") is None
    uninstall = ctx.pushed[-1]
    assert isinstance(uninstall, PlanScreen) and (uninstall.action, uninstall.names) == ("uninstall", [name])


def test_enter_on_a_unit_plans_just_that_unit() -> None:
    screen, ctx, _ = shown()
    screen.keypress("tab")
    unit = load("list-all")["packages"][0]["name"]
    first_row(screen, "unit").keypress((100,), "enter")  # type: ignore[attr-defined]
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and plan.names == [unit]


def type_name(screen: InstallScreen, value: str) -> None:
    screen._name_edit.set_edit_text(value)
    screen._walker.set_focus(screen._walker.index(screen._name_edit))
    screen.keypress("enter")


def test_a_typed_name_goes_to_the_plan_as_separate_argv_elements() -> None:
    screen, ctx, _ = shown()
    type_name(screen, "station  hamlib")
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and plan.names == ["station", "hamlib"]


@pytest.mark.parametrize("typed", ["-y", "--yes", "station -y", "--dry-run", "-", "a --yes b"])
def test_a_typed_name_that_begins_with_a_dash_runs_nothing(typed: str) -> None:
    screen, ctx, _ = shown()
    type_name(screen, typed)
    assert ctx.pushed == [] and ctx.panes == []
    assert "does not start with '-'" in render(screen.widget(), 110, 30) and "Nothing was run" in render(screen.widget(), 110, 30)


def test_an_empty_name_does_nothing() -> None:
    screen, ctx, _ = shown()
    type_name(screen, "   ")
    assert ctx.pushed == []


def test_highlight_puts_focus_on_that_profile_and_the_detail_shows_its_docs() -> None:
    profile = load("list-all")["profiles"][1]
    screen, _, out = shown(highlight=profile["name"])
    focused = screen._walker.focus
    assert focused.value[1]["name"] == profile["name"]  # type: ignore[union-attr]
    docs = profile["documentation"]
    if docs.get("why_together"):
        assert docs["why_together"][:30] in out
    if docs.get("manual_configuration"):
        assert docs["manual_configuration"][:30] in out


def test_the_detail_panel_tolerates_null_documentation_fields() -> None:
    engine = FakeEngine()
    cat = load("list-all")
    cat["profiles"][0]["documentation"] = {"what_it_installs": None, "why_together": None, "deliberately_excludes": None,
                                           "manual_configuration": None, "disk_footprint_hint": None}
    engine.set(("list",), document("catalog", cat))
    assert "None" not in shown(FakeContext(engine=engine))[2]


def test_the_gate_marker_is_explained() -> None:
    assert "G = asks you to type yes" in shown()[2]
```

- [ ] **Step 2: Run it; confirm it fails; implement**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_install_screen.py -v`
Expected: FAIL (`ModuleNotFoundError`).

Create `hammunition_console/screens/install.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import urwid

from hammunition_console.context import Context
from hammunition_console.engine import Document
from hammunition_console.fmt import clean, human_size
from hammunition_console.screens.base import Row, Screen, text
from hammunition_console.screens.plan import PlanScreen


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def profile_state(entry: Mapping[str, Any]) -> str:
    """Installed state from E1's fields; 'unknown' when the engine does not send them."""
    members, installed, size = entry.get("members"), entry.get("installed"), entry.get("installed_size_bytes")
    if _int(members) and _int(installed):
        return f"{installed} of {members} installed" + (f", {human_size(size)}" if _int(size) else "")
    packages = entry.get("packages")
    return f"{len(packages) if isinstance(packages, list) else 0} units, state unknown"


def profile_text(entry: Mapping[str, Any]) -> str:
    gate = "G" if entry.get("consent_gated") is True else " "
    return (f"{clean(entry.get('name') or '?'):<18} {clean(entry.get('stage') or ''):<9} "
            f"{profile_state(entry):<26} {gate}  {clean(entry.get('summary') or '')}")


def unit_text(entry: Mapping[str, Any]) -> str:
    return (f"{clean(entry.get('name') or '?'):<26} {clean(entry.get('status') or ''):<12} "
            f"{clean(entry.get('resolves_here') or 'not here'):<10} {clean(entry.get('summary') or '')}")


class InstallScreen(Screen):
    name = "install"
    title = "Install"

    def __init__(self, ctx: Context, highlight: str | None = None) -> None:
        super().__init__(ctx)
        self.mode = "profiles"
        self.note = ""
        self._highlight = highlight
        self._catalog: Document | None = None
        self._name_edit = urwid.Edit("Install by name (separate several with spaces): ")
        self._detail = urwid.Text("")
        self._frame = urwid.Frame(self._list, footer=urwid.Pile([urwid.Divider("-"), self._detail]))
        urwid.connect_signal(self._walker, "modified", self._focus_changed)

    def widget(self) -> urwid.Widget:
        return self._frame

    def on_show(self) -> None:
        self.load("list", lambda: self.ctx.engine.read("list"), self._store)
        self.redraw()

    def _store(self, doc: Document) -> None:
        self._catalog = doc

    def _entries(self, key: str) -> list[Mapping[str, Any]]:
        value = self._catalog.body.get(key) if self._catalog else None
        return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []

    def redraw(self) -> None:
        rows: list[urwid.Widget] = [self._name_edit]
        if self.note:
            rows.append(text(self.note, "warn"))
        if self.status.get("list") == "loading":
            rows.append(text("Reading the catalog..."))
        elif self.status.get("list") == "error":
            rows.append(text(self.errors["list"], "fail"))
        else:
            kind = "profile" if self.mode == "profiles" else "unit"
            rows.append(text(("Profiles" if kind == "profile" else "Units") +
                             "   (Tab switches; Enter plans the install; U plans an uninstall; G = asks you to type yes first)", "dim"))
            for entry in self._entries("profiles" if kind == "profile" else "packages"):
                row = Row(profile_text(entry) if kind == "profile" else unit_text(entry), (kind, entry))
                urwid.connect_signal(row, "activate", self._open)
                rows.append(row)
        self.set_rows(rows)
        self._focus_highlight()
        self._focus_changed()

    def _focus_highlight(self) -> None:
        if not self._highlight:
            return
        for index, row in enumerate(self._walker):
            value = getattr(row, "value", None)
            if isinstance(value, tuple) and value[1].get("name") == self._highlight:
                self._walker.set_focus(index)
                self._highlight = None
                return

    def _focus_changed(self) -> None:
        value = self.focused_value()
        lines: list[str] = []
        if isinstance(value, tuple) and value[0] == "profile":
            docs = value[1].get("documentation")
            docs = docs if isinstance(docs, dict) else {}
            for label, key in (("Why together", "why_together"), ("Set up by hand afterwards", "manual_configuration"),
                               ("Disk", "disk_footprint_hint")):
                if docs.get(key):
                    lines.append(f"{label}: {docs[key]}")
        elif isinstance(value, tuple):
            lines.append(f"{value[1].get('summary') or ''}  [{', '.join(str(c) for c in value[1].get('categories') or [])}]")
        self._detail.set_text(clean("\n".join(lines)))

    def _open(self, row: Row) -> None:
        self._plan("install", row)

    def _plan(self, action: str, row: Any) -> None:
        value = getattr(row, "value", None)
        if isinstance(value, tuple) and isinstance(value[1].get("name"), str):
            self.ctx.push(PlanScreen(self.ctx, action, [value[1]["name"]]))

    def _submit_name(self) -> None:
        names = self._name_edit.edit_text.split()
        if not names:
            return
        if any(name.startswith("-") for name in names):
            self.note = "A name does not start with '-'. Nothing was run."
            self.redraw()
            return
        self.note = ""
        self.ctx.push(PlanScreen(self.ctx, "install", names))

    def keypress(self, key: str) -> str | None:
        if key == "tab":
            self.mode = "units" if self.mode == "profiles" else "profiles"
            self.redraw()
            return None
        if key == "enter" and self._walker.focus is self._name_edit:
            self._submit_name()
            return None
        if key == "U" and self.mode == "profiles":
            focus = self._walker.focus
            self._plan("uninstall", focus)
            return None
        return key
```

Run: `python3 -m pytest tests/test_install_screen.py -v`
Expected: PASS (all). If `urwid.connect_signal(self._walker, "modified", self._focus_changed)` rejects a zero-argument callback in your urwid, change `_focus_changed` to accept `*_: object`. The `modified` signal also fires inside `set_rows`; that is intended.

- [ ] **Step 3: The end-to-end install through the whole console, in a real pty**

Create `tests/test_pty_install.py`:

```python
"""The whole console, in a real pseudo-terminal, against the fake hammunition:
Home -> Install -> plan -> R -> the pane -> a person types yes -> result."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import load, make_shim
from tests.pty_driver import PtyProcess

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.pty


def env_for(tmp: Path) -> dict[str, str]:
    home = tmp / "home"
    home.mkdir()
    return {
        "PATH": f"{make_shim(tmp)}:{os.environ['PATH']}", "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
        "TERM": "xterm-256color", "LANG": "C.UTF-8", "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_HAMMUNITION_LOG": str(tmp / "fake.log"),
        "HAMMUNITION_ACCEPT_RF_RESEARCH": "1",  # a canary: no child of the console may ever see it
    }


def test_install_end_to_end_with_a_typed_yes(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    first = load("list-all")["profiles"][0]["name"]
    proc = PtyProcess([sys.executable, "-m", "hammunition_console"], env)
    try:
        proc.expect("Install")
        proc.send("1")
        proc.expect(first)
        proc.send("\x1b[B")  # down: off the name box onto the first profile
        proc.send("\r")
        proc.expect("changes nothing")
        proc.send("R")
        proc.expect("continue:")
        proc.send("yes\r")
        proc.expect("Finished with exit code 0")
        proc.send("\r")
        proc.expect("Exit code: 0")
        proc.send("b")
        proc.expect(first)
        proc.send("q")
        assert proc.wait() == 0
    finally:
        proc.close()
    entries = [json.loads(line) for line in (tmp_path / "fake.log").read_text().splitlines()]
    assert entries, "the fake was never called"
    for entry in entries:
        assert "HAMMUNITION_ACCEPT_RF_RESEARCH" not in entry["env"], entry
        assert "--yes" not in entry["argv"] and "-y" not in entry["argv"], entry
    real = [e for e in entries if e["argv"][:1] == ["install"] and "--dry-run" not in e["argv"]]
    assert len(real) == 1 and real[0]["argv"] == ["install", first] and real[0]["tty"] is True
    dry = [e for e in entries if "--dry-run" in e["argv"]]
    assert dry and dry[0]["tty"] is False, "reads must never have a terminal"


def test_the_console_refuses_a_pipe(tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, "-m", "hammunition_console"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert done.returncode == 2 and "terminal" in done.stderr
```

Run: `python3 -m pytest tests/test_pty_install.py -v`
Expected: PASS (2 passed). This is the first run of the whole console under a real terminal. If `proc.expect(first)` times out, the failure prints the last screen: read it. The usual real findings: a screen's `on_show` not calling `redraw()` (the page stays blank), the `Install` word not matching because the Home rows are drawn before the loop's first render (expect a different anchor such as `Where to next`), or `urwid.Terminal` needing the main loop's screen to be started before construction (the pane is only built after `R`, so the loop is running).

- [ ] **Step 4: Falsify the end-to-end consent test, then commit**

In `hammunition_console/screens/plan.py`, change `argv = self.ctx.engine.command(self.action, *self.names)` to append `"--yes"`: `argv = [*self.ctx.engine.command(self.action, *self.names), "--yes"]`. Run: `python3 -m pytest tests/test_plan.py tests/test_consent_guard.py -v`
Expected: FAIL: `Refused: the console never passes '--yes'` from `FakeContext.run_pane` and the grep test naming `hammunition_console/screens/plan.py`. Revert; re-run: PASS.

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the Install screen and the end-to-end install through a real pty"
```
Expected: clean, all pass.

---

### Task 11: Station

The Station screen shows the engine's saved values, hides the callsign, grid square, alias, region names and rig port until a key reveals them, and changes a value only by running the real `hammunition station set --FLAG=VALUE` in a pane. The value goes to the engine as one argv element and nowhere else: not to the console's config, a log, a crash report or the environment. It is read back from a fresh `station show --json` to confirm.

**Files:**
- Create: `hammunition_console/screens/station.py`
- Test: `tests/test_station.py`

**Interfaces:**
- Consumes: `screens.base.{Screen, Row, PromptScreen, text}`, `fmt.{clean, mask}`, `ctx.engine.command`, `ctx.run_pane`, `ctx.pop`.
- Produces: `station.Field(key, label, flag, secret=False, clear_flag=None, chooser=None)`; `station.FIELDS: tuple[Field, ...]`; `station.display_value(field, value, revealed) -> str`; `station.set_argv(engine_command, field, value) -> list[str]`; `station.ChooserScreen(ctx, title, load_items, selected, on_apply, note="")`; `station.StationScreen(ctx)` (`name = "station"`, `.revealed: bool`, `.note: str`).

- [ ] **Step 1: Write the tests (failing first)**

Create `tests/test_station.py`:

```python
from typing import Any

import pytest

from hammunition_console.config import Config
from hammunition_console.engine import EngineRefused
from hammunition_console.screens.base import PromptScreen
from hammunition_console.screens.station import FIELDS, ChooserScreen, StationScreen, display_value
from tests.helpers import FakeContext, FakeEngine, document, load, render

SENTINELS = {"callsign": "ZZ9SENTINEL", "grid_square": "ZZ99zz", "node_alias": "SENTALIAS",
             "rig_device": "/dev/serial/by-id/usb-SENTINELSERIAL-if00", "map_regions": ["north-america/us/sentinelregion"]}


def sentinel_ctx() -> FakeContext:
    body = {**load("station-set"), **SENTINELS}
    engine = FakeEngine()
    engine.set(("station", "show"), document("station", body))
    return FakeContext(engine=engine)


def shown(ctx: FakeContext) -> tuple[StationScreen, str]:
    screen = StationScreen(ctx)
    screen.on_show()
    return screen, render(screen.widget(), 100, 30)


def row_for(screen: StationScreen, key: str) -> Any:
    return next(r for r in screen._walker if getattr(r, "value", None) is not None and getattr(r.value, "key", None) == key)


def test_secret_values_are_hidden_until_revealed_and_hidden_again_on_leaving() -> None:
    screen, out = shown(sentinel_ctx())
    for secret in (*[v for v in SENTINELS.values() if isinstance(v, str)], "sentinelregion"):
        assert secret not in out, secret
    assert "1 set" in out  # the region count
    assert screen.keypress("v") is None and screen.revealed
    out = render(screen.widget(), 100, 30)
    assert "ZZ9SENTINEL" in out and "ZZ99zz" in out and "sentinelregion" in out
    screen.on_hide()
    assert screen.revealed is False and "ZZ9SENTINEL" not in render(screen.widget(), 100, 30)


def test_nothing_is_set_says_so() -> None:
    screen, out = shown(FakeContext(engine=FakeEngine(station="none")))
    assert out.count("not set") >= 4 and "Station values are saved by the engine" in out


def test_the_station_screen_stores_nothing_itself() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    screen.keypress("v")
    assert ctx.saved == 0 and ctx.config == Config()


@pytest.mark.parametrize("field,value,shown_as", [
    ("callsign", "N0CALL", "********"), ("map_regions", ["a", "b"], "2 set"), ("node_alias", None, "not set"),
    ("rig_baud", 38400, "38400"), ("mirror", "http://lan/", "http://lan/"), ("reference_books", [], "not set"),
])
def test_display_value(field: str, value: Any, shown_as: str) -> None:
    f = next(x for x in FIELDS if x.key == field)
    assert display_value(f, value, revealed=False) == shown_as


def test_revealed_lists_are_joined() -> None:
    f = next(x for x in FIELDS if x.key == "map_regions")
    assert display_value(f, ["a", "b"], revealed=True) == "a, b"


def test_setting_a_value_runs_station_set_with_one_argv_element_and_the_value_is_not_in_the_title() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "callsign").keypress((100,), "enter")
    prompt = ctx.pushed[-1]
    assert isinstance(prompt, PromptScreen)
    prompt._edit.set_edit_text("N0TST")
    prompt.keypress("enter")
    pane = ctx.panes[0]
    assert pane.argv == ["hammunition", "station", "set", "--callsign=N0TST"]
    assert "N0TST" not in pane.title and pane.title == "station set --callsign"


def test_a_value_that_looks_like_a_flag_stays_inside_one_argv_element() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "node_alias").keypress((100,), "enter")
    ctx.pushed[-1]._edit.set_edit_text("--clear-rig")
    ctx.pushed[-1].keypress("enter")
    assert ctx.panes[0].argv == ["hammunition", "station", "set", "--node-alias=--clear-rig"]


def test_an_empty_value_is_a_cancel() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "callsign").keypress((100,), "enter")
    ctx.pushed[-1].keypress("enter")
    assert ctx.panes == []


def test_after_the_pane_the_screen_reads_back_and_reports_the_engines_exit_code_not_its_own_opinion() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "node_alias").keypress((100,), "enter")
    ctx.pushed[-1]._edit.set_edit_text("X")
    ctx.pushed[-1].keypress("enter")
    reads_before = len([c for c in ctx.engine.calls if c == ("station", "show")])
    ctx.panes[0].on_exit(2)
    assert ctx.popped >= 1 and "exit 2" in screen.note and "its own words were in the pane" in screen.note
    ctx.panes[0].on_exit(0)
    assert "Saved" in screen.note
    screen.on_show()
    assert len([c for c in ctx.engine.calls if c == ("station", "show")]) > reads_before


def test_clearing_a_value_the_engine_can_clear() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    screen._walker.set_focus(screen._walker.index(row_for(screen, "mirror")))
    assert screen.keypress("c") is None
    assert ctx.panes[0].argv == ["hammunition", "station", "set", "--clear-mirror"]


def test_c_on_a_field_with_no_clear_flag_does_nothing() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    screen._walker.set_focus(screen._walker.index(row_for(screen, "callsign")))
    assert screen.keypress("c") == "c" and ctx.panes == []


def test_the_book_chooser_toggles_and_applies_one_comma_list() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "reference_books").keypress((100,), "enter")
    chooser = ctx.pushed[-1]
    assert isinstance(chooser, ChooserScreen)
    books = load("books")["books"]
    out = render(chooser.widget(), 110, 30)
    assert books[0]["id"] in out and books[0]["licence"][:10] in out
    assert chooser.keypress("A") is None and ctx.panes == [], "nothing selected: nothing runs"
    chooser._walker[chooser._walker.index(next(r for r in chooser._walker if getattr(r, "value", None) == books[0]["id"]))].keypress((100,), "enter")
    chooser._walker.set_focus(0)
    chosen = [b["id"] for b in books if b["chosen"]]
    assert chooser.keypress("A") is None
    expected = ",".join([*chosen, books[0]["id"]] if books[0]["id"] not in chosen else chosen)
    assert ctx.panes[0].argv == ["hammunition", "station", "set", f"--reference-books={expected}"]


def test_the_region_search_reads_maps_regions_and_applies_the_selection() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "map_regions").keypress((100,), "enter")
    prompt = ctx.pushed[-1]
    assert isinstance(prompt, PromptScreen)
    prompt._edit.set_edit_text("vermont")
    prompt.keypress("enter")
    chooser = ctx.pushed[-1]
    assert ("maps", "regions", "vermont") in ctx.engine.calls and isinstance(chooser, ChooserScreen)
    region = load("regions")["regions"][0]
    next(r for r in chooser._walker if getattr(r, "value", None) == region).keypress((100,), "enter")
    chooser.keypress("A")
    arg = ctx.panes[0].argv[-1]
    assert arg.startswith("--map-regions=") and region in arg and "sentinelregion" in arg  # replaces the whole list: the old one is kept


def test_a_region_search_term_that_looks_like_a_flag_is_refused_before_any_read() -> None:
    ctx = sentinel_ctx()
    screen, _ = shown(ctx)
    row_for(screen, "map_regions").keypress((100,), "enter")
    ctx.pushed[-1]._edit.set_edit_text("--help")
    ctx.pushed[-1].keypress("enter")
    assert not any(c[:2] == ("maps", "regions") for c in ctx.engine.calls)
    assert "does not start with '-'" in screen.note


def test_set_argv_is_one_element() -> None:
    from hammunition_console.screens.station import set_argv

    f = next(x for x in FIELDS if x.key == "callsign")
    assert set_argv(lambda *w: ["hammunition", *w], f, "N0TST") == ["hammunition", "station", "set", "--callsign=N0TST"]


def test_a_failed_read_is_shown_not_retried() -> None:
    engine = FakeEngine()
    engine.set(("station", "show"), EngineRefused(2, "no station file"))
    ctx = FakeContext(engine=engine)
    _, out = shown(ctx)
    assert "no station file" in out and engine.calls.count(("station", "show")) == 1


def test_engine_text_in_a_value_is_cleaned() -> None:
    ctx = sentinel_ctx()
    body = {**load("station-set"), "mirror": "http://lan/\x1b[2J"}
    ctx.engine.set(("station", "show"), document("station", body))
    assert "\x1b" not in shown(ctx)[1]
```

- [ ] **Step 2: Run it; confirm it fails; implement**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_station.py -v`
Expected: FAIL (`ModuleNotFoundError`).

Create `hammunition_console/screens/station.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import urwid

from hammunition_console.context import Context
from hammunition_console.engine import Document
from hammunition_console.fmt import clean, first_line, mask
from hammunition_console.screens.base import PromptScreen, Row, Screen, text


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    flag: str
    secret: bool = False
    clear_flag: str | None = None
    chooser: str | None = None


FIELDS: tuple[Field, ...] = (
    Field("callsign", "Callsign", "--callsign", secret=True),
    Field("grid_square", "Grid square", "--grid-square", secret=True),
    Field("node_alias", "Packet node alias", "--node-alias", secret=True),
    Field("map_regions", "Map regions", "--map-regions", secret=True, chooser="regions"),
    Field("map_freshness", "Map freshness", "--map-freshness"),
    Field("reference_books", "Kiwix books", "--reference-books", chooser="books"),
    Field("mirror", "LAN mirror", "--mirror", clear_flag="--clear-mirror"),
    Field("dem_source", "Elevation source", "--dem-source"),
    Field("rig", "Rig", "--rig", clear_flag="--clear-rig"),
    Field("rig_device", "Rig port", "--rig-device", secret=True),
    Field("rig_baud", "Rig baud rate", "--rig-baud"),
    Field("rig_ptt_line", "Rig PTT line", "--rig-ptt-line"),
    Field("rig_owner", "Rig owner", "--rig-owner"),
)


def display_value(field: Field, value: Any, revealed: bool) -> str:
    if value is None or value == []:
        return "not set"
    if isinstance(value, list):
        return ", ".join(clean(v) for v in value) if (revealed or not field.secret) else f"{len(value)} set"
    if field.secret and not revealed:
        return mask(str(value))
    return clean(value)


def set_argv(command: Callable[..., list[str]], field: Field, value: str) -> list[str]:
    """One argv element carries the flag and the value; it cannot be read as another flag."""
    return command("station", "set", f"{field.flag}={value}")


class ChooserScreen(Screen):
    """Pick several items from a list; capital A applies. Space and Enter toggle."""

    name = "chooser"

    def __init__(
        self,
        ctx: Context,
        title: str,
        load_items: Callable[[], list[tuple[str, str]]],
        selected: Sequence[str],
        on_apply: Callable[[list[str]], None],
        note: str = "",
    ) -> None:
        super().__init__(ctx)
        self.title = title
        self._load_items = load_items
        self.selected = list(selected)
        self._on_apply = on_apply
        self._note = note
        self._items: list[tuple[str, str]] = []
        self._hint = ""

    def on_show(self) -> None:
        self.load("items", self._load_items, self._store)
        self.redraw()

    def _store(self, items: list[tuple[str, str]]) -> None:
        known = {value for value, _ in items}
        self._items = [(v, v) for v in self.selected if v not in known] + items

    def redraw(self) -> None:
        rows: list[urwid.Widget] = [text(self._note, "dim"), text("Enter toggles; A applies the whole selection; b goes back and changes nothing.", "dim")]
        if self._hint:
            rows.append(text(self._hint, "warn"))
        if self.status.get("items") == "loading":
            rows.append(text("Loading..."))
        elif self.status.get("items") == "error":
            rows.append(text(self.errors["items"], "fail"))
        for value, label in self._items:
            row = Row(f"[{'x' if value in self.selected else ' '}] {label}", value)
            urwid.connect_signal(row, "activate", self._toggle)
            rows.append(row)
        self.set_rows(rows)

    def _toggle(self, row: Row) -> None:
        value = str(row.value)
        if value in self.selected:
            self.selected.remove(value)
        else:
            self.selected.append(value)
        self.redraw()

    def keypress(self, key: str) -> str | None:
        if key == "A":
            if not self.selected:
                self._hint = "Select at least one first. Nothing was run."
                self.redraw()
                return None
            self.ctx.pop()
            self._on_apply(list(self.selected))
            return None
        return key


class StationScreen(Screen):
    name = "station"
    title = "Station"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.revealed = False
        self.note = ""
        self._doc: Document | None = None

    def on_show(self) -> None:
        self.load("station", lambda: self.ctx.engine.read("station", "show"), lambda d: setattr(self, "_doc", d))
        self.redraw()

    def on_hide(self) -> None:
        self.revealed = False
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = [text("Station values are saved by the engine, never by this console. Enter changes one; v reveals or hides; c clears.", "dim")]
        if self.note:
            rows.append(text(self.note, "warn"))
        if self.status.get("station") == "error":
            rows.append(text(self.errors["station"], "fail"))
        elif self._doc is not None:
            for field in FIELDS:
                value = self._doc.body.get(field.key)
                row = Row(f"{field.label:<20} {display_value(field, value, self.revealed)}", field)
                urwid.connect_signal(row, "activate", self._edit)
                rows.append(row)
        else:
            rows.append(text("Reading the station..."))
        self.set_rows(rows)

    def keypress(self, key: str) -> str | None:
        if key == "v":
            self.revealed = not self.revealed
            self.redraw()
            return None
        if key == "c":
            field = self.focused_value()
            if isinstance(field, Field) and field.clear_flag:
                self._run(self.ctx.engine.command("station", "set", field.clear_flag), f"station set {field.clear_flag}")
                return None
        return key

    def _run(self, argv: list[str], title: str) -> None:
        self.ctx.run_pane(argv, title, self._after_set)

    def _after_set(self, code: int | None) -> None:
        self.note = ("Saved. The values below were read back from the engine." if code == 0 else
                     f"The engine exited with exit {code}; its own words were in the pane.")
        self.ctx.pop()

    def _field(self, key: str) -> Field:
        return next(f for f in FIELDS if f.key == key)

    def _edit(self, row: Row) -> None:
        field = row.value
        if not isinstance(field, Field):
            return
        if field.chooser == "books":
            self._choose_books()
        elif field.chooser == "regions":
            self.ctx.push(PromptScreen(self.ctx, "Search Geofabrik regions", "contains: ", self._search_regions,
                                       note="Part of a region name, for example: vermont"))
        else:
            self.ctx.push(PromptScreen(self.ctx, f"Set {field.label.lower()}", f"{field.label}: ",
                                       lambda value: self._set(field, value)))

    def _set(self, field: Field, value: str) -> None:
        if value:
            self._run(set_argv(self.ctx.engine.command, field, value), f"station set {field.flag}")

    def _current(self, key: str) -> list[str]:
        value = self._doc.body.get(key) if self._doc else None
        return [str(v) for v in value] if isinstance(value, list) else []

    def _choose_books(self) -> None:
        field = self._field("reference_books")

        def items() -> list[tuple[str, str]]:
            books = self.ctx.engine.read("reference", "books").body.get("books")
            return [(str(b["id"]), f"{b['id']}  {first_line(str(b.get('title') or ''))}  {b.get('licence') or ''}")
                    for b in books if isinstance(b, dict) and "id" in b] if isinstance(books, list) else []

        self.ctx.push(ChooserScreen(
            self.ctx, "Kiwix books", items, self._current("reference_books"),
            lambda ids: self._run(set_argv(self.ctx.engine.command, field, ",".join(ids)), f"station set {field.flag}"),
            note="Replaces the whole list. Each book's licence is shown before you choose."))

    def _search_regions(self, term: str) -> None:
        if not term:
            return
        if term.startswith("-"):
            self.note = "A search term does not start with '-'. Nothing was run."
            self.redraw()
            return
        field = self._field("map_regions")

        def items() -> list[tuple[str, str]]:
            found = self.ctx.engine.read("maps", "regions", term).body.get("regions")
            return [(str(r), str(r)) for r in found] if isinstance(found, list) else []

        self.ctx.push(ChooserScreen(
            self.ctx, f"Regions matching {term}", items, self._current("map_regions"),
            lambda ids: self._run(set_argv(self.ctx.engine.command, field, ",".join(ids)), f"station set {field.flag}"),
            note="Replaces the whole list; regions you already carry are kept ticked."))
```

Run: `python3 -m pytest tests/test_station.py -v`
Expected: PASS (all). The book-chooser test reads `books[0]` and `chosen` from the recorded `books.json`; if every book in your capture is already `chosen: false` the expected list is just that one id.

- [ ] **Step 3: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the Station screen: masked values, station set in a pane, read-back"
```
Expected: clean, all pass.

---

### Task 12: Logs

**Files:**
- Create: `hammunition_console/screens/logs.py`
- Test: `tests/test_logs.py`

**Interfaces:**
- Consumes: `screens.base.{Screen, Row, text}`, `fmt.{clean, first_line, human_size}`, `ctx.after`.
- Produces: `logs.is_inside(path: str, directory: str) -> bool`; `logs.read_tail(path: str, max_bytes: int = 65536) -> tuple[str, int]`; `logs.read_from(path: str, offset: int) -> tuple[str, int] | None` (`None` when the file is gone); `logs.LogsScreen(ctx)` (`name = "logs"`, `.note`); `logs.LogViewScreen(ctx, path, directory, running)` (`.lines: list[str]`, `.following: bool`, `.note`).

- [ ] **Step 1: Write the tests (failing first)**

Create `tests/test_logs.py`:

```python
import os
from pathlib import Path
from typing import Any

from hammunition_console.engine import EngineRefused
from hammunition_console.screens.logs import (
    LogsScreen, LogViewScreen, is_inside, read_from, read_tail,
)
from tests.helpers import FakeContext, FakeEngine, document, load, render


def logs_doc(directory: Path, *runs: dict[str, Any]) -> Any:
    return document("logs", {"directory": str(directory), "total_bytes": 0, "max_files": 30, "max_bytes": 1, "runs": list(runs)})


def run_entry(path: Path, result: str = "ok", code: int | None = 0, command: str = "install") -> dict[str, Any]:
    return {"path": str(path), "started": "2026-10-03T14:02:11Z", "command": command, "pid": 1, "size": 1, "result": result, "exit_code": code}


def ctx_for(doc: Any) -> FakeContext:
    engine = FakeEngine()
    engine.set(("logs",), doc)
    return FakeContext(engine=engine)


def test_the_list_shows_every_result_word_newest_first() -> None:
    screen = LogsScreen(FakeContext())
    screen.on_show()
    out = render(screen.widget(), 110, 20)
    runs = load("logs")["runs"]
    assert [r["result"] for r in runs] == ["running", "ok", "failed", "refused", "not confirmed", "incomplete"]
    data = [line for line in out.splitlines() if any(r["command"] in line and r["result"] in line for r in runs)]
    assert len(data) == len(runs) and "running" in data[0] and "incomplete" in data[-1]
    assert "None" not in out


def test_a_null_exit_code_is_a_dash() -> None:
    screen = LogsScreen(FakeContext())
    screen.on_show()
    running = next(l for l in render(screen.widget(), 110, 20).splitlines() if "running" in l)
    assert running.rstrip().endswith("-")


def test_an_empty_log_and_a_failed_read() -> None:
    ctx = ctx_for(logs_doc(Path("/x")))
    screen = LogsScreen(ctx)
    screen.on_show()
    assert "No runs yet" in render(screen.widget(), 100, 10)
    engine = FakeEngine()
    engine.set(("logs",), EngineRefused(2, "no log dir"))
    screen = LogsScreen(FakeContext(engine=engine))
    screen.on_show()
    assert "no log dir" in render(screen.widget(), 100, 10)


def open_first(tmp_path: Path, name: str = "a.log", body: str = "line one\nline two\n", result: str = "ok") -> tuple[LogsScreen, FakeContext, Path]:
    logdir = tmp_path / "logs"
    logdir.mkdir()
    log = logdir / name
    log.write_text(body)
    ctx = ctx_for(logs_doc(logdir, run_entry(log, result, 0 if result == "ok" else None)))
    screen = LogsScreen(ctx)
    screen.on_show()
    next(r for r in screen._walker if getattr(r, "value", None)).keypress((100,), "enter")
    return screen, ctx, log


def test_enter_opens_the_file_the_engine_listed(tmp_path: Path) -> None:
    _, ctx, _ = open_first(tmp_path)
    view = ctx.pushed[-1]
    assert isinstance(view, LogViewScreen)
    assert "line two" in render(view.widget(), 80, 10) and view.following is False and ctx.timers == []


def test_log_text_is_cleaned_of_control_sequences(tmp_path: Path) -> None:
    _, ctx, _ = open_first(tmp_path, body="ok\x1b[2J\x1b]0;pwned\x07done\n")
    out = render(ctx.pushed[-1].widget(), 80, 10)
    assert "\x1b" not in out and "\x07" not in out and "done" in out


def test_invalid_utf8_in_a_log_is_tolerated(tmp_path: Path) -> None:
    logdir = tmp_path / "l"
    logdir.mkdir()
    log = logdir / "b.log"
    log.write_bytes(b"good\n\xff\xfe bad bytes\nafter\n")
    text, _ = read_tail(str(log))
    assert "good" in text and "after" in text


def test_only_the_last_64k_are_read(tmp_path: Path) -> None:
    log = tmp_path / "big.log"
    log.write_text("".join(f"row {i:06d}\n" for i in range(40000)))
    text, size = read_tail(str(log))
    assert size == log.stat().st_size and "row 039999" in text and "row 000000" not in text
    assert len(text) <= 70000 and text.startswith("row ")  # the partial first line is dropped


def test_refuses_a_path_outside_the_log_directory(tmp_path: Path) -> None:
    logdir = tmp_path / "logs"
    logdir.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    (logdir / "link.log").symlink_to(outside)
    (logdir / "real.log").write_text("x")
    assert is_inside(str(logdir / "real.log"), str(logdir))
    assert not is_inside(str(logdir / "link.log"), str(logdir)), "a symlink out of the directory"
    assert not is_inside(str(logdir / ".." / "secret.txt"), str(logdir))
    assert not is_inside(str(outside), str(logdir))
    assert not is_inside(str(logdir), str(logdir)), "the directory itself"
    assert not is_inside(str(logdir / "missing.log"), str(logdir)), "must be an existing regular file"
    assert not is_inside(str(tmp_path / "logs-evil" / "x"), str(logdir)), "a sibling with the same prefix"


def test_the_list_refuses_to_open_a_path_that_escapes(tmp_path: Path) -> None:
    logdir = tmp_path / "logs"
    logdir.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    ctx = ctx_for(logs_doc(logdir, run_entry(secret)))
    screen = LogsScreen(ctx)
    screen.on_show()
    next(r for r in screen._walker if getattr(r, "value", None)).keypress((100,), "enter")
    assert ctx.pushed == [] and "not inside the log directory" in screen.note
    assert "not inside the log directory" in render(screen.widget(), 100, 10)


def test_a_running_log_is_followed_and_new_lines_appear(tmp_path: Path) -> None:
    _, ctx, log = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]
    assert view.following and len(ctx.timers) == 1 and ctx.timers[0][0] == 1.0
    with open(log, "a") as handle:
        handle.write("a new line\n")
    ctx.timers.pop()[1]()
    assert "a new line" in render(view.widget(), 80, 10) and len(ctx.timers) == 1


def test_leaving_the_view_stops_the_following(tmp_path: Path) -> None:
    _, ctx, _ = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]
    view.on_hide()
    ctx.timers.pop()[1]()
    assert ctx.timers == [] and view.following is False


def test_a_log_deleted_by_rotation_while_open_is_a_calm_note_not_a_traceback(tmp_path: Path) -> None:
    _, ctx, log = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]
    log.unlink()
    ctx.timers.pop()[1]()
    assert "rotated away" in view.note and ctx.timers == [] and view.following is False
    assert "rotated away" in render(view.widget(), 80, 10)


def test_a_truncated_log_is_reread(tmp_path: Path) -> None:
    _, ctx, log = open_first(tmp_path, body="old old old old old old old\n" * 20, result="running")
    view = ctx.pushed[-1]
    log.write_text("fresh\n")
    ctx.timers.pop()[1]()
    assert "truncated" in view.note and "fresh" in render(view.widget(), 80, 10)


def test_read_from_returns_only_new_text_and_none_when_gone(tmp_path: Path) -> None:
    log = tmp_path / "x.log"
    log.write_text("abc\n")
    text, offset = read_from(str(log), 0) or ("", 0)
    assert text == "abc\n" and offset == 4
    assert read_from(str(log), 4) == ("", 4)
    log.unlink()
    assert read_from(str(log), 4) is None


def test_a_view_never_holds_more_than_the_line_cap(tmp_path: Path) -> None:
    _, ctx, log = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]
    with open(log, "a") as handle:
        handle.write("".join(f"l{i}\n" for i in range(6000)))
    ctx.timers.pop()[1]()
    assert len(view.lines) <= 5000 and view.lines[-1] == "l5999"
```

- [ ] **Step 2: Run it; confirm it fails; implement**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_logs.py -v`
Expected: FAIL (`ModuleNotFoundError`).

Create `hammunition_console/screens/logs.py`:

```python
"""The engine's run logs: a list from `logs --json`, and a viewer for one file. The
viewer opens only a path the engine listed that lies inside the directory it
reported, and shows file text as inert text (every control character removed)."""

from __future__ import annotations

import os
from typing import Any

import urwid

from hammunition_console.context import Context
from hammunition_console.engine import Document
from hammunition_console.fmt import clean, first_line, human_size
from hammunition_console.screens.base import Row, Screen, text

TAIL_BYTES = 65536
MAX_LINES = 5000
FOLLOW_SECONDS = 1.0


def is_inside(path: str, directory: str) -> bool:
    """True only for an existing regular file strictly below the directory, symlinks resolved."""
    real, base = os.path.realpath(path), os.path.realpath(directory)
    try:
        if os.path.commonpath([real, base]) != base or real == base:
            return False
    except ValueError:
        return False
    return os.path.isfile(real)


def read_tail(path: str, max_bytes: int = TAIL_BYTES) -> tuple[str, int]:
    with open(path, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        start = max(0, size - max_bytes)
        handle.seek(start)
        data = handle.read()
    content = data.decode("utf-8", errors="replace")
    if start > 0 and "\n" in content:
        content = content.split("\n", 1)[1]
    return content, size


def read_from(path: str, offset: int) -> tuple[str, int] | None:
    try:
        with open(path, "rb") as handle:
            handle.seek(offset)
            data = handle.read()
    except FileNotFoundError:
        return None
    return data.decode("utf-8", errors="replace"), offset + len(data)


class LogViewScreen(Screen):
    name = "logview"

    def __init__(self, ctx: Context, path: str, directory: str, running: bool) -> None:
        super().__init__(ctx)
        self.title = f"Log: {os.path.basename(path)}"
        self._path, self._directory = path, directory
        self.following = running
        self.note = ""
        self.lines: list[str] = []
        self._offset = 0
        self._started = False

    def on_show(self) -> None:
        if not self._started:
            self._started = True
            try:
                content, self._offset = read_tail(self._path)
            except OSError as exc:
                self.note = f"Could not read the log: {exc.strerror}"
                self.following = False
            else:
                self._append(content)
            if self.following:
                self.ctx.after(FOLLOW_SECONDS, self._tick)
        self.redraw()

    def on_hide(self) -> None:
        self.following = False

    def _append(self, content: str) -> None:
        self.lines += [clean(line) for line in content.splitlines()]
        del self.lines[:-MAX_LINES]

    def _tick(self) -> None:
        if not self.following:
            return
        if not is_inside(self._path, self._directory):
            self.note, self.following = "The log was rotated away; no longer following.", False
            self.redraw()
            return
        chunk = read_from(self._path, self._offset)
        if chunk is None:
            self.note, self.following = "The log was rotated away; no longer following.", False
        else:
            content, new_offset = chunk
            if new_offset < self._offset or (os.path.getsize(self._path) < self._offset):
                self.note, self.lines = "The log was truncated; showing it again from the end.", []
                content, new_offset = read_tail(self._path)
            self._offset = new_offset
            self._append(content)
            self.ctx.after(FOLLOW_SECONDS, self._tick)
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self.note:
            rows.append(text(self.note, "warn"))
        rows += [text(line) for line in self.lines] or [text("(empty)", "dim")]
        self.set_rows(rows)
        if self.following and len(self._walker):
            self._walker.set_focus(len(self._walker) - 1)


class LogsScreen(Screen):
    name = "logs"
    title = "Logs"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.note = ""
        self._doc: Document | None = None

    def on_show(self) -> None:
        self.load("logs", lambda: self.ctx.engine.read("logs"), lambda d: setattr(self, "_doc", d))
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self.note:
            rows.append(text(self.note, "warn"))
        if self.status.get("logs") == "error":
            rows.append(text(self.errors["logs"], "fail"))
        elif self._doc is not None:
            runs = [r for r in (self._doc.body.get("runs") or []) if isinstance(r, dict)]
            if not runs:
                rows.append(text("No runs yet."))
            for run in runs:
                code = run.get("exit_code")
                row = Row(f"{run.get('started') or '':<22} {run.get('command') or '?':<18} {run.get('result') or '?':<14} "
                          f"{human_size(run['size']) if isinstance(run.get('size'), int) else '':>9}  "
                          f"{code if isinstance(code, int) else '-'}", run)
                urwid.connect_signal(row, "activate", self._open)
                rows.append(row)
        else:
            rows.append(text("Reading the run logs..."))
        self.set_rows(rows)

    def _open(self, row: Row) -> None:
        run: Any = row.value
        directory = str(self._doc.body.get("directory", "")) if self._doc else ""
        path = run.get("path") if isinstance(run, dict) else None
        if not isinstance(path, str) or not directory or not is_inside(path, directory):
            self.note = f"Refused: {first_line(str(path))} is not inside the log directory the engine reported."
            self.redraw()
            return
        self.note = ""
        self.ctx.push(LogViewScreen(self.ctx, path, directory, running=run.get("result") == "running"))
```

Run: `python3 -m pytest tests/test_logs.py -v`
Expected: PASS (all). The test asserting "not inside the log directory" matches the note text above ("is not inside the log directory the engine reported").

- [ ] **Step 3: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the Logs screen: the run list, a contained viewer, live follow"
```
Expected: clean, all pass.

---

### Task 13: Update

**Files:**
- Create: `hammunition_console/screens/update.py`
- Test: `tests/test_update.py`

**Interfaces:**
- Consumes: `guard.apt_upgrade_argv`, `screens.base.{Screen, Row, ConfirmScreen, text}`, `screens.plan.PlanScreen`, `ctx.run_pane`.
- Produces: `update.rebuild_names(command: str | None) -> list[str] | None`; `update.counts_text(counts: Mapping[str, Any]) -> str`; `update.UpdateScreen(ctx, names: Sequence[str] = ())` (`name = "update"`, `.upstream: bool`, `.note`).

- [ ] **Step 1: Write the tests (failing first)**

Create `tests/test_update.py`:

```python
from typing import Any

import pytest

from hammunition_console.engine import EngineRefused
from hammunition_console.screens.base import ConfirmScreen
from hammunition_console.screens.plan import PlanScreen
from hammunition_console.screens.update import UpdateScreen, counts_text, rebuild_names
from tests.helpers import FakeContext, FakeEngine, document, load, render


def shown(ctx: FakeContext | None = None, **kw: Any) -> tuple[UpdateScreen, FakeContext, str]:
    ctx = ctx or FakeContext()
    screen = UpdateScreen(ctx, **kw)
    screen.on_show()
    return screen, ctx, render(screen.widget(), 110, 30)


def test_the_report_lists_each_unit_with_its_state_and_the_lists_age() -> None:
    _, _, out = shown()
    doc = load("update-all")
    for row in doc["rows"]:
        assert row["unit"] in out and row["state"] in out
    assert doc["lists_note"] in out
    assert counts_text(doc["counts"]) in out and "None" not in out


def test_an_unknown_state_word_is_shown_verbatim() -> None:
    engine = FakeEngine()
    doc = load("update-all")
    doc["rows"][0]["state"] = "quarantined"
    engine.set(("update",), document("update", doc))
    assert "quarantined" in shown(FakeContext(engine=engine))[2]


def test_counts_text_tolerates_missing_keys() -> None:
    assert counts_text({}) == "counts unknown"
    assert "1 up to date" in counts_text({"up_to_date": 1})


def test_capital_a_confirms_then_runs_apt_in_a_pane_without_the_assume_yes() -> None:
    screen, ctx, _ = shown()
    assert screen.keypress("A") is None
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    assert "sudo apt-get install --only-upgrade --no-remove -- fixture-apt" in render(confirm.widget(), 110, 10)
    assert ctx.panes == [], "nothing runs until the person presses R on the confirm screen"
    confirm.keypress("R")
    assert ctx.panes[0].argv == ["sudo", "apt-get", "install", "--only-upgrade", "--no-remove", "--", "fixture-apt"]


def test_a_missing_or_unexpected_apt_command_is_shown_as_text_and_never_run() -> None:
    engine = FakeEngine()
    doc = load("update-all")
    doc["upgrade_command"] = None
    engine.set(("update",), document("update", doc))
    screen, ctx, _ = shown(FakeContext(engine=engine))
    screen.keypress("A")
    assert ctx.pushed == [] and "No apt upgrade is offered" in screen.note
    doc["upgrade_command"] = "sudo rm -rf / --yes"
    engine.set(("update",), document("update", doc))
    screen.on_show()
    screen.keypress("A")
    assert ctx.pushed == [] and ctx.panes == [] and "run it yourself" in screen.note and "sudo rm -rf" in screen.note


def test_capital_b_goes_through_the_plan_for_the_units_behind_the_pin() -> None:
    screen, ctx, _ = shown()
    assert screen.keypress("B") is None
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and (plan.action, plan.names) == ("install", ["acarsdec"])
    assert ctx.panes == []


@pytest.mark.parametrize("command,expected", [
    ("hammunition install a b", ["a", "b"]), ("hammunition install osm-regions osm-navit", ["osm-regions", "osm-navit"]),
    (None, None), ("", None), ("hammunition install", None), ("hammunition install a; rm x", None),
    ("hammunition install $(id)", None), ("sudo hammunition install a", None), ("hammunition uninstall a", None),
    ("hammunition install -y a", None), ("hammunition install 'a b'", None), ("hammunition install a 'b", None),
])
def test_rebuild_names_accepts_only_the_exact_shape(command: str | None, expected: list[str] | None) -> None:
    assert rebuild_names(command) == expected


def test_an_unexpected_rebuild_command_is_not_planned() -> None:
    engine = FakeEngine()
    doc = load("update-all")
    doc["rebuild_command"] = "hammunition install a; echo pwned"
    engine.set(("update",), document("update", doc))
    screen, ctx, _ = shown(FakeContext(engine=engine))
    screen.keypress("B")
    assert ctx.pushed == [] and "run it yourself" in screen.note


def test_lowercase_u_adds_upstream_and_asks_again() -> None:
    screen, ctx, _ = shown()
    assert screen.keypress("u") is None and screen.upstream is True
    assert ctx.engine.calls[-1] == ("update", "--upstream")
    assert "asks GitHub" in render(screen.widget(), 110, 30)
    screen.keypress("u")
    assert ctx.engine.calls[-1] == ("update",)


def test_upstream_rows_are_shown_when_the_report_has_them() -> None:
    engine = FakeEngine()
    doc = load("update-all")
    doc["upstream"] = [{"unit": "linbpq", "method": "git_tags", "catalog": "25.39", "upstream": None, "state": "unanswered", "detail": None}]
    engine.set(("update", "--upstream"), document("update", doc))
    screen, _, _ = shown(FakeContext(engine=engine))
    screen.keypress("u")
    out = render(screen.widget(), 110, 30)
    assert "linbpq" in out and "unanswered" in out and "None" not in out


def test_without_e2_the_engines_refusal_is_shown_and_a_per_profile_list_is_offered() -> None:
    screen, ctx, out = shown(FakeContext(engine=FakeEngine(suffix="-without")))
    assert "retired" in out and "the engine refused (exit 2)" in out and "Update by profile" in out
    profile = load("list-all-without")["profiles"][0]["name"]
    assert profile in out
    next(r for r in screen._walker if getattr(r, "value", None) == profile).keypress((100,), "enter")
    nested = ctx.pushed[-1]
    assert isinstance(nested, UpdateScreen) and nested.names == [profile]
    assert ctx.engine.calls[-1] == ("update", profile)


def test_a_profile_report_reads_update_with_the_names() -> None:
    _, ctx, out = shown(names=["station"])
    assert ctx.engine.calls[0] == ("update", "station")
    assert load("update-profile")["rows"][0]["unit"] in out


def test_engine_text_is_cleaned() -> None:
    engine = FakeEngine()
    engine.set(("update",), EngineRefused(2, "\x1b[2Jbroken"))
    assert "\x1b" not in shown(FakeContext(engine=engine))[2]
```

- [ ] **Step 2: Run it; confirm it fails; implement**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_update.py -v`
Expected: FAIL (`ModuleNotFoundError`).

Create `hammunition_console/screens/update.py`:

```python
"""Installed versus the catalog (D-053), as the engine reports it. The apt upgrade the
report offers runs in a pane (apt shows what it will change and asks); the rebuilds go
through the same plan screen as any install, so they too are planned first."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, Sequence
from typing import Any

import urwid

from hammunition_console.context import Context
from hammunition_console.engine import Document
from hammunition_console.fmt import clean
from hammunition_console.guard import apt_upgrade_argv
from hammunition_console.screens.base import ConfirmScreen, Row, Screen, text
from hammunition_console.screens.plan import PlanScreen

_UNIT = re.compile(r"^[a-z0-9][a-z0-9._+-]*$")
_COUNT_LABELS = (("up_to_date", "up to date"), ("candidate_differs", "with a different apt candidate"),
                 ("behind_pin", "behind the catalog's pin"), ("not_installed", "not installed"),
                 ("unknown", "unknown"), ("on_install", "re-checked on install"), ("manual", "manual"))
_ATTR = {"up to date": "ok", "behind the pin": "warn", "candidate differs": "warn", "retired": "fail"}


def rebuild_names(command: str | None) -> list[str] | None:
    """The unit names in `hammunition install NAME...`, or None unless it is exactly that."""
    if not command:
        return None
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    names = words[2:]
    if words[:2] != ["hammunition", "install"] or not names or not all(_UNIT.match(n) for n in names):
        return None
    return names


def counts_text(counts: Mapping[str, Any]) -> str:
    parts = [f"{counts[key]} {label}" for key, label in _COUNT_LABELS if isinstance(counts.get(key), int)]
    return ", ".join(parts) if parts else "counts unknown"


class UpdateScreen(Screen):
    name = "update"

    def __init__(self, ctx: Context, names: Sequence[str] = ()) -> None:
        super().__init__(ctx)
        self.names = list(names)
        self.title = "Update" + (f": {' '.join(self.names)}" if self.names else "")
        self.upstream = False
        self.note = ""
        self._doc: Document | None = None
        self._catalog: Document | None = None

    def on_show(self) -> None:
        self._doc = None
        words = ["update", *self.names] + (["--upstream"] if self.upstream else [])
        self.load("update", lambda: self.ctx.engine.read(*words), lambda d: setattr(self, "_doc", d))
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self.note:
            rows.append(text(self.note, "warn"))
        if self.status.get("update") == "loading":
            rows.append(text("Comparing (nothing is run, nothing is fetched)..."))
        elif self.status.get("update") == "error":
            rows += [text(self.errors["update"], "fail"), text("")]
            if not self.names:
                rows += self._by_profile()
        elif self._doc is not None:
            rows += self._report(self._doc.body)
        self.set_rows(rows)

    def _by_profile(self) -> list[urwid.Widget]:
        if self._catalog is None:
            self.ctx.bg.submit(lambda: self.ctx.engine.read("list"), self._catalog_loaded)
            return [text("Update by profile instead (reading the profiles)...")]
        rows: list[urwid.Widget] = [text("Update by profile instead (Enter):", "key")]
        for entry in self._catalog.body.get("profiles") or []:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                row = Row(f"  {clean(entry['name'])}", entry["name"])
                urwid.connect_signal(row, "activate", self._open_profile)
                rows.append(row)
        return rows

    def _catalog_loaded(self, doc: Document | None, error: BaseException | None) -> None:
        if doc is not None:
            self._catalog = doc
            self.redraw()

    def _open_profile(self, row: Row) -> None:
        self.ctx.push(UpdateScreen(self.ctx, names=[str(row.value)]))

    def _report(self, body: Mapping[str, Any]) -> list[urwid.Widget]:
        counts = body.get("counts")
        rows: list[urwid.Widget] = [text(counts_text(counts if isinstance(counts, dict) else {})),
                                    text(str(body.get("lists_note") or ""), "dim"),
                                    text("A run the apt upgrade   B plan the rebuilds   u also ask upstream (asks GitHub, git hosts and PyPI; off by default)", "key"),
                                    text("")]
        for row in body.get("rows") or []:
            if isinstance(row, dict):
                state = str(row.get("state") or "?")
                rows.append(text(f"{clean(row.get('unit') or '?'):<26} {clean(state):<20} {clean(row.get('detail') or '')}", _ATTR.get(state)))
        upstream = body.get("upstream")
        if isinstance(upstream, list):
            rows += [text(""), text("Upstream (the catalog's pin against what upstream publishes):", "key")]
            for row in upstream:
                if isinstance(row, dict):
                    rows.append(text(f"{clean(row.get('unit') or '?'):<22} {clean(row.get('state') or '?'):<18} "
                                     f"catalog {clean(row.get('catalog') or '?')}  upstream {clean(row.get('upstream') or 'unanswered')}"))
        return rows

    def _command(self, key: str) -> str | None:
        value = self._doc.body.get(key) if self._doc else None
        return value if isinstance(value, str) else None

    def keypress(self, key: str) -> str | None:
        if key == "u":
            self.upstream = not self.upstream
            self.on_show()
            return None
        if key == "A":
            self._offer_upgrade()
            return None
        if key == "B":
            self._offer_rebuild()
            return None
        return key

    def _offer_upgrade(self) -> None:
        command = self._command("upgrade_command")
        if command is None:
            self.note = "No apt upgrade is offered."
        elif (argv := apt_upgrade_argv(command)) is None:
            self.note = f"The upgrade command is not in the shape the console runs; run it yourself: {first(command)}"
        else:
            self.note = ""
            self.ctx.push(ConfirmScreen(
                self.ctx, "Upgrade apt packages",
                ["This runs in a terminal pane; apt shows what it will change and asks you first:", "", "  " + " ".join(argv)],
                lambda: self.ctx.run_pane(argv, "apt upgrade", lambda code: self.ctx.pop())))
            return
        self.redraw()

    def _offer_rebuild(self) -> None:
        command = self._command("rebuild_command")
        names = rebuild_names(command)
        if command is None:
            self.note = "Nothing is behind the pin."
        elif names is None:
            self.note = f"The rebuild command is not in the shape the console plans; run it yourself: {first(command)}"
        else:
            self.note = ""
            self.ctx.push(PlanScreen(self.ctx, "install", names))
            return
        self.redraw()


def first(command: str) -> str:
    return clean(command)[:200]
```

Run: `python3 -m pytest tests/test_update.py -v`
Expected: PASS (all). The upgrade test asserts the confirm screen shows `sudo apt-get install --only-upgrade --no-remove -- fixture-apt`, which is `apt_upgrade_argv` of the fixture's `upgrade_command`.

- [ ] **Step 3: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the Update screen: the report, upstream opt-in, apt upgrade and planned rebuilds"
```
Expected: clean, all pass.

---

### Task 14: Help, profile documentation, the man page, and the screen registry

**Files:**
- Create: `hammunition_console/screens/help.py`, `man/hammunition-console.1`
- Modify: `hammunition_console/helptext.py` (add `SCREEN_HELP`, `NEVER`), `hammunition_console/screens/install.py` (add the `i` key)
- Test: `tests/test_help.py`, `tests/test_man_and_registry.py`

**Interfaces:**
- Consumes: `helptext.{KEYS, EXIT_CODES}`, `screens.base.*`, `app.build_registry/SCREEN_CLASSES`.
- Produces: `helptext.SCREEN_HELP: dict[str, tuple[str, ...]]` (keys `home install plan station logs update help`), `helptext.NEVER: tuple[str, ...]`; `help.HelpScreen(ctx, about: str = "")` (`name = "help"`); `help.ProfileDocsScreen(ctx, profile: str)` (`name = "profile"`); `help.profile_lines(doc_body) -> list[str]`.

- [ ] **Step 1: Write the tests (failing first)**

Create `tests/test_help.py`:

```python
import json
from pathlib import Path

from hammunition_console.engine import EngineRefused
from hammunition_console.helptext import KEYS, NEVER, SCREEN_HELP
from hammunition_console.screens.help import HelpScreen, ProfileDocsScreen, profile_lines
from hammunition_console.screens.install import InstallScreen
from tests.helpers import FakeContext, FakeEngine, document, load, render


def help_out(about: str = "", ctx: FakeContext | None = None) -> tuple[HelpScreen, FakeContext, str]:
    ctx = ctx or FakeContext()
    screen = HelpScreen(ctx, about=about)
    screen.on_show()
    return screen, ctx, render(screen.widget(), 110, 60)


def test_help_lists_every_key_and_what_the_console_never_does() -> None:
    _, _, out = help_out()
    for keys, meaning in KEYS:
        assert keys in out and meaning[:30] in out
    for line in NEVER:
        assert line[:40] in out


def test_help_opens_with_the_page_you_came_from() -> None:
    _, _, out = help_out("install")
    assert SCREEN_HELP["install"][0] in out and out.index(SCREEN_HELP["install"][0]) < out.index("Keys")


def test_an_unknown_origin_shows_just_the_general_help() -> None:
    _, _, out = help_out("pane")
    assert "Keys" in out


def test_every_screen_has_help_text() -> None:
    assert set(SCREEN_HELP) >= {"home", "install", "plan", "station", "logs", "update", "help"}
    assert all(lines for lines in SCREEN_HELP.values())


def test_profiles_are_listed_and_enter_opens_their_documentation() -> None:
    screen, ctx, out = help_out()
    first = load("list-all")["profiles"][0]["name"]
    assert first in out
    next(r for r in screen._walker if getattr(r, "value", None) == first).keypress((100,), "enter")
    docs = ctx.pushed[-1]
    assert isinstance(docs, ProfileDocsScreen) and docs.profile == first


def test_a_failed_profile_list_is_shown_and_the_rest_still_works() -> None:
    engine = FakeEngine()
    engine.set(("list",), EngineRefused(2, "no catalog"))
    _, _, out = help_out(ctx=FakeContext(engine=engine))
    assert "no catalog" in out and "Keys" in out


def test_profile_documentation_shows_the_five_fields_and_the_gate_text_without_the_variable_name() -> None:
    ctx = FakeContext()
    name = json.loads((Path(__file__).parent / "fixtures" / "manifest.json").read_text())["gated"]
    screen = ProfileDocsScreen(ctx, name)
    screen.on_show()
    out = render(screen.widget(), 110, 60)
    doc = load("show-gated")
    for key in ("what_it_installs", "why_together", "deliberately_excludes", "manual_configuration"):
        assert doc["documentation"][key][:30] in out
    assert doc["consent"]["disclosure"].splitlines()[0][:40] in out and "type yes" in out
    assert doc["consent"]["env_var"] not in out and "HAMMUNITION_ACCEPT" not in out


def test_null_documentation_never_prints_none() -> None:
    lines = profile_lines({"name": "p", "summary": None, "stage": None, "packages": None, "suggests_one_of": None,
                           "consent": None, "documentation": {"what_it_installs": None, "why_together": None,
                                                              "deliberately_excludes": None, "manual_configuration": None,
                                                              "disk_footprint_hint": None}})
    assert "None" not in "\n".join(lines)


def test_suggestions_are_shown() -> None:
    lines = profile_lines({"name": "p", "documentation": {}, "suggests_one_of": [
        {"name": "logger", "reason": "pick one", "options": ["a", "b"], "recommended": "a", "detect_commands": []}]})
    assert any("logger" in l and "a, b" in l and "recommended a" in l for l in lines)


def test_install_i_opens_the_focused_profiles_documentation() -> None:
    ctx = FakeContext()
    install = InstallScreen(ctx)
    install.on_show()
    row = next(r for r in install._walker if getattr(r, "value", None) and r.value[0] == "profile")
    install._walker.set_focus(install._walker.index(row))
    assert install.keypress("i") is None
    assert isinstance(ctx.pushed[-1], ProfileDocsScreen) and ctx.pushed[-1].profile == row.value[1]["name"]


def test_profile_docs_error_is_shown() -> None:
    engine = FakeEngine()
    engine.set(("show", "x"), EngineRefused(2, "no such profile"))
    screen = ProfileDocsScreen(FakeContext(engine=engine), "x")
    screen.on_show()
    assert "no such profile" in render(screen.widget(), 100, 10)


def test_engine_text_is_cleaned() -> None:
    engine = FakeEngine()
    engine.set(("show", "x"), document("profile", {"name": "x", "summary": "s\x1b[2J", "stage": "1.0", "packages": [],
                                                   "documentation": {}, "consent": None, "suggests_one_of": []}))
    screen = ProfileDocsScreen(FakeContext(engine=engine), "x")
    screen.on_show()
    assert "\x1b" not in render(screen.widget(), 100, 10)
```

Create `tests/test_man_and_registry.py`:

```python
from pathlib import Path

import pytest

from hammunition_console.app import SCREEN_CLASSES, build_registry
from hammunition_console.helptext import EXIT_CODES, KEYS
from tests.helpers import FakeContext

ROOT = Path(__file__).resolve().parent.parent
MAN = (ROOT / "man" / "hammunition-console.1").read_text().replace("\\-", "-").replace("\\fB", "").replace("\\fR", "").replace("\\fI", "")


def test_the_man_page_documents_every_key_every_exit_code_and_the_config_file() -> None:
    for keys, _ in KEYS:
        assert keys in MAN, f"man page lacks key {keys!r}"
    for code, _ in EXIT_CODES:
        assert f"\n{code}\n" in MAN or f" {code} " in MAN or f"{code}  " in MAN, f"exit code {code}"
    assert "config.toml" in MAN and "crash.log" in MAN and ".TH HAMMUNITION-CONSOLE 1" in MAN


def test_the_man_page_names_what_it_never_does() -> None:
    assert "never" in MAN.lower() and "consent" in MAN.lower()


@pytest.mark.parametrize("name", sorted(SCREEN_CLASSES))
def test_every_registered_screen_resolves_and_builds(name: str) -> None:
    screen = build_registry()[name](FakeContext())
    assert screen.name == name

```
- [ ] **Step 2: Run them; confirm they fail**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_help.py tests/test_man_and_registry.py -v`
Expected: FAIL (`ImportError` on `SCREEN_HELP`, then `FileNotFoundError` for the man page).

- [ ] **Step 3: Add the help text (no consent tokens: the grep test reads this file)**

Append to `hammunition_console/helptext.py`:

```python
SCREEN_HELP: dict[str, tuple[str, ...]] = {
    "home": (
        "Home shows what needs attention: the engine's own health check, whether your station is set, the last run and "
        "how many units are behind the catalog's pin. Enter on the health line lists each check and the engine's "
        "suggested fix; the console shows a fix and never runs one.",
    ),
    "install": (
        "Install lists the engine's profiles (a profile is a named bundle) and, with Tab, its single units. Enter opens "
        "the plan: everything the engine will do, before anything runs. G marks a profile that asks you to type yes first.",
        "A name you type in the box is handed to the engine as it is; the engine decides whether it exists.",
    ),
    "plan": (
        "The plan is the engine's own dry run. Nothing has changed while you read it. R runs the real command in a "
        "terminal pane, where sudo, the group choice and any typed yes are the engine's, answered by you. b goes back "
        "and changes nothing.",
    ),
    "station": (
        "Station shows the values the engine saved. Callsign, grid square, alias, regions and the rig port stay hidden "
        "until you press v. Enter changes one by running the engine's own station set command; the console keeps no "
        "copy and writes the value nowhere itself.",
    ),
    "logs": (
        "Logs lists every run the engine recorded, newest first, with its result in the engine's own words. Enter opens "
        "the file; a run that is still going is followed live.",
    ),
    "update": (
        "Update compares what is installed with the catalog. Nothing is fetched unless you press u, which also asks "
        "GitHub, git hosts and PyPI whether the catalog's pins are current. A runs the apt upgrade it offers (apt asks "
        "you first); B plans the rebuilds it offers.",
    ),
    "help": ("Help is this screen. Enter on a profile shows what it is for and what you still set up by hand.",),
}

NEVER: tuple[str, ...] = (
    "It never answers a consent prompt for you: you type yes into the engine's own prompt, in the pane.",
    "It never runs anything but the engine's own commands (and the apt upgrade the engine's update report offers).",
    "It never stores your callsign, grid square or any station value; the engine's station file is the only copy.",
    "It never fetches anything from the network; the engine does that, and says so in its plan.",
)
```

- [ ] **Step 4: Implement the Help screens and the `i` key**

Create `hammunition_console/screens/help.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import urwid

from hammunition_console.context import Context
from hammunition_console.engine import Document
from hammunition_console.fmt import clean
from hammunition_console.helptext import EXIT_CODES, KEYS, NEVER, SCREEN_HELP
from hammunition_console.screens.base import Row, Screen, text


def profile_lines(body: Mapping[str, Any]) -> list[str]:
    """What a profile is for, from the engine's `show` document. Never the gate's variable name."""
    docs = body.get("documentation")
    docs = docs if isinstance(docs, dict) else {}
    lines = [f"{clean(body.get('name') or '?')}  ({clean(body.get('stage') or '')})  {clean(body.get('summary') or '')}", ""]
    for label, key in (("What it installs", "what_it_installs"), ("Why these belong together", "why_together"),
                       ("What it deliberately leaves out", "deliberately_excludes"),
                       ("What you still set up by hand", "manual_configuration"), ("Disk", "disk_footprint_hint")):
        if docs.get(key):
            lines += [f"{label}:", f"  {clean(docs[key]).strip()}", ""]
    consent = body.get("consent")
    if isinstance(consent, dict) and consent.get("disclosure"):
        lines += ["You will be asked to type yes before this installs. The engine shows exactly this:",
                  *[f"  {clean(l)}" for l in str(consent["disclosure"]).splitlines()], ""]
    packages = body.get("packages")
    if isinstance(packages, list) and packages:
        lines += [f"Units ({len(packages)}): " + ", ".join(clean(p) for p in packages)]
    for s in body.get("suggests_one_of") or []:
        if isinstance(s, dict):
            lines.append(f"Choose one of {', '.join(clean(o) for o in s.get('options') or [])} for {clean(s.get('name') or '?')}"
                         + (f" (recommended {clean(s['recommended'])})" if s.get("recommended") else "")
                         + (f": {clean(s['reason'])}" if s.get("reason") else ""))
    return lines


class ProfileDocsScreen(Screen):
    name = "profile"

    def __init__(self, ctx: Context, profile: str) -> None:
        super().__init__(ctx)
        self.profile = profile
        self.title = f"Profile: {profile}"
        self._doc: Document | None = None

    def on_show(self) -> None:
        self.load("show", lambda: self.ctx.engine.read("show", self.profile), lambda d: setattr(self, "_doc", d))
        self.redraw()

    def redraw(self) -> None:
        if self.status.get("show") == "error":
            self.set_rows([text(self.errors["show"], "fail")])
        elif self._doc is not None:
            self.set_rows([text(line) for line in profile_lines(self._doc.body)])
        else:
            self.set_rows([text("Reading the profile...")])


class HelpScreen(Screen):
    name = "help"
    title = "Help"

    def __init__(self, ctx: Context, about: str = "") -> None:
        super().__init__(ctx)
        self._about = about
        self._catalog: Document | None = None

    def on_show(self) -> None:
        self.load("list", lambda: self.ctx.engine.read("list"), lambda d: setattr(self, "_catalog", d))
        self.redraw()

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self._about in SCREEN_HELP:
            rows += [text(f"This screen ({self._about})", "key")] + [text(line) for line in SCREEN_HELP[self._about]] + [text("")]
        rows += [text("Keys", "key")] + [text(f"  {keys:<10} {meaning}") for keys, meaning in KEYS] + [text("")]
        rows += [text("What the console never does", "key")] + [text(f"  {line}") for line in NEVER] + [text("")]
        rows += [text("Exit codes", "key")] + [text(f"  {code:<10} {meaning}") for code, meaning in EXIT_CODES] + [text("")]
        rows.append(text("Profiles (Enter shows what each is for)", "key"))
        if self.status.get("list") == "error":
            rows.append(text(self.errors["list"], "fail"))
        elif self._catalog is not None:
            for entry in self._catalog.body.get("profiles") or []:
                if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    row = Row(f"  {clean(entry['name']):<18} {clean(entry.get('summary') or '')}", entry["name"])
                    urwid.connect_signal(row, "activate", self._open)
                    rows.append(row)
        else:
            rows.append(text("  reading the profiles..."))
        self.set_rows(rows)

    def _open(self, row: Row) -> None:
        self.ctx.push(ProfileDocsScreen(self.ctx, str(row.value)))
```

In `hammunition_console/screens/install.py`, add to `InstallScreen.keypress`, before the final `return key`:

```python
        if key == "i" and self.mode == "profiles":
            value = self.focused_value()
            if isinstance(value, tuple) and isinstance(value[1].get("name"), str):
                from hammunition_console.screens.help import ProfileDocsScreen

                self.ctx.push(ProfileDocsScreen(self.ctx, value[1]["name"]))
                return None
```

- [ ] **Step 5: The man page**

Create `man/hammunition-console.1`:

```roff
.TH HAMMUNITION-CONSOLE 1 "2026-10-03" "hammunition-console 0.1.0" "Hammunition"
.SH NAME
hammunition\-console \- a terminal front end for the Hammunition engine
.SH SYNOPSIS
.B hammunition\-console
[\fB\-\-help\fR] [\fB\-\-version\fR]
.SH DESCRIPTION
A full\-screen program that shows what the Hammunition engine has installed, what is wrong and what to do next, and runs the
engine's own commands for you. It reads the engine's JSON documents and runs every change in a terminal pane, so sudo, every
group choice and every consent prompt are the engine's, answered by you. It needs a terminal of at least 80x24, and the
engine (\fBhammunition\fR) on PATH.
.SH SCREENS
Home, Install, Station, Logs, Update and Help. Hardware and maps are left to the CLI and the tray.
.SH KEYS
.TP
.B 1\-5
open the screen with that number (Home)
.TP
.B Enter
open the selected row
.TP
.B b / Esc
go back; changes nothing
.TP
.B ?
help
.TP
.B q
quit
.TP
.B r
refresh this screen
.TP
.B R
run the planned command in a terminal pane (plan and confirm screens)
.TP
.B Tab
switch between profiles and single units (Install)
.TP
.B U
plan an uninstall of the selected profile (Install)
.TP
.B i
the selected profile's documentation (Install)
.TP
.B v
reveal or hide station values (Station)
.TP
.B c
clear the selected value, where the engine can (Station)
.TP
.B u
also ask upstream whether the catalog's pins are current (Update)
.TP
.B A
run the apt upgrade the report offers (Update)
.TP
.B B
plan the rebuilds the report offers (Update)
.TP
.B s
skip the selected first\-run step (Home)
.TP
.B D
dismiss the first\-run checklist (Home)
.SH WHAT IT NEVER DOES
It never answers a consent prompt for you, never runs anything but the engine's own commands, never stores a station value
and never fetches anything from the network. Every command it runs is shown first.
.SH EXIT STATUS
.TP
.B 0
normal exit
.TP
.B 1
the console crashed (details, without any message text, in crash.log)
.TP
.B 2
the console refused to start: no terminal, TERM=dumb, running as root, bad argument
.SH FILES
.TP
.I ~/.config/hammunition\-console/config.toml
the last screen, the colour theme and whether the first\-run checklist was dismissed. Nothing else.
.TP
.I ~/.config/hammunition\-console/crash.log
the exception type and its frames after a crash; never a message, a station value or a plan.
.SH SEE ALSO
.BR hammunition (1)
and https://chiefgyk3d.github.io/Hammunition/getting\-started/console/
```

- [ ] **Step 6: Run the tests; commit**

Run: `python3 -m pytest tests/test_help.py tests/test_man_and_registry.py tests/test_consent_guard.py -v`
Expected: PASS. If `test_the_man_page_documents_every_key...` reports an exit code missing, adjust the roff (it must contain the code on its own line after `.B`).

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add Help, profile documentation, the man page and the screen registry test"
```
Expected: clean, all pass.

---

### Task 15: The first-run checklist

Four optional, resumable, skippable steps on Home. State is read from the engine each time, never stored; the only thing the console stores is "dismissed". The hardware step is shown as unknown and never as done, because no engine document reports whether the udev rules and groups are applied (E4).

**Files:**
- Create: `hammunition_console/walkthrough.py`
- Modify: `hammunition_console/screens/home.py` (`__init__`, `_walkthrough_rows`, `keypress`, three new methods)
- Test: `tests/test_walkthrough.py`

**Interfaces:**
- Consumes: `home.HomeScreen.docs`, `screens.base.{Row, ConfirmScreen, text}`, `screens.plan.PlanScreen`, `ctx.open_screen("install", highlight=...)`, `ctx.save_config`.
- Produces: `walkthrough.STARTER = "station"`; `walkthrough.Step(number, key, label, state, detail)` (`state` one of `done todo unknown skipped`); `walkthrough.steps(station, catalog, skipped) -> list[Step]` (`station` and `catalog` are documents' bodies or `None`); `walkthrough.show_checklist(steps) -> bool`; `walkthrough.MARK: dict[str, str]`.

- [ ] **Step 1: Write the tests (failing first)**

Create `tests/test_walkthrough.py`:

```python
from typing import Any

from hammunition_console.config import Config
from hammunition_console.screens.base import ConfirmScreen
from hammunition_console.screens.home import HomeScreen
from hammunition_console.screens.plan import PlanScreen
from hammunition_console.walkthrough import STARTER, show_checklist, steps
from tests.helpers import FakeContext, FakeEngine, document, load, render

SET = {"callsign": "N0CALL", "grid_square": "FN31pr"}
NONE: dict[str, Any] = {"callsign": None, "grid_square": None}


def catalog(installed: Any, members: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": STARTER, "packages": ["a", "b"]}
    if installed is not None:
        entry.update(installed=installed, members=members)
    return {"profiles": [entry]}


def state(items: list[Any], key: str) -> str:
    return next(s.state for s in items if s.key == key)


def test_station_is_done_only_when_both_values_are_present() -> None:
    assert state(steps(SET, catalog(0, 2), set()), "station") == "done"
    assert state(steps(NONE, catalog(0, 2), set()), "station") == "todo"
    assert state(steps({"callsign": "N0CALL", "grid_square": None}, catalog(0, 2), set()), "station") == "todo"
    assert state(steps(None, None, set()), "station") == "unknown"


def test_hardware_is_never_done() -> None:
    for station in (SET, NONE, None):
        assert state(steps(station, catalog(2, 2), set()), "hardware") == "unknown"
    assert state(steps(SET, catalog(2, 2), {"hardware"}), "hardware") == "skipped"


def test_pick_and_install_follow_the_starter_profiles_installed_state() -> None:
    nothing = steps(SET, catalog(0, 2), set())
    assert (state(nothing, "pick"), state(nothing, "install")) == ("todo", "todo")
    part = steps(SET, catalog(1, 2), set())
    assert (state(part, "pick"), state(part, "install")) == ("done", "todo")
    whole = steps(SET, catalog(2, 2), set())
    assert (state(whole, "pick"), state(whole, "install")) == ("done", "done")


def test_without_e1_those_two_are_unknown_never_done() -> None:
    items = steps(SET, catalog(None, None), set())
    assert (state(items, "pick"), state(items, "install")) == ("unknown", "unknown")
    assert state(steps(SET, None, set()), "pick") == "unknown"
    assert state(steps(SET, {"profiles": []}, set()), "install") == "unknown"
    assert state(steps(SET, catalog("x", None), set()), "install") == "unknown"


def test_skipping_never_hides_a_done_step_and_the_checklist_shows_until_all_are_settled() -> None:
    items = steps(SET, catalog(2, 2), {"station", "pick", "hardware"})
    assert state(items, "station") == "done" and state(items, "pick") == "done" and state(items, "hardware") == "skipped"
    assert show_checklist(items) is False
    assert show_checklist(steps(SET, catalog(2, 2), set())) is True, "hardware stays unknown, so the list stays"


def home(ctx: FakeContext | None = None) -> tuple[HomeScreen, FakeContext]:
    ctx = ctx or FakeContext()
    screen = HomeScreen(ctx)
    screen.on_show()
    return screen, ctx


def step_row(screen: HomeScreen, key: str) -> Any:
    return next(r for r in screen._walker if getattr(getattr(r, "value", None), "key", None) == key)


def test_home_shows_the_checklist_and_never_a_station_value() -> None:
    screen, _ = home()
    out = render(screen.widget(), 110, 40)
    assert "First run" in out and "Set your station" in out and "hardware" in out.lower()
    assert "N0CALL" not in out and "FN31pr" not in out
    assert "[?]" in out, "the hardware step is shown as unknown"


class NeverBackground:
    """A background that never finishes: the documents have not arrived yet."""

    def submit(self, call: Any, done: Any) -> None:
        return None


def test_the_checklist_waits_for_the_documents_instead_of_flickering() -> None:
    ctx = FakeContext()
    ctx.bg = NeverBackground()  # type: ignore[assignment]
    screen = HomeScreen(ctx)
    screen.on_show()
    assert "First run" not in render(screen.widget(), 110, 40)


def test_dismiss_saves_only_the_flag_and_hides_the_list() -> None:
    screen, ctx = home()
    assert screen.keypress("D") is None
    assert ctx.config.walkthrough_dismissed is True and ctx.saved == 1
    assert "First run" not in render(screen.widget(), 110, 40)
    assert ctx.config == Config(walkthrough_dismissed=True)


def test_a_dismissed_checklist_stays_hidden() -> None:
    ctx = FakeContext(config=Config(walkthrough_dismissed=True))
    screen, _ = home(ctx)
    assert "First run" not in render(screen.widget(), 110, 40)


def test_skip_marks_the_focused_step_for_this_session_only() -> None:
    screen, ctx = home()
    screen._walker.set_focus(screen._walker.index(step_row(screen, "hardware")))
    assert screen.keypress("s") is None
    assert "[-]" in render(screen.widget(), 110, 40) and ctx.saved == 0


def test_the_station_step_opens_the_station_screen() -> None:
    screen, ctx = home()
    step_row(screen, "station").keypress((100,), "enter")
    assert ctx.opened[-1] == ("station", {})


def test_the_pick_step_opens_install_with_the_starter_highlighted() -> None:
    screen, ctx = home()
    step_row(screen, "pick").keypress((100,), "enter")
    assert ctx.opened[-1] == ("install", {"highlight": STARTER})


def test_the_install_step_goes_through_the_plan() -> None:
    screen, ctx = home()
    step_row(screen, "install").keypress((100,), "enter")
    plan = ctx.pushed[-1]
    assert isinstance(plan, PlanScreen) and (plan.action, plan.names) == ("install", [STARTER])
    assert ctx.panes == []


def test_the_hardware_step_names_the_command_and_runs_it_only_on_capital_r() -> None:
    screen, ctx = home()
    step_row(screen, "hardware").keypress((100,), "enter")
    confirm = ctx.pushed[-1]
    assert isinstance(confirm, ConfirmScreen)
    out = render(confirm.widget(), 100, 12)
    assert "hammunition hardware apply" in out and "its own plan" in out and "confirmation" in out
    assert ctx.panes == []
    confirm.keypress("R")
    assert ctx.panes[0].argv == ["hammunition", "hardware", "apply"]


def test_a_failed_step_leaves_the_list_and_says_why() -> None:
    screen, ctx = home()
    step_row(screen, "hardware").keypress((100,), "enter")
    ctx.pushed[-1].keypress("R")
    ctx.panes[0].on_exit(1)
    assert "hardware apply exited 1" in screen.note and "First run" in render(screen.widget(), 110, 40)


def test_a_finished_install_hides_the_install_steps() -> None:
    engine = FakeEngine()
    cat = load("list-all")
    for profile in cat["profiles"]:
        if profile["name"] == STARTER:
            profile["members"], profile["installed"] = 3, 3
    engine.set(("list",), document("catalog", cat))
    screen, _ = home(FakeContext(engine=engine))
    out = render(screen.widget(), 110, 40)
    assert "[x] 3" in out and "[x] 4" in out
```

- [ ] **Step 2: Run them; confirm they fail; implement the pure part**

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_walkthrough.py -v`
Expected: FAIL (`ModuleNotFoundError: hammunition_console.walkthrough`).

Create `hammunition_console/walkthrough.py`:

```python
"""The first-run checklist (spec section 6). Pure: documents in, steps out. State is
never stored, so the checklist is always true; skipping lasts for the session."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

STARTER = "station"
MARK = {"done": "[x]", "todo": "[ ]", "unknown": "[?]", "skipped": "[-]"}


@dataclass(frozen=True)
class Step:
    number: int
    key: str
    label: str
    state: str
    detail: str


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _starter(catalog: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    for entry in (catalog or {}).get("profiles") or []:
        if isinstance(entry, dict) and entry.get("name") == STARTER:
            return entry
    return None


def steps(station: Mapping[str, Any] | None, catalog: Mapping[str, Any] | None, skipped: Collection[str]) -> list[Step]:
    if station is None:
        s1, d1 = "unknown", "reading the station"
    elif station.get("callsign") is not None and station.get("grid_square") is not None:
        s1, d1 = "done", "the engine has your callsign and grid square"
    else:
        s1, d1 = "todo", "the engine needs your callsign and grid square; Enter opens Station"
    entry = _starter(catalog)
    known = entry is not None and _int(entry.get("members")) and _int(entry.get("installed"))
    if known and entry is not None:
        s3 = "done" if entry["installed"] >= 1 else "todo"
        s4 = "done" if entry["members"] > 0 and entry["installed"] == entry["members"] else "todo"
        d3 = f"the {STARTER} profile is the floor everything stands on; Enter opens Install with it selected"
        d4 = f"{entry['installed']} of {entry['members']} of its units installed; Enter shows the plan"
    else:
        s3 = s4 = "unknown"
        d3 = d4 = "the engine does not report installed state yet"
    raw = [
        (1, "station", "Set your station", s1, d1),
        (2, "hardware", "Apply the hardware rules", "unknown",
         "the engine does not yet report whether the udev rules and groups are applied; Enter shows the command, which prints its own plan"),
        (3, "pick", "Pick a profile", s3, d3),
        (4, "install", f"Install {STARTER}", s4, d4),
    ]
    return [Step(n, k, label, "skipped" if k in skipped and st != "done" else st, d) for n, k, label, st, d in raw]


def show_checklist(items: list[Step]) -> bool:
    return any(s.state in ("todo", "unknown") for s in items)
```

- [ ] **Step 3: Wire it into Home**

In `hammunition_console/screens/home.py` add the imports
`from hammunition_console.screens.base import ConfirmScreen`, `from hammunition_console.screens.plan import PlanScreen`, `from hammunition_console.walkthrough import MARK, STARTER, Step, show_checklist, steps`,
extend `__init__` with `self.skipped: set[str] = set()` and `self.note = ""`, replace `_walkthrough_rows`, and replace `keypress`:

```python
    def _walkthrough_rows(self) -> list[urwid.Widget]:
        if self.ctx.config.walkthrough_dismissed:
            return []
        if "station" not in self.docs and "station" not in self.errors:
            return []  # still reading: do not flash a checklist that may be all done
        station = self.docs["station"].body if "station" in self.docs else None
        catalog = self.docs["list"].body if "list" in self.docs else None
        items = steps(station, catalog, self.skipped)
        if not show_checklist(items):
            return []
        rows: list[urwid.Widget] = [text("First run: four steps, each optional. Enter opens one, s skips it, D dismisses this list.", "key")]
        if self.note:
            rows.append(text(self.note, "warn"))
        for step in items:
            row = Row(f" {MARK[step.state]} {step.number}  {step.label}  - {step.detail}", step)
            urwid.connect_signal(row, "activate", self._open_step)
            rows.append(row)
        rows.append(text(""))
        return rows

    def _open_step(self, row: Row) -> None:
        step = row.value
        if not isinstance(step, Step):
            return
        if step.key == "station":
            self.ctx.open_screen("station")
        elif step.key == "hardware":
            self.ctx.push(ConfirmScreen(
                self.ctx, "Apply the hardware rules",
                ["This runs: hammunition hardware apply", "",
                 "It prints its own plan and asks for its own typed confirmation (and your sudo password).",
                 "The console cannot show that plan first: the engine has no JSON form of it yet."],
                self._run_hardware))
        elif step.key == "pick":
            self.ctx.open_screen("install", highlight=STARTER)
        elif step.key == "install":
            self.ctx.push(PlanScreen(self.ctx, "install", [STARTER]))

    def _run_hardware(self) -> None:
        self.ctx.run_pane(self.ctx.engine.command("hardware", "apply"), "hardware apply", self._after_hardware)

    def _after_hardware(self, code: int | None) -> None:
        self.note = "" if code == 0 else f"hardware apply exited {code}; its own words were in the pane. The step stays on the list."
        self.ctx.pop()

    def keypress(self, key: str) -> str | None:
        if key in ("1", "2", "3", "4", "5"):
            self.ctx.open_screen(MENU[int(key) - 1][0])
            return None
        if key == "D":
            self.ctx.config.walkthrough_dismissed = True
            self.ctx.save_config()
            self.redraw()
            return None
        if key == "s":
            step = self.focused_value()
            if isinstance(step, Step):
                self.skipped.add(step.key)
                self.redraw()
                return None
        return key
```

Run: `python3 -m pytest tests/test_walkthrough.py tests/test_home.py -v`
Expected: PASS (all). In `test_a_finished_install_hides_the_install_steps` the checklist remains (hardware is unknown) with steps 3 and 4 marked `[x]`.

- [ ] **Step 4: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the first-run checklist on Home"
```
Expected: clean, all pass.

---

### Task 16: Cross-cutting guards: no station values, only JSON verbs, golden screens, no network

Four checks that watch the whole program rather than one screen. Each is falsified on purpose before it is trusted.

**Files:**
- Create: `tests/test_no_station_values.py`, `tests/test_screen_table.py`, `tests/test_golden.py`, `tests/golden/` (generated), `tests/test_no_network.py`

**Interfaces:**
- Consumes: `app.Shell/build_registry/write_crash_log`, `config.save/config_path`, every screen, `verbs.JSON_VERBS/verb_of`, `FakeEngine/FakeContext/render/document/load`, `fixture_scan.findings`.
- Produces: nothing later tasks use; a regression net.

- [ ] **Step 1: No station value reaches a screen, a file or the environment**

Create `tests/test_no_station_values.py`:

```python
"""A callsign resolves to a name and an address; a grid square says where the station is.
They live in the engine's station file and nowhere else. This opens every screen against
a station full of sentinels and then looks everywhere the console could have put one."""

import os
from pathlib import Path

import pytest

from hammunition_console import config
from hammunition_console.app import Shell, build_registry, write_crash_log
from hammunition_console.config import SCREENS, Config
from hammunition_console.worker import SyncBackground
from tests.helpers import FakeEngine, document, load, render

SENTINELS = ("ZZ9SENTINEL", "ZZ99zz", "SENTALIAS", "sentinelregion", "usb-SENTINELSERIAL")


def station_body() -> dict[str, object]:
    return {**load("station-set"), "callsign": SENTINELS[0], "grid_square": SENTINELS[1], "node_alias": SENTINELS[2],
            "map_regions": [f"north-america/us/{SENTINELS[3]}"], "rig_device": f"/dev/serial/by-id/{SENTINELS[4]}-if00"}


def test_no_station_value_reaches_a_screen_a_file_or_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    env_before = dict(os.environ)
    engine = FakeEngine()
    engine.set(("station", "show"), document("station", station_body()))
    cfg_path = config.config_path(os.environ)
    shell = Shell(engine, Config(), SyncBackground(), pane_factory=lambda a, t, e: shell.stack[-1],
                  after=lambda s, f: None, registry=build_registry(), save=lambda c: config.save(c, cfg_path))
    shell.open_screen("home")
    for name in SCREENS[1:]:
        shell.open_screen(name)
    drawn = [render(shell.root, 120, 40)]
    for screen in list(shell.stack):  # every screen, not only the top one
        drawn.append(render(screen.widget(), 120, 40))
    for sentinel in SENTINELS:
        assert not any(sentinel in text for text in drawn), f"{sentinel} was drawn before any reveal"

    station = next(s for s in shell.stack if s.name == "station")
    station.keypress("v")  # type: ignore[attr-defined]
    assert SENTINELS[0] in render(station.widget(), 120, 40)
    station.on_hide()
    assert SENTINELS[0] not in render(station.widget(), 120, 40), "leaving the screen must hide the values again"

    try:
        raise RuntimeError(f"callsign {SENTINELS[0]} grid {SENTINELS[1]}")
    except RuntimeError as exc:
        crash = write_crash_log(exc, config.config_dir(os.environ))
    assert crash is not None

    files = [p for p in home.rglob("*") if p.is_file()]
    assert {p.name for p in files} == {"config.toml", "crash.log"}, files
    for path in files:
        data = path.read_bytes()
        for sentinel in SENTINELS:
            assert sentinel.encode() not in data, f"{sentinel} found in {path.name}"
    assert dict(os.environ) == env_before, "the console changed the environment"
    assert not any(s in v for v in os.environ.values() for s in SENTINELS)
    assert config.load(cfg_path).last_screen == "help"
```

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_no_station_values.py -v`
Expected: PASS.

Falsify it: in `hammunition_console/screens/home.py` temporarily change `station_text` to return `f"Station: {doc.body.get('callsign')}"` for the set case. Run the test.
Expected: FAIL, "ZZ9SENTINEL was drawn before any reveal". Revert.

Falsify the file half: in `app.write_crash_log` temporarily add `lines.append(str(exc))`. Run `python3 -m pytest tests/test_shell.py tests/test_no_station_values.py -v`.
Expected: FAIL in both (`sentinel not in content`; `found in crash.log`). Revert.

- [ ] **Step 2: Every read is a JSON verb; the set of verbs the screens use is pinned**

Create `tests/test_screen_table.py`:

```python
"""The spec: a command with no JSON form returns an error document, ran nothing, and is a bug in the
screen table. Two checks: statically, every literal verb in the package is a JSON verb; dynamically,
driving every screen reads exactly the verbs below, so a new read cannot slip in unseen."""

import re
from pathlib import Path

from hammunition_console.verbs import JSON_VERBS, verb_of
from tests.helpers import FakeContext, FakeEngine
from hammunition_console.screens.help import HelpScreen, ProfileDocsScreen
from hammunition_console.screens.home import HomeScreen
from hammunition_console.screens.install import InstallScreen
from hammunition_console.screens.logs import LogsScreen
from hammunition_console.screens.plan import PlanScreen
from hammunition_console.screens.station import StationScreen
from hammunition_console.screens.update import UpdateScreen

PACKAGE = Path(__file__).resolve().parent.parent / "hammunition_console"
READ = re.compile(r"engine\.read\(\s*\"([a-z-]+)\"(?:\s*,\s*\"([a-z-]+)\")?")
EXPECTED = {("status",), ("doctor",), ("list",), ("show",), ("logs",), ("update",), ("station", "show"),
            ("install",), ("uninstall",), ("maps", "regions"), ("reference", "books")}


def test_every_literal_read_in_the_package_is_a_json_verb() -> None:
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for m in READ.finditer(path.read_text()):
            words = tuple(w for w in m.groups() if w)
            found.append((path.name, words))
            assert verb_of(words) in JSON_VERBS, f"{path.name}: {words} has no --json form"
    assert len(found) >= 8, "the scan found too few reads to mean anything"


def test_driving_every_screen_reads_exactly_the_expected_verbs() -> None:
    ctx = FakeContext()
    for screen in (HomeScreen(ctx), InstallScreen(ctx), StationScreen(ctx), LogsScreen(ctx), UpdateScreen(ctx),
                   UpdateScreen(ctx, names=["station"]), HelpScreen(ctx), ProfileDocsScreen(ctx, "station"),
                   PlanScreen(ctx, "install", ["station"]), PlanScreen(ctx, "uninstall", ["station"])):
        screen.on_show()
    station = StationScreen(ctx)
    station.on_show()
    station._choose_books()
    ctx.pushed[-1].on_show()
    station._search_regions("vermont")
    ctx.pushed[-1].on_show()
    engine: FakeEngine = ctx.engine
    assert {verb_of(call) for call in engine.calls} == EXPECTED
    assert EXPECTED <= JSON_VERBS
```

Run: `python3 -m pytest tests/test_screen_table.py -v`
Expected: PASS. Falsify: in `screens/logs.py` change `engine.read("logs")` to `engine.read("hardware", "list")`. Run it: FAIL with `hardware list has no --json form` (static) and `NotAJsonVerb` (dynamic). Revert.

- [ ] **Step 3: Golden screens**

Create `tests/test_golden.py`:

```python
"""A few screens rendered at a fixed size and compared with a reviewed text file. After an
intended change, regenerate with `UPDATE_GOLDEN=1 python3 -m pytest tests/test_golden.py`
and READ the diff before committing: a golden nobody reads is not a check."""

import os
from pathlib import Path

import pytest

from hammunition_console.screens.home import HomeScreen
from hammunition_console.screens.install import InstallScreen
from hammunition_console.screens.plan import PlanScreen
from hammunition_console.screens.update import UpdateScreen
from tests.fixture_scan import findings
from tests.helpers import FakeContext, FakeEngine, render

GOLDEN = Path(__file__).parent / "golden"


def check(name: str, drawn: str) -> None:
    path = GOLDEN / f"{name}.txt"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(drawn + "\n")
        return
    assert path.exists(), f"missing golden {name}: run UPDATE_GOLDEN=1 python3 -m pytest tests/test_golden.py and review it"
    assert drawn + "\n" == path.read_text(), f"{name} changed: review the diff; if intended, regenerate with UPDATE_GOLDEN=1"


def drawn(screen: object) -> str:
    screen.on_show()  # type: ignore[attr-defined]
    return render(screen.widget(), 100, 30)  # type: ignore[attr-defined]


@pytest.mark.parametrize("name,build", [
    ("home", lambda: HomeScreen(FakeContext())),
    ("install-with-e1", lambda: InstallScreen(FakeContext())),
    ("install-without-e1", lambda: InstallScreen(FakeContext(engine=FakeEngine(suffix="-without")))),
    ("plan-station", lambda: PlanScreen(FakeContext(), "install", ["station"])),
    ("update-with-e2", lambda: UpdateScreen(FakeContext())),
    ("update-without-e2", lambda: UpdateScreen(FakeContext(engine=FakeEngine(suffix="-without")))),
])
def test_golden(name: str, build: object) -> None:
    check(name, drawn(build()))  # type: ignore[operator]


def test_goldens_carry_no_identifier() -> None:
    for path in sorted(GOLDEN.glob("*.txt")):
        assert findings(path.read_text()) == [], path.name
```

Generate and review them:

Run: `UPDATE_GOLDEN=1 python3 -m pytest tests/test_golden.py -v && python3 -m pytest tests/test_golden.py -v && head -30 tests/golden/home.txt tests/golden/install-without-e1.txt`
Expected: first run passes (writes six files), second run passes (compares). Read the two printed files: `home.txt` shows the first-run checklist, Doctor, Station, Last run, Behind the pin and the numbered menu; `install-without-e1.txt` shows `units, state unknown` and no `None`. If either looks wrong, fix the screen, not the golden.

Falsify: in `screens/home.py` change the text `Doctor:` to `Health:` in `doctor_text`. Run `python3 -m pytest tests/test_golden.py -v`.
Expected: FAIL for `home` with "home changed: review the diff". Revert.

- [ ] **Step 4: The no-network guard is itself checked**

Create `tests/test_no_network.py`:

```python
import socket

import pytest


def test_a_test_cannot_reach_the_network() -> None:
    with pytest.raises(AssertionError, match="the console fetches nothing"):
        socket.create_connection(("93.184.216.34", 80), timeout=1)


def test_the_package_has_no_network_imports() -> None:
    from pathlib import Path

    forbidden = ("import socket", "import urllib", "import http", "import requests", "import ssl", "from urllib", "from http")
    package = Path(__file__).resolve().parent.parent / "hammunition_console"
    hits = [f"{p.name}: {tok}" for p in package.rglob("*.py") for tok in forbidden if tok in p.read_text()]
    assert hits == [], "the console fetches nothing; the engine does"
```

Run: `python3 -m pytest tests/test_no_network.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add cross-cutting guards: no station values, JSON verbs only, golden screens, no network"
```
Expected: clean, all pass.

---

### Task 17: The launcher, `install.sh` and `uninstall.sh`

The installer mirrors hammunition-tray's: no pip, no venv, nothing as root, a `/bin/sh` wrapper that runs the system `python3`. `--prefix` defaults to `~/.local`; `--interpreter` is the Python the wrapper runs.

**Files:**
- Create: `bin/hammunition-console`, `install.sh`, `uninstall.sh`
- Test: `tests/test_install_sh.py`

**Interfaces:**
- Produces: `bin/hammunition-console` (the in-tree wrapper the Hammunition catalog unit launches); `install.sh [--prefix DIR] [--interpreter PATH]`; `uninstall.sh [--prefix DIR]`. Installed layout: `<prefix>/share/hammunition-console/hammunition_console/`, `<prefix>/bin/hammunition-console` (carries the mark `# Installed by hammunition-console install.sh.`), `<prefix>/share/man/man1/hammunition-console.1`.

- [ ] **Step 1: Write the tests (failing first)**

Create `tests/test_install_sh.py`:

```python
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MARK = "# Installed by hammunition-console install.sh."


def sh(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(ROOT / script), *args], capture_output=True, text=True, env=env or os.environ.copy())


def install(prefix: Path) -> subprocess.CompletedProcess[str]:
    return sh("install.sh", "--prefix", str(prefix), "--interpreter", sys.executable)


def test_install_places_the_tree_the_wrapper_and_the_man_page(tmp_path: Path) -> None:
    done = install(tmp_path)
    assert done.returncode == 0, done.stderr
    wrapper = tmp_path / "bin" / "hammunition-console"
    assert os.access(wrapper, os.X_OK) and MARK in wrapper.read_text().splitlines()
    tree = tmp_path / "share" / "hammunition-console" / "hammunition_console"
    assert (tree / "__main__.py").exists() and not list(tree.rglob("__pycache__"))
    assert (tmp_path / "share" / "man" / "man1" / "hammunition-console.1").exists()
    ran = subprocess.run([str(wrapper), "--version"], capture_output=True, text=True)
    assert ran.returncode == 0 and ran.stdout.startswith("hammunition-console ")


def test_the_wrapper_bakes_in_the_interpreter_and_never_uses_a_shell_string(tmp_path: Path) -> None:
    install(tmp_path)
    text = (tmp_path / "bin" / "hammunition-console").read_text()
    assert f'exec "{sys.executable}" -P -m hammunition_console "$@"' in text


def test_reinstalling_is_idempotent_and_replaces_the_tree(tmp_path: Path) -> None:
    install(tmp_path)
    stale = tmp_path / "share" / "hammunition-console" / "hammunition_console" / "stale.py"
    stale.write_text("x")
    assert install(tmp_path).returncode == 0 and not stale.exists()


def test_a_wrapper_this_installer_did_not_write_is_left_alone(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    foreign = tmp_path / "bin" / "hammunition-console"
    foreign.write_text("#!/bin/sh\necho mine\n")
    done = install(tmp_path)
    assert done.returncode == 1 and "not replaced" in done.stderr and foreign.read_text().endswith("echo mine\n")


@pytest.mark.parametrize("args,needle", [
    (["--prefix", "relative/dir"], "absolute"),
    (["--interpreter", "python3"], "absolute"),
    (["--prefix"], "needs"),
    (["--bogus"], "unknown option"),
])
def test_bad_arguments_are_refused_with_exit_2(args: list[str], needle: str, tmp_path: Path) -> None:
    done = sh("install.sh", *args)
    assert done.returncode == 2 and needle in done.stderr


def test_an_interpreter_that_is_not_python_311_with_urwid_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    notpython = tmp_path / "notpython"
    notpython.write_text("#!/bin/sh\nexit 1\n")
    notpython.chmod(0o755)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    done = sh("install.sh", "--prefix", str(prefix), "--interpreter", str(notpython))
    assert done.returncode == 1 and "3.11" in done.stderr
    assert list(prefix.iterdir()) == []


def test_help_prints_usage_and_exits_0() -> None:
    for script in ("install.sh", "uninstall.sh"):
        done = sh(script, "--help")
        assert done.returncode == 0 and "--prefix" in done.stdout


def test_uninstall_removes_what_install_placed_and_leaves_the_config(tmp_path: Path) -> None:
    install(tmp_path)
    config = tmp_path / ".config" / "hammunition-console"
    config.mkdir(parents=True)
    (config / "config.toml").write_text("theme = 'dark'\n")
    done = sh("uninstall.sh", "--prefix", str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert not (tmp_path / "bin" / "hammunition-console").exists()
    assert not (tmp_path / "share" / "hammunition-console").exists()
    assert not (tmp_path / "share" / "man" / "man1" / "hammunition-console.1").exists()
    assert (config / "config.toml").exists() and "config.toml" in done.stdout
    assert sh("uninstall.sh", "--prefix", str(tmp_path)).returncode == 0, "uninstall is idempotent"


def test_uninstall_leaves_a_foreign_wrapper(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    foreign = tmp_path / "bin" / "hammunition-console"
    foreign.write_text("#!/bin/sh\necho mine\n")
    done = sh("uninstall.sh", "--prefix", str(tmp_path))
    assert done.returncode == 0 and foreign.exists() and "not written by" in done.stdout


def test_the_in_tree_wrapper_runs_the_package_beside_it(tmp_path: Path) -> None:
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    (fakebin / "python3").symlink_to(sys.executable)
    env = {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"}
    ran = subprocess.run([str(ROOT / "bin" / "hammunition-console"), "--version"], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert ran.returncode == 0 and ran.stdout.startswith("hammunition-console ")


def test_the_in_tree_wrapper_follows_a_symlink(tmp_path: Path) -> None:
    link = tmp_path / "hc"
    link.symlink_to(ROOT / "bin" / "hammunition-console")
    fakebin = tmp_path / "pybin"
    fakebin.mkdir()
    (fakebin / "python3").symlink_to(sys.executable)
    ran = subprocess.run([str(link), "--version"], capture_output=True, text=True,
                         env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"})
    assert ran.returncode == 0


def test_shellcheck_is_clean() -> None:
    if shutil.which("shellcheck") is None:
        if os.environ.get("HAMMUNITION_REQUIRE_SHELLCHECK") == "1":
            pytest.fail("shellcheck is required here and is not installed")
        pytest.skip("shellcheck not installed (CI requires it)")
    done = subprocess.run(["shellcheck", "install.sh", "uninstall.sh", "bin/hammunition-console"], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
```

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_install_sh.py -v`
Expected: FAIL (the scripts do not exist; `bash: .../install.sh: No such file`).

- [ ] **Step 2: Write the scripts**

Create `bin/hammunition-console`:

```sh
#!/bin/sh
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
# hammunition-console: run the package that sits beside bin/ with the system python3.
# No virtualenv, no pip: the interpreter is whatever `python3` is on PATH (3.11 or later,
# with python3-urwid installed from the distribution).
here=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd -P) || exit 1
PYTHONPATH="${here}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec python3 -P -m hammunition_console "$@"
```

Create `install.sh`:

```bash
#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
# Install hammunition-console for the current user (or into --prefix).
#
# The script is deliberately NOT run as root and uses no pip and no virtualenv: it
# copies the package, writes a /bin/sh wrapper that runs the system Python, and
# copies the man page. Nothing is fetched.
#
#   ./install.sh                      into ~/.local
#   ./install.sh --prefix DIR         into DIR (absolute path)
#   ./install.sh --interpreter PATH   the Python the wrapper runs (default
#                                     /usr/bin/python3); it must be 3.11 or later
#                                     and import urwid (Debian family:
#                                     sudo apt install python3-urwid)
#
# Files placed:
#   <prefix>/share/hammunition-console/hammunition_console/   the package
#   <prefix>/bin/hammunition-console                          the wrapper
#   <prefix>/share/man/man1/hammunition-console.1             the man page
# Remove them with ./uninstall.sh. The console's own configuration
# (~/.config/hammunition-console/) is never touched by either script.
set -euo pipefail

prefix="${HOME}/.local"
interpreter=/usr/bin/python3

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            [[ $# -ge 2 ]] || { echo "--prefix needs a directory" >&2; exit 2; }
            prefix="$2"
            shift
            ;;
        --interpreter)
            [[ $# -ge 2 ]] || { echo "--interpreter needs a path" >&2; exit 2; }
            interpreter="$2"
            shift
            ;;
        -h | --help)
            sed -n '4,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
    shift
done

if [[ ${EUID} -eq 0 ]]; then
    echo "Do not run this as root: it installs for your own account." >&2
    exit 1
fi
case "${prefix}" in /*) ;; *) echo "--prefix must be an absolute path, got: ${prefix}" >&2; exit 2 ;; esac
case "${interpreter}" in /*) ;; *) echo "--interpreter must be an absolute path, got: ${interpreter}" >&2; exit 2 ;; esac
[[ -x "${interpreter}" ]] || { echo "--interpreter ${interpreter} is not an executable file." >&2; exit 2; }
"${interpreter}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null \
    || { echo "${interpreter} is not Python 3.11 or later." >&2; exit 1; }
"${interpreter}" -c 'import urwid' 2>/dev/null \
    || { echo "${interpreter} cannot import urwid. Debian family: sudo apt install python3-urwid" >&2; exit 1; }

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
share="${prefix}/share/hammunition-console"
wrapper="${prefix}/bin/hammunition-console"
man="${prefix}/share/man/man1/hammunition-console.1"
mark="# Installed by hammunition-console install.sh."

if [[ -e "${wrapper}" ]] && ! grep -qxF "${mark}" "${wrapper}"; then
    echo "${wrapper} exists and was not written by this installer; not replaced." >&2
    exit 1
fi

rm -rf "${share}/hammunition_console"
install -d -m 0755 "${share}" "${prefix}/bin" "${prefix}/share/man/man1"
cp -R "${src}/hammunition_console" "${share}/hammunition_console"
find "${share}" -name __pycache__ -type d -prune -exec rm -rf {} +
cat >"${wrapper}" <<WRAP
#!/bin/sh
${mark}
PYTHONPATH="${share}\${PYTHONPATH:+:\$PYTHONPATH}"
export PYTHONPATH
exec "${interpreter}" -P -m hammunition_console "\$@"
WRAP
chmod 0755 "${wrapper}"
install -m 0644 "${src}/man/hammunition-console.1" "${man}"

echo "Installed hammunition-console."
echo "  package  ${share}/hammunition_console"
echo "  command  ${wrapper}"
echo "  man page ${man}"
case ":${PATH}:" in *":${prefix}/bin:"*) ;; *) echo "Note: ${prefix}/bin is not on your PATH." ;; esac
```

Create `uninstall.sh`:

```bash
#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
# Remove what install.sh placed.
#
#   ./uninstall.sh                 from ~/.local
#   ./uninstall.sh --prefix DIR    from DIR (absolute path)
#
# The wrapper is removed only when it carries install.sh's mark. The console's own
# configuration, ~/.config/hammunition-console/config.toml, is left in place.
set -euo pipefail

prefix="${HOME}/.local"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            [[ $# -ge 2 ]] || { echo "--prefix needs a directory" >&2; exit 2; }
            prefix="$2"
            shift
            ;;
        -h | --help)
            sed -n '4,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
    shift
done
case "${prefix}" in /*) ;; *) echo "--prefix must be an absolute path, got: ${prefix}" >&2; exit 2 ;; esac

share="${prefix}/share/hammunition-console"
wrapper="${prefix}/bin/hammunition-console"
man="${prefix}/share/man/man1/hammunition-console.1"
mark="# Installed by hammunition-console install.sh."

rm -rf "${share}/hammunition_console"
rmdir "${share}" 2>/dev/null || true
rm -f "${man}"
if [[ -e "${wrapper}" ]]; then
    if grep -qxF "${mark}" "${wrapper}"; then
        rm -f "${wrapper}"
    else
        echo "${wrapper} was not written by this installer; left in place."
    fi
fi
echo "Removed hammunition-console. Its configuration, ~/.config/hammunition-console/config.toml, was left in place."
```

- [ ] **Step 3: Make them executable, run the tests, fix, commit**

Run: `chmod +x bin/hammunition-console install.sh uninstall.sh && python3 -m pytest tests/test_install_sh.py -v`
Expected: PASS (shellcheck test passes or skips with "shellcheck not installed"; run `shellcheck install.sh uninstall.sh bin/hammunition-console` by hand if it is installed: Expected: no output, exit 0).

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the launcher, install.sh and uninstall.sh"
```
Expected: clean, all pass.

---

### Task 18: Changelog tooling, version check, CI and release workflows

**Files:**
- Create: `scripts/changelog.py` (copied then adapted), `scripts/check_version.py`, `CHANGELOG.md`, `changelog.d/README.md`, `changelog.d/first-release.added.md`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`
- Test: `tests/test_changelog.py`, `tests/test_check_version.py`, `tests/test_workflows.py`

**Interfaces:**
- Produces: `scripts/changelog.py preview|check-pr|assemble` (the engine's, adapted: first release allowed, fragment paths renamed); `scripts.check_version.check(tag: str, root: Path) -> str`; CI jobs `lint`, `test` (matrix), `archive-ubuntu`, `archive-debian`, `shell`; release jobs `verify`, `test`, `publish`.

- [ ] **Step 1: Copy and adapt the engine's changelog tool; write its tests**

```bash
cd /home/chiefgyk3d/src/hammunition-console && cp /home/chiefgyk3d/src/Hammunition/scripts/changelog.py scripts/changelog.py && git -C /home/chiefgyk3d/src/Hammunition log -1 --format=%h -- scripts/changelog.py
```
Expected: prints the engine commit the copy was taken from (put it in the script's docstring: "copied from Hammunition scripts/changelog.py at <hash>, both GPL-3.0-or-later, same owner").

Make the copy's first lines the shebang followed directly by the two SPDX lines: the engine's file has a blank line after the shebang, and `scripts/spdx.py --check` wants none (`sed -i '2{/^$/d}' scripts/changelog.py && head -4 scripts/changelog.py`; Expected: shebang, two `# SPDX-` lines, then a blank line). Add one sentence to its docstring naming the commit it was copied from. Then edit two things in the copy. First, a first release has no later `## ` heading to stop at: in `assemble_text` change `re.search(r"^## Unreleased\n.*?(?=^## )", changelog, re.M | re.S)` to `re.search(r"^## Unreleased\n.*?(?=^## |\Z)", changelog, re.M | re.S)` and change the error text to `"CHANGELOG.md has no '## Unreleased' section"`. Second, replace `NEEDS_FRAGMENT = ("src/", "catalog/", "docs/guides/")` with `NEEDS_FRAGMENT = ("hammunition_console/", "bin/", "install.sh", "uninstall.sh")` and the sentence in `pr_problem` that names `src/, catalog/ or docs/guides/` with `hammunition_console/, bin/ or the installers`.

Create `CHANGELOG.md`:

```markdown
<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Changelog

One entry per release, assembled from the fragments each merged pull request adds under
`changelog.d/` (never edited here in a pull request).

## Unreleased

Nothing yet.
```

Create `changelog.d/README.md`:

```markdown
One file per change: `changelog.d/<pr-or-branch>.<kind>.md`, kind one of `added`, `changed`, `fixed`,
`removed`, `docs`, `decision`, holding one entry that starts with its `- ` bullet. Never edit
`CHANGELOG.md` in a pull request; `python3 scripts/changelog.py assemble --version vX.Y.Z --date YYYY-MM-DD`
writes the release section and deletes the fragments.
```

Create `changelog.d/first-release.added.md`:

```markdown
- **The first release.** A full-screen terminal front end for the Hammunition engine: Home (health, station, last run, units behind their pin, a first-run checklist), Install (profiles and units, the engine's plan, then the real command in a terminal pane where a person types any consent), Station, Logs, Update and Help. It reads only `hammunition <verb> --json`, never passes the engine's assume-yes flag, never sets a scripted-consent variable, and stores only its own config. Needs `python3-urwid` 2.6 or later and the engine 0.19.0 or later; the engine's per-profile installed state and its `update` report for retired units are used when present and shown as unknown when not.
```

Create `tests/test_changelog.py`:

```python
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "changelog.py"


def load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("changelog_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["changelog_script"] = module
    spec.loader.exec_module(module)
    return module


def tree(tmp_path: Path, changelog: str) -> Path:
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "x.added.md").write_text("- Added a thing.\n")
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    return tmp_path


def test_a_first_release_can_be_assembled_from_an_unreleased_only_changelog(tmp_path: Path) -> None:
    root = tree(tmp_path, "# Changelog\n\n## Unreleased\n\nNothing yet.\n")
    done = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "assemble", "--version", "v0.1.0", "--date", "2026-10-03"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    text = (root / "CHANGELOG.md").read_text()
    assert "## Unreleased\n\nNothing yet." in text and "## v0.1.0 — 2026-10-03" in text and "- Added a thing." in text
    assert not (root / "changelog.d" / "x.added.md").exists()


def test_the_real_changelog_says_nothing_yet_until_a_release_is_cut() -> None:
    assert "## Unreleased\n\nNothing yet." in (ROOT / "CHANGELOG.md").read_text()


def test_the_real_fragments_preview_cleanly() -> None:
    done = subprocess.run([sys.executable, str(SCRIPT), "preview"], capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0 and "first release" in done.stdout


def test_a_pull_request_that_changes_the_package_needs_a_fragment() -> None:
    mod = load()
    assert mod.pr_problem(["hammunition_console/app.py"], [], []) is not None
    assert mod.pr_problem(["hammunition_console/app.py", "changelog.d/9.fixed.md"], ["changelog.d/9.fixed.md"], []) is None
    assert mod.pr_problem(["README.md"], [], []) is None
```

Run: `python3 -m pytest tests/test_changelog.py -v`
Expected: PASS after the two edits (FAIL on the first test before them: "has no '## Unreleased' section followed by a release").

- [ ] **Step 2: The version check, its tests, and the tag's agreement with the tree**

Create `scripts/check_version.py`:

```python
#!/usr/bin/env python3
"""Refuse a release tag that disagrees with the tree it points at.

The tag is the one release input a human types. A v0.2.0 tag on a package that says
0.1.0 publishes a version number that means two things."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def check(tag: str, root: Path) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError(f"tag {tag!r} is not vMAJOR.MINOR.PATCH")
    wanted = tag[1:]
    init = (root / "hammunition_console" / "__init__.py").read_text()
    match = re.search(r'^__version__ = "([^"]+)"', init, re.M)
    have = match.group(1) if match else "(none)"
    if have != wanted:
        raise ValueError(f"tag {tag} but __version__ says {have}")
    changelog = (root / "CHANGELOG.md").read_text()
    if not re.search(rf"^## v{re.escape(wanted)}\b", changelog, re.M):
        raise ValueError(f"CHANGELOG.md has no '## v{wanted}' section (run scripts/changelog.py assemble)")
    man = (root / "man" / "hammunition-console.1").read_text()
    if f'"hammunition-console {wanted}"' not in man:
        raise ValueError(f"man/hammunition-console.1 does not say {wanted} in its .TH line")
    return wanted


if __name__ == "__main__":
    try:
        print(check(sys.argv[1], Path(__file__).resolve().parent.parent))
    except (IndexError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
```

Create `tests/test_check_version.py`:

```python
from pathlib import Path

import pytest

from hammunition_console import __version__
from scripts.check_version import check

ROOT = Path(__file__).resolve().parent.parent


def tree(tmp_path: Path, version: str = "0.2.0", section: str = "v0.2.0", man: str = "0.2.0") -> Path:
    (tmp_path / "hammunition_console").mkdir()
    (tmp_path / "hammunition_console" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    (tmp_path / "CHANGELOG.md").write_text(f"## Unreleased\n\nNothing yet.\n\n## {section} — 2026-10-03\n\n- x\n")
    (tmp_path / "man").mkdir()
    (tmp_path / "man" / "hammunition-console.1").write_text(f'.TH HAMMUNITION-CONSOLE 1 "d" "hammunition-console {man}" "H"\n')
    return tmp_path


def test_a_tag_that_agrees_passes(tmp_path: Path) -> None:
    assert check("v0.2.0", tree(tmp_path)) == "0.2.0"


@pytest.mark.parametrize("tag", ["0.2.0", "v0.2", "v0.2.0-rc1", "main"])
def test_a_malformed_tag_is_refused(tag: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        check(tag, tree(tmp_path))


@pytest.mark.parametrize("kw,needle", [({"version": "0.1.9"}, "__version__"), ({"section": "v0.1.0"}, "CHANGELOG"), ({"man": "0.1.0"}, "man/")])
def test_each_disagreement_is_named(kw: dict[str, str], needle: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=needle):
        check("v0.2.0", tree(tmp_path, **kw))


def test_the_man_page_and_the_package_agree_today() -> None:
    assert f'"hammunition-console {__version__}"' in (ROOT / "man" / "hammunition-console.1").read_text()
```

Run: `python3 -m pytest tests/test_check_version.py -v`
Expected: PASS (4 groups).

- [ ] **Step 3: Write the workflows with unresolved pin tokens, then the guard test that refuses them**

Create `.github/workflows/ci.yml`:

```yaml
# CI for hammunition-console. The tests run on the oldest Python the console supports
# and the newest, against the oldest urwid it supports (2.6.10, Ubuntu 24.04's), the
# one Debian 13 and Parrot ship (2.6.16) and the newest (3.0.4, Ubuntu 26.04 and
# Kali's); and against each archive's own python3-urwid, which is what the console
# depends on in the field. Actions are pinned by commit, resolved with
# `git ls-remote --tags`; a tag reaches shell only through env.
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    name: ruff, mypy --strict, headers
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@PIN_CHECKOUT
        with:
          persist-credentials: false
      - uses: actions/setup-python@PIN_SETUP_PYTHON
        with:
          python-version: "3.13"
      - run: python -m pip install ruff mypy pytest "urwid==3.0.4"
      - run: python -m ruff check .
      - run: python -m mypy
      - run: python scripts/spdx.py --check

  test:
    name: tests (Python ${{ matrix.python }}, urwid ${{ matrix.urwid }})
    runs-on: ubuntu-24.04
    strategy:
      fail-fast: false
      matrix:
        include:
          - {python: "3.11", urwid: "2.6.10"}
          - {python: "3.13", urwid: "2.6.16"}
          - {python: "3.13", urwid: "3.0.4"}
    steps:
      - uses: actions/checkout@PIN_CHECKOUT
        with:
          persist-credentials: false
      - uses: actions/setup-python@PIN_SETUP_PYTHON
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install pytest "urwid==${{ matrix.urwid }}"
      - run: python -m pytest -v

  archive-ubuntu:
    name: tests (Ubuntu 24.04 archive urwid, system python3)
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@PIN_CHECKOUT
        with:
          persist-credentials: false
      - run: sudo apt-get update -qq && sudo apt-get install -y -qq python3-urwid python3-pytest
      - run: /usr/bin/python3 -c "import urwid; print('urwid', urwid.__version__)"
      - run: /usr/bin/python3 -m pytest -v

  archive-debian:
    name: tests (Debian 13 archive urwid, system python3)
    runs-on: ubuntu-24.04
    container: debian:trixie
    steps:
      - run: apt-get update -qq && apt-get install -y -qq python3-urwid python3-pytest git
      - uses: actions/checkout@PIN_CHECKOUT
        with:
          persist-credentials: false
      - run: python3 -c "import urwid; print('urwid', urwid.__version__)"
      - run: python3 -m pytest -v

  shell:
    name: shellcheck
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@PIN_CHECKOUT
        with:
          persist-credentials: false
      - run: sudo apt-get update -qq && sudo apt-get install -y -qq shellcheck
      - run: shellcheck install.sh uninstall.sh bin/hammunition-console
```

Create `.github/workflows/release.yml`:

```yaml
# Cut a release when a v* tag is pushed. verify refuses a tag that disagrees with the
# tree; test runs the suite; publish creates the GitHub release with the changelog
# section and the sha256 of GitHub's source archive for the tag, fetched twice and
# compared, which is the digest the Hammunition catalog unit pins. The tag reaches
# shell only through env, never through ${{ }} inside run.
name: release

on:
  push:
    tags: ["v*"]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    name: the tag agrees with the tree
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@PIN_CHECKOUT
        with:
          persist-credentials: false
      - name: the tag, the version, the man page and the changelog agree
        env:
          TAG: ${{ github.ref_name }}
          REF: ${{ github.ref }}
        run: |
          set -euo pipefail
          case "$REF" in
            refs/tags/v*) python3 scripts/check_version.py "$TAG" ;;
            *) python3 scripts/check_version.py "v$(python3 -c 'from hammunition_console import __version__ as v; print(v)')" ;;
          esac

  test:
    name: tests
    needs: verify
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@PIN_CHECKOUT
        with:
          persist-credentials: false
      - uses: actions/setup-python@PIN_SETUP_PYTHON
        with:
          python-version: "3.13"
      - run: python -m pip install pytest "urwid==3.0.4"
      - run: python -m pytest -v

  publish:
    name: publish
    needs: test
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@PIN_CHECKOUT
        with:
          persist-credentials: false
      - name: publish
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ github.ref_name }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          awk -v v="${TAG}" 'index($0, "## " v) == 1 {f=1; next} /^## / {f=0} f' CHANGELOG.md > notes.md
          test -s notes.md
          url="https://github.com/${REPO}/archive/refs/tags/${TAG}.tar.gz"
          curl -fsSL "$url" -o a.tgz
          curl -fsSL "$url" -o b.tgz
          cmp a.tgz b.tgz
          sum="$(sha256sum a.tgz | cut -d' ' -f1)"
          {
            echo
            echo "Source archive: ${url}"
            echo "sha256: ${sum}"
            echo "bytes: $(stat -c %s a.tgz)"
          } >> notes.md
          gh release create "$TAG" --repo "$REPO" --title "hammunition-console $TAG" --notes-file notes.md
```

Create `tests/test_workflows.py`:

```python
import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)@(\S+)(?:\s+#\s*(v\S+))?\s*$")
ENV_ASSIGN = re.compile(r"^\s+[A-Z][A-Z_]*:\s+\$\{\{[^}]+\}\}\s*$")
SAFE_KEYS = re.compile(r"^\s*(if|group|name|runs-on|python-version|cancel-in-progress):")


def test_there_are_workflows() -> None:
    assert {w.name for w in WORKFLOWS} == {"ci.yml", "release.yml"}


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_resolved_commit_with_its_tag_in_a_comment(path: Path) -> None:
    uses = [USES.match(line) for line in path.read_text().splitlines() if "uses:" in line]
    assert uses, "no actions found"
    for m in uses:
        assert m, "an unparsable `uses:` line"
        assert re.fullmatch(r"[0-9a-f]{40}", m.group(2)), (
            f"{path.name}: {m.group(1)}@{m.group(2)} is not a commit; resolve it with `git ls-remote --tags` (see Task 18)")
        assert m.group(3), f"{path.name}: {m.group(1)} pin has no `# vX.Y.Z` tag comment"
    assert "PIN_" not in path.read_text()


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_a_tag_or_ref_never_reaches_shell_except_through_env(path: Path) -> None:
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if "${{" not in line:
            continue
        ok = ENV_ASSIGN.match(line) or SAFE_KEYS.match(line) or ("matrix." in line and "github." not in line)
        assert ok, f"{path.name}:{number}: an expression outside env/if/group/matrix: {line.strip()}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_permissions_default_to_read_only(path: Path) -> None:
    assert re.search(r"^permissions:\n  contents: read$", path.read_text(), re.M)
```

Run: `python3 -m pytest tests/test_workflows.py -v`
Expected: FAIL in `test_every_action_is_pinned...` ("PIN_CHECKOUT is not a commit; resolve it..."). Everything else passes.

- [ ] **Step 4: Resolve the pins from the network, never from memory**

```bash
cd /home/chiefgyk3d/src/hammunition-console
for repo in actions/checkout actions/setup-python; do
  echo "== $repo"
  git ls-remote --tags "https://github.com/$repo" 'refs/tags/v*' | grep -v '\^{}' | sed 's|.*refs/tags/||' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -3
done
```
Expected: the three newest full-version tags of each action. Choose the newest of each (`TAG_CHECKOUT`, `TAG_SETUP`); do not pick a pre-release.

```bash
resolve() { git ls-remote "https://github.com/$1" "refs/tags/$2" "refs/tags/$2^{}" | awk '{print $1}' | tail -1; }
TAG_CHECKOUT=<the tag printed above for actions/checkout>
TAG_SETUP=<the tag printed above for actions/setup-python>
SHA_CHECKOUT=$(resolve actions/checkout "$TAG_CHECKOUT"); SHA_SETUP=$(resolve actions/setup-python "$TAG_SETUP")
echo "$SHA_CHECKOUT $SHA_SETUP" | grep -E '^[0-9a-f]{40} [0-9a-f]{40}$'
```
Expected: one line of two 40-hex commits (the peeled commit of an annotated tag, the commit itself of a lightweight one). Then:

```bash
sed -i "s|actions/checkout@PIN_CHECKOUT|actions/checkout@${SHA_CHECKOUT} # ${TAG_CHECKOUT}|; s|actions/setup-python@PIN_SETUP_PYTHON|actions/setup-python@${SHA_SETUP} # ${TAG_SETUP}|" .github/workflows/ci.yml .github/workflows/release.yml
grep -n "uses:" .github/workflows/*.yml | head -3 && python3 -m pytest tests/test_workflows.py -v
```
Expected: the `uses:` lines show 40-hex pins with `# vN.N.N` comments; the workflow tests PASS. Re-run these commands whenever a workflow is touched.

Falsify the pin guard: temporarily change one pin to `@v5` and run the test: FAIL naming the file; revert.

- [ ] **Step 5: Commit**

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the changelog tooling, version check, CI and release workflows"
```
Expected: clean, all pass.

---

### Task 19: README, the contract note, and the checks that keep them true

**Files:**
- Create: `README.md`, `docs/contract.md`
- Test: `tests/test_docs.py`

**Interfaces:**
- Consumes: `helptext.KEYS`, `verbs.JSON_VERBS`, `config.SCREENS`, `fixture_scan.findings`.
- Produces: the README sections `What it is`, `Requirements`, `Install`, `How it works`, `What it never does`, `Keys`, `Screens`, `Status`, `Development`, `Licence`; `docs/contract.md` naming every verb the console reads.

- [ ] **Step 1: Write the checks (failing first)**

Create `tests/test_docs.py`:

```python
from pathlib import Path

from hammunition_console.config import SCREENS
from hammunition_console.helptext import KEYS
from hammunition_console.verbs import JSON_VERBS
from tests.fixture_scan import findings

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
CONTRACT = (ROOT / "docs" / "contract.md").read_text()


def test_the_readme_has_every_required_section() -> None:
    for heading in ("What it is", "Requirements", "Install", "How it works", "What it never does", "Keys", "Screens",
                    "Status", "Development", "Licence"):
        assert f"\n## {heading}\n" in README, heading


def test_the_keys_table_lists_every_key_in_the_help() -> None:
    for keys, meaning in KEYS:
        assert f"| `{keys}` | {meaning} |" in README, f"README keys table is out of step with helptext.KEYS: {keys}"


def test_the_readme_names_every_screen_and_counts_them_right() -> None:
    assert "six screens" in README and len(SCREENS) == 6
    for screen in SCREENS:
        assert screen.capitalize() in README


def test_the_status_section_says_what_has_not_run_on_real_hardware() -> None:
    status = README.split("\n## Status\n")[1].split("\n## ")[0]
    assert "has not been run" in status and "real target" in status and "urwid.Terminal" in status


def test_the_readme_and_contract_carry_no_identifier() -> None:
    assert findings(README) == [] and findings(CONTRACT) == []


def test_the_contract_lists_every_verb_the_console_reads_and_both_engine_prerequisites() -> None:
    for verb in JSON_VERBS:
        assert f"`hammunition {' '.join(verb)}`" in CONTRACT, verb
    assert "E1" in CONTRACT and "E2" in CONTRACT and "unknown" in CONTRACT


def test_the_readme_says_how_the_three_channels_differ() -> None:
    assert "worker thread" in README and "terminal pane" in README and "config.toml" in README
```

Run: `cd /home/chiefgyk3d/src/hammunition-console && python3 -m pytest tests/test_docs.py -v`
Expected: FAIL (`FileNotFoundError: README.md`).

- [ ] **Step 2: Write the README**

Create `README.md`:

````markdown
# hammunition-console

A full-screen terminal front end for the [Hammunition](https://github.com/ChiefGyk3D/Hammunition) engine. It shows what is
installed, what is wrong and what to do next, and runs the engine's own commands for you, so a licensed operator can get from
a fresh machine to a working station without remembering the CLI's verbs. It works over SSH and on a Pi.

It is a client of the engine, not part of it: it has no install logic, no package names and no catalog parser. It asks the engine.

## What it is

Six screens: Home, Install, Station, Logs, Update and Help. Every action is a command you could type yourself, and the console
shows it before it runs. Hardware and maps are left to the CLI and to
[hammunition-tray](https://github.com/ChiefGyk3D/hammunition-tray) for now.

## Requirements

- Hammunition 0.19.0 or later on `PATH` (the engine's `--json` interface, D-059). Install it first; this console never installs it.
- Python 3.11 or later and `python3-urwid` 2.6 or later (Debian 13 and Parrot ship 2.6.16, Ubuntu 24.04 ships 2.6.10, Ubuntu 26.04
  and Kali ship 3.0.4).
- A terminal of at least 80x24. It refuses to start without a terminal, with `TERM=dumb`, or as root.

## Install

Through Hammunition, once a release is cataloged:

```sh
hammunition install hammunition-console
```

From a checkout, for your own account, with no pip and no virtualenv:

```sh
sudo apt install python3-urwid
./install.sh            # into ~/.local; --prefix DIR and --interpreter PATH are the options
hammunition-console
```

`./uninstall.sh` removes what `install.sh` placed and leaves `~/.config/hammunition-console/` alone. To try it without
installing, `python3 -m hammunition_console` from the checkout works.

## How it works

Three channels, each with one job.

1. **Reads** run `hammunition <verb> --json` in a worker thread and parse the one document it prints. The console reads only
   the verbs listed in [docs/contract.md](docs/contract.md), refuses a document whose `schema` it does not know, and reads the
   engine's version from the first document's `engine` field.
2. **Writes** run the real `hammunition` command inside a terminal pane. The child owns the tty: sudo's password prompt, the
   group choice and any consent prompt reach the engine untouched, typed by you. The console sees only the exit code, then
   reads again.
3. **Its own config**, `~/.config/hammunition-console/config.toml`: the last screen, the colour theme, whether you dismissed
   the first-run checklist. Nothing else. (A crash writes `crash.log` beside it with the exception type and its frames, never a
   message.)

The plan always comes first: choosing a profile shows the engine's own dry run (`--dry-run`), grouped as the engine groups it,
and nothing runs until you press `R` on it.

## What it never does

- It never answers a consent prompt for you, never passes the engine's assume-yes flag, never sets a scripted-consent
  environment variable, and removes any you exported from the environment of everything it starts.
- It never holds a station value: your callsign and grid square live in the engine's station file, the header says only
  "station: set" or "not set", and the Station screen hides values until you ask.
- It never fetches anything from the network, never pipes anything into a shell, and never runs a `doctor` fix (it shows the
  engine's fix text and leaves the command to you).
- It never runs as root.

## Keys

| Keys | Meaning |
|---|---|
| `1-5` | open the screen with that number (Home) |
| `Enter` | open the selected row |
| `b / Esc` | go back; changes nothing |
| `?` | help |
| `q` | quit |
| `r` | refresh this screen |
| `R` | run the planned command in a terminal pane (plan and confirm screens) |
| `Tab` | switch between profiles and single units (Install) |
| `U` | plan an uninstall of the selected profile (Install) |
| `i` | the selected profile's documentation (Install) |
| `v` | reveal or hide station values (Station) |
| `c` | clear the selected value, where the engine can (Station) |
| `u` | also ask upstream whether the catalog's pins are current (Update) |
| `A` | run the apt upgrade the report offers (Update) |
| `B` | plan the rebuilds the report offers (Update) |
| `s` | skip the selected first-run step (Home) |
| `D` | dismiss the first-run checklist (Home) |

## Screens

- **Home**: the engine's health check, whether the station is set, the last run, units behind their pin, and a first-run
  checklist (set the station, apply the hardware rules, pick a profile, install it).
- **Install**: profiles, and with `Tab` single units; the plan; the run.
- **Station**: the saved values, changed by running the engine's own `station set`.
- **Logs**: each run the engine recorded, newest first; a run in progress is followed live.
- **Update**: installed against the catalog; `u` also asks upstream.
- **Help**: keys, what the console never does, and what each profile is for.

## Status

First release. What has run: the whole suite (unit tests against fixtures recorded from the engine, a fake `hammunition` that
asks for `yes` on a real pseudo-terminal, and the console driven end to end in one) on Python 3.11 and 3.13 against urwid
2.6.10, 2.6.16 and 3.0.4 and the Debian 13 and Ubuntu 24.04 archives' own `python3-urwid`.

What has not been run: a real `hammunition install` through the pane on a real target; urwid's `urwid.Terminal` against a
real engine install on any machine; the engine's per-profile installed state and its `update` report for retired units
(engine work E1 and E2) were built against recorded fixtures, so each screen that reads them shows "unknown" when they are
absent; Raspberry Pi OS, Pop!_OS and Mint are inferred from their bases, not run. A claim about hardware belongs here only after
it has run there.

## Development

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt "urwid==2.6.16"
python3 -m pytest          # also: ruff check . ; mypy ; python3 scripts/spdx.py --check
```

Fixtures are recorded by `scripts/capture_fixtures.py` from a real engine on a throwaway home with the station set to
`N0CALL` and `FN31pr`, scrubbed, and scanned for identifiers; review every new fixture by eye before committing. Never edit
`CHANGELOG.md` in a pull request: add `changelog.d/<pr>.<kind>.md`.

## Licence

GPL-3.0-or-later. Copyright Renegade Penguin LLC.
````

- [ ] **Step 3: Write the contract note**

Create `docs/contract.md`:

````markdown
# What the console reads, and how each screen degrades

The console reads only `hammunition <verb> --json` (docs/reference/json-interface.md in the engine repository). Every read runs in
a worker thread. A document whose `schema` is not `hammunition/1` is refused by name; one whose `engine` field is older than
`ENGINE_FLOOR` in `hammunition_console/engine.py` stops the console with both versions named. A read that fails shows the
engine's own message and is never retried silently.

Engine prerequisites: **E1** is per-profile `members`, `installed` and `installed_size_bytes` on each profile of
`hammunition list`; **E2** is `hammunition update` reporting retired units as rows with exit 0 (engine issue 239). Both are
treated as present; each screen that reads them shows "unknown" when they are not.

| Screen | Reads | Fields used | When a field or document is missing |
|---|---|---|---|
| Home | `hammunition status` | `target`, `engine` | the header says `?` |
| Home | `hammunition doctor` | `fails`, `warns`, `healthy`, `checks[].name/status/detail/fix` | the counts say `?`; `fix` is shown, never run |
| Home | `hammunition station show` | `callsign`, `grid_square` (only whether each is set) | "station: ?" |
| Home | `hammunition logs` | `runs[0]` | "no runs yet" |
| Home | `hammunition update` | `counts.behind_pin`, rows in state `retired` | without E2 the engine refuses with exit 2: "unknown (the engine's words)" |
| Home | `hammunition list` | the starter profile's `members`, `installed` (E1) | the checklist's install steps show `[?]` |
| Install | `hammunition list` | profiles: `name`, `stage`, `summary`, `consent_gated`, `packages`, `documentation`, E1 fields; units: `name`, `status`, `summary`, `resolves_here` | without E1: "N units, state unknown" |
| Install | `hammunition install NAMES --dry-run`, `hammunition uninstall NAMES --dry-run` | the whole plan: every section of `InstallPlanView` and `RemovalPlanView`, `blockers` | a refused plan shows its blockers and offers no run |
| Station | `hammunition station show` | every station field | an unset field says "not set" |
| Station | `hammunition maps regions FILTER`, `hammunition reference books` | `regions`; `books[].id/title/licence` | the chooser shows the engine's error |
| Logs | `hammunition logs` | `directory`, `runs[].path/started/command/result/exit_code/size` | "No runs yet." A path outside `directory` is never opened |
| Update | `hammunition update [NAMES] [--upstream]` | `counts`, `rows`, `lists_note`, `upgrade_command`, `rebuild_command`, `upstream` | without E2: the refusal is shown and a per-profile list is offered |
| Help | `hammunition list`, `hammunition show PROFILE` | `documentation.*`, `consent.disclosure`, `suggests_one_of` | the engine's error is shown |

Writes (never read as JSON): `hammunition install|uninstall NAMES`, `hammunition station set --FLAG=VALUE`,
`hammunition hardware apply`, and the apt upgrade command the `update` report prints (run without apt's assume-yes, so apt
asks). All of them run in a terminal pane.

`hammunition services`, `hammunition artifacts`, `hammunition maps phone` and the other documents the engine publishes are not
read in this release.
````

- [ ] **Step 4: Run the checks; commit**

Run: `python3 -m pytest tests/test_docs.py -v`
Expected: PASS (7 passed). If the keys-table test fails on one row, the README row and the `KEYS` tuple differ by one character; make the README match `helptext.KEYS` exactly.

Falsify the key check: delete the `| \`B\` |` row from the README and run the test: FAIL naming `B`. Restore it.

```bash
cd /home/chiefgyk3d/src/hammunition-console && python3 scripts/spdx.py --fix && python3 -m ruff check --fix . && python3 -m mypy && python3 -m pytest -q && git add -A && git commit -m "Add the README and the contract note, with checks that keep them true"
```
Expected: clean, all pass.

- [ ] **Step 5: Push the branch and open the pull request (the maintainer merges)**

```bash
cd /home/chiefgyk3d/src/hammunition-console && git push -u origin first-release && gh pr create --base main --head first-release --title "The first release: Home, Install, Station, Logs, Update, Help" --body "Implements the spec in Hammunition's docs/superpowers/specs/2026-10-03-console-design.md (rulings in section 12). Tasks 1-19 of the plan. CI runs the tests against urwid 2.6.10, 2.6.16 and 3.0.4 and the Debian 13 and Ubuntu 24.04 archives.

Not run: a real install through the pane on a real target (README Status).

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```
Expected: a PR URL. Watch CI: `gh pr checks --watch`. Expected: every job green. A job that fails on urwid 3.x or on an archive's urwid is a real finding (API drift is unmeasured until now): fix the code, not the matrix. Merging is the maintainer's.

---

### Task 20: The engine side: catalog unit, docs page, fragment (in the Hammunition repository)

Everything here happens in `/home/chiefgyk3d/src/Hammunition` on its own branch, after Task 19's PR is merged and the maintainer has tagged `v0.1.0` (Phase B needs the tag). Phase A can be done and pushed as a draft PR before the tag exists; its pin test is red on purpose until Phase B.

**Files:**
- Create: `catalog/packages/hammunition-console.yaml`, `docs/getting-started/console.md`, `changelog.d/console-unit.added.md`, `tests/test_hammunition_console_unit.py`
- Modify: `mkdocs.yml` (nav), `docs/packages/hammunition-console.md` and `docs/projects.md` (regenerated, not edited)

**Interfaces:**
- Consumes: the console's release `v0.1.0`; the engine's `install_tree` binary backend and `launchers` (the shape of `catalog/packages/skid-finder.yaml`); `scripts/gen_package_reference.py`, `scripts/gen_projects_page.py`, `scripts/check_pin_reviews.py`.
- Produces: `hammunition install hammunition-console` (by name, in no profile).

#### Phase A: before the tag

- [ ] **Step 1: A branch, and the pin test first (red until Phase B)**

```bash
cd /home/chiefgyk3d/src/Hammunition && git fetch -q origin && git checkout -b console-unit origin/main && git status --short
```
Expected: clean on a new branch `console-unit` from `origin/main`. (Do not touch the other worktrees' branches. Check `git worktree list` first; `console-spec` lives in its own worktree.)

Create `tests/test_hammunition_console_unit.py`:

```python
"""The hammunition-console unit pins a tag's source archive, like hammunition-tray (D-024)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "catalog" / "packages" / "hammunition-console.yaml"


def load() -> dict:  # type: ignore[type-arg]
    return yaml.safe_load(MANIFEST.read_text())  # type: ignore[no-any-return]


def test_the_digest_is_a_real_release_digest_not_the_draft_zeros() -> None:
    block = load()["install"][0]["install"]
    assert block["artifact"]["sha256"] != "0" * 64, (
        "fill the pin at release: Phase B of the console plan's Task 20 says which command produces it")


def test_the_pin_is_the_version_the_manifest_declares() -> None:
    data = load()
    url = data["install"][0]["install"]["artifact"]["url"]
    assert url == f"https://github.com/ChiefGyk3D/hammunition-console/archive/refs/tags/v{data['version']}.tar.gz"


def test_it_depends_on_the_archives_urwid_and_nothing_is_fetched_by_pip() -> None:
    data = load()
    assert "python3-urwid" in data["depends"] and "python3" in data["depends"]
    methods = {b["install"]["method"] for b in data["install"]}
    assert methods == {"binary"}, "no venv, no pip, no pipx (D-014)"


def test_it_is_in_no_profile() -> None:
    for path in (ROOT / "catalog" / "profiles").glob("*.yaml"):
        assert "hammunition-console" not in path.read_text(), f"{path.name} must not include it yet"


def test_it_has_a_terminal_launcher_for_the_menu() -> None:
    launcher = load()["launchers"][0]
    assert launcher["terminal"] is True and launcher["name"] == "hammunition-console"
    assert launcher["exec"].endswith("/hammunition-console/bin/hammunition-console")
```

Run: `python3 -m pytest tests/test_hammunition_console_unit.py -q`
Expected: FAIL (`FileNotFoundError` for the manifest).

- [ ] **Step 2: The manifest (the digest is the draft zeros until Phase B)**

Create `catalog/packages/hammunition-console.yaml`:

```yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0

name: hammunition-console
version: "0.1.0"
summary: A terminal front end for the engine: install, station, logs and updates in one full-screen program
categories: [workstation]

# ADD. Like hammunition-tray and gps-tether, a unit whose upstream is this project's own
# maintainer, disclosed here: a separate repository (GPL-3.0-or-later), its own releases and
# tests, carried on the same terms as everything else: a published, digest-pinned artifact.
#
# The pin is the tag's source archive (the D-024 reasoning, as for the tray). It is a pure
# Python tree run in place with the archive's python3 and python3-urwid: no build, no pip,
# no venv, no network after the fetch (D-014). The console imports no engine code and reads
# only `hammunition <verb> --json` (D-059); every change it makes is the real CLI run in a
# terminal pane, so a consent gate is answered by a person (D-021).
#
# DRAFT: the digest below is all zeros until the v0.1.0 tag exists. The release workflow
# prints the archive's sha256 in the release notes; Phase B of the plan fills it in, with
# the tag's commit and the archive's size, each measured, and the pin test then goes green.
install:
  - install:
      method: binary
      artifact:
        url: https://github.com/ChiefGyk3D/hammunition-console/archive/refs/tags/v0.1.0.tar.gz
        sha256: "0000000000000000000000000000000000000000000000000000000000000000"
      format: tarball
      install_tree: true
      # GitHub's tag tarballs have one top directory, which extraction strips.
      tree_marker: hammunition_console/__main__.py
    note: >-
      The tag's source tree, installed to /usr/local/share/hammunition/hammunition-console
      and handed to the operator, with a launcher named hammunition-console in ~/.local/bin
      and a terminal menu entry. Nothing is built and nothing runs as root but the copy.
      The console's own configuration, ~/.config/hammunition-console/, is created by the
      program when it first runs and is left in place on uninstall.

depends: [python3, python3-urwid]

launchers:
  - name: hammunition-console
    exec: /usr/local/share/hammunition/hammunition-console/bin/hammunition-console
    title: Install and manage the station from a terminal (hammunition-console)
    terminal: true

update:
  probe:
    method: github_release
    repo: ChiefGyk3D/hammunition-console
  strategy: reinstall
  cadence_hint: >-
    Tagged releases; each is a new source-archive digest. Re-pin the URL and the digest
    together at every tag, never from a branch.

documentation:
  what_it_does: >-
    A full-screen terminal program that shows what Hammunition has installed on this
    machine, what is wrong, and what to do next, and runs the engine's own commands for you.
    Home shows the health check, whether your station is set, the last run and how many
    units are behind the catalog's pin, with a four-step first-run checklist. Install lists
    the profiles and units, shows the engine's own plan, then runs the real command in a
    terminal pane. Station, Logs, Update and Help round it out. It works over SSH and on a Pi.
  why_you_want_it: >-
    You would rather pick from a list than remember the CLI's verbs, or you are walking a
    fresh machine to a working station for the first time. It is a front end for the
    commands in docs/reference/cli.md and does exactly what they do and nothing else; it is
    the alternative to typing them. Because it runs each change in a real terminal, sudo and
    every consent prompt are the engine's and are answered by you, never by the console.
  prerequisites: >-
    The engine itself, 0.19.0 or later, on PATH (this unit does not install it), and a
    terminal of at least 80x24. Nothing is configured first; the Station screen sets the
    values the engine needs. Python 3.11 or later, which every target but Ubuntu 22.04 and
    Pop!_OS 22.04 ships.
  known_problems: >-
    **First release; not yet run through a real install on any target.** It was tested
    against recorded engine documents and a fake engine on a real pseudo-terminal, not
    against a real install through its terminal pane on the field laptop; that is a bench
    item. The engine's per-profile installed state and its update report for retired units
    are used when the engine sends them and shown as "unknown" when it does not. Hardware
    and maps screens are not in this release: use the CLI and hammunition-tray. A per-user
    copy placed by the console repository's own install.sh (~/.local/bin/hammunition-console)
    shadows or conflicts with this unit's launcher; run that repository's uninstall.sh once
    before installing the unit. It refuses to start without a terminal, with TERM=dumb, or as root.
  upstream_url: https://github.com/ChiefGyk3D/hammunition-console
  upstream_support: >-
    Issues on the hammunition-console repository for the console itself; the engine's own
    docs and `hammunition doctor` for anything the engine reports.
```

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('catalog/packages/hammunition-console.yaml')); print('yaml ok')" && python3 -m pytest tests/test_hammunition_console_unit.py -q`
Expected: `yaml ok`, then 4 passed and 1 FAILED (`test_the_digest_is_a_real_release_digest...`, the draft-zeros guard, red on purpose).

- [ ] **Step 3: Validate the manifest against the engine's own checks**

Run: `HAMMUNITION_CATALOG=$PWD/catalog python3 -m hammunition show hammunition-console --json 2>&1 | head -5; python3 -m hammunition list packages 2>&1 | grep hammunition-console`
Expected: the unit loads (a `unit` document with `resolves_here: binary`) and appears in the list. If the schema rejects the zero digest, the error names the field: use `"deadbeef"` repeated to 64 hex characters as the draft digest, and let the pin test's "all zeros" check become `!= "deadbeef" * 8`. If the launcher validator rejects a field, read the error; `catalog/packages/skid-finder.yaml` is the working shape. Then: `python3 -m hammunition install hammunition-console --dry-run 2>&1 | tail -20`
Expected: a plan listing the fetch of the v0.1.0 archive, the tree install under `/usr/local/share/hammunition/hammunition-console`, the `chown` hand-over, the launcher and menu entry. It reaches the network only for the engine's own HEAD checks, if any; it must not install anything (`--dry-run`).

- [ ] **Step 4: The docs page, nav, and fragment**

Create `docs/getting-started/console.md`:

````markdown
# The console

`hammunition-console` is a full-screen terminal program for the same commands this documentation describes. It shows what is
installed, what is wrong and what to do next, and runs the engine's own commands for you, so you can walk from a fresh install
to a working station without remembering the verbs. It works over SSH and on a Pi. It is its own project, with its own
releases, at <https://github.com/ChiefGyk3D/hammunition-console>.

It is a client of the engine. It has no install logic and no package names of its own; it asks the engine, and everything it
does is a command you could type, which it shows you first. It is the alternative to typing them, not a replacement for the
[command reference](../reference/cli.md).

## Install it

Install the engine first ([install the engine](install.md)); the console never does that. Then:

```sh
hammunition install hammunition-console
```

That is by name: it is in no profile. The plan lists exactly what is placed (below). Then run `hammunition-console` from a
terminal, or pick it from the desktop menu.

It needs a terminal of at least 80x24 and refuses to start without one, with `TERM=dumb`, or as root.

## Your first run: four steps

Home shows a checklist the first time. Each step is optional, skippable (`s`) and resumable, and the state is read from the
engine each time, so the list is always true. `D` dismisses it for good.

1. **Set your station.** Opens Station and runs the engine's own `hammunition station set`. The console never holds the
   value: the engine's station file does, and the Station screen hides it until you press `v`. Nothing is invented; a missing
   value only defers the one file that needed it ([D-035](../reference/cli.md)).
2. **Apply the hardware rules.** Shows the command, `hammunition hardware apply`, and runs it in a terminal pane. That command
   prints its own plan and asks for its own typed confirmation and your sudo password; the console cannot show the plan first
   because the engine has no JSON form of it yet, and says so. The checklist shows this step as unknown, never done, because
   no engine document reports whether the rules are applied.
3. **Pick a profile.** Opens Install with `station`, the floor everything stands on, selected, and shows why its units belong
   together and what you still set up by hand.
4. **Install.** The engine's plan comes first, grouped as the engine groups it: units in order, third-party repositories with
   their pinned key fingerprints, offline data with size and licence, group memberships, files written, what will not
   happen, and every consent gate. Nothing has changed while you read it. Press `R` and the real command runs in a terminal
   pane; you type any `yes` yourself.

## What it writes on your machine

- The program's tree under `/usr/local/share/hammunition/hammunition-console`, handed to your account by the engine's
  `chown` step, with a launcher in `~/.local/bin/hammunition-console` and a terminal menu entry. Nothing runs as root but
  the copy.
- Its own configuration, `~/.config/hammunition-console/config.toml`, created when it first runs: the last screen, the
  colour theme and whether you dismissed the checklist. Nothing else, and never a station value. A crash writes `crash.log`
  beside it with the exception's type and frames, never a message.

Inspect with `ls -l ~/.local/bin/hammunition-console /usr/local/share/hammunition/hammunition-console`. Remove with
`hammunition uninstall hammunition-console`; the configuration directory is left, and `rm -r
~/.config/hammunition-console` removes it.

## What it never does

It never answers a consent prompt for you and never passes the engine's assume-yes flag ([D-021](../reference/cli.md)); it
removes any scripted-consent variable you exported from the environment of everything it starts. It never fetches anything
from the network. It never runs a `doctor` fix. Every read is `hammunition <verb> --json` ([D-059](../reference/json-interface.md)).

## What was measured, and what was not

Measured: the console's test suite runs against documents recorded from the engine, against a fake engine that asks for `yes`
on a real pseudo-terminal, and drives the whole program in one, on Python 3.11 and 3.13 with urwid 2.6.10, 2.6.16 and 3.0.4
and the Debian 13 and Ubuntu 24.04 archives' own `python3-urwid`.

Not measured: a real install through the console's terminal pane on a real target, which is a bench item; the engine's
per-profile installed state and its update report for retired units, which the console treats as present and shows as
"unknown" when absent; Hardware and maps screens, which are not in the first release.
````

In `mkdocs.yml`, add under `Getting started:` after `First contact`:

```yaml
      - The console: getting-started/console.md
```

Create `changelog.d/console-unit.added.md`:

```markdown
- **`hammunition-console` is a catalog unit** (**D-059**, **D-021**; branch `console-unit`): a terminal front end in its own repository, pinned by its tag's source-archive sha256 like the tray, installed by name and in no profile, with a terminal menu entry. It reads only `--json` documents and runs every change in a pane where a person types any consent. `docs/getting-started/console.md` walks the first run. Rename this fragment to `<PR number>.added.md` when the pull request has a number.
```

- [ ] **Step 5: Regenerate what is generated, run the engine's checks, and commit (draft PR)**

```bash
cd /home/chiefgyk3d/src/Hammunition && python3 scripts/gen_package_reference.py && python3 scripts/gen_projects_page.py && git status --short
```
Expected: `docs/packages/hammunition-console.md` appears as a new file and `docs/projects.md` is modified (one added row). Nothing else generated changes; if a count-bearing generated page (capability matrix, parity coverage) also reports drift, run its `--check` and regenerate only what `tests/test_docs_generated.py` names.

```bash
python3 scripts/check_doc_links.py && python3 -m pytest tests/test_site.py tests/test_docs_generated.py tests/test_changelog.py tests/test_hammunition_console_unit.py -q
```
Expected: the link checker exits 0; the site builds `--strict`; every generated-docs test passes; the changelog test passes (the fragment is present); the pin test fails only on the draft digest. Fix any real failure (a link, a nav entry); never edit a generated file by hand.

Run the whole suite once, in the background, because a unit count appears in tests: `python3 -m pytest -q -x 2>&1 | tail -5`
Expected: only `test_the_digest_is_a_real_release_digest_not_the_draft_zeros` fails. A failure naming a catalog count (for example 321 manifests) means that number is asserted somewhere: update it where the test names it.

```bash
git add -A && git commit -m "Add the hammunition-console unit and its first-run page (draft: digest pending the v0.1.0 tag)" && git push -u origin console-unit && gh pr create --draft --base main --head console-unit --title "hammunition-console: the catalog unit and its docs page (draft until v0.1.0 is tagged)" --body "Phase A of the console plan's Task 20. The pin test is red on purpose until the digest is filled from the v0.1.0 release. Merged by the maintainer.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```
Expected: a draft PR URL. Rename the fragment: `git mv changelog.d/console-unit.added.md changelog.d/<PR number>.added.md` and push once the PR has a number.

#### Phase B: after `v0.1.0` is tagged on the console repository

- [ ] **Step 6: Produce the pin from the published tag, twice, and compare with the release notes**

```bash
cd /home/chiefgyk3d/src/Hammunition && T=$(mktemp -d) && git ls-remote https://github.com/ChiefGyk3D/hammunition-console 'refs/tags/v0.1.0' 'refs/tags/v0.1.0^{}'
```
Expected: one or two lines; the last is the tag's commit. Record that commit for the manifest comment.

```bash
URL=https://github.com/ChiefGyk3D/hammunition-console/archive/refs/tags/v0.1.0.tar.gz
curl -fsSL "$URL" -o "$T/a.tgz" && curl -fsSL "$URL" -o "$T/b.tgz" && cmp "$T/a.tgz" "$T/b.tgz" && sha256sum "$T/a.tgz" && stat -c %s "$T/a.tgz" && tar -tzf "$T/a.tgz" | head -3
gh release view v0.1.0 --repo ChiefGyk3D/hammunition-console --json body --jq .body | grep -E '^(sha256|bytes):'
```
Expected: `cmp` prints nothing (identical); `sha256sum` prints a 64-hex digest and the size; the archive has exactly one top-level directory (`hammunition-console-0.1.0/`); the release notes' `sha256:` and `bytes:` lines equal what you measured. If they differ, stop: GitHub regenerated the archive or the workflow hashed the wrong file; investigate before pinning.

- [ ] **Step 7: Fill the pin, verify it the engine's way, and finish**

In `catalog/packages/hammunition-console.yaml` replace the zero digest with the measured one, and replace the DRAFT paragraph in the leading comment with a measured record in the style of `catalog/packages/hammunition-tray.yaml`: `Measured <date>: tag v0.1.0 is the annotated tag whose commit is <commit> (git ls-remote); the archive's digest below is what sha256sum printed on two separate downloads and what the engine's fetcher verified on a third; <bytes> bytes, one top-level directory.` Then:

```bash
python3 scripts/check_pin_reviews.py --verify-refs --only hammunition-console
```
Expected: exits 0, reporting the ref resolves upstream (this needs the network; it is also the per-PR CI job for a changed pin).

```bash
python3 -m hammunition install hammunition-console --dry-run 2>&1 | grep -i "sha256\|hammunition-console-0.1.0\|v0.1.0" | head -5 && python3 -m pytest tests/test_hammunition_console_unit.py tests/test_site.py tests/test_docs_generated.py -q
```
Expected: the plan names the v0.1.0 archive and its sha256; the pin test now passes along with the rest.

```bash
python3 scripts/gen_package_reference.py && git add -A && git commit -m "Pin hammunition-console v0.1.0 by its source-archive digest" && git push
```
Then take the PR out of draft (`gh pr ready`) and say in its description what has not run: a real install through the pane on the field laptop is a bench item, recorded in `docs/reference/bench-verification-5430.md` only after it runs. Merging is the maintainer's.

---

## Self-Review

**Spec coverage** (spec section to task):

| Spec | Task |
|---|---|
| 1 purpose, 2 what it is not | Global Constraints; README (Task 19); Help `NEVER` (Task 14) |
| 3.1 process model: reads / writes / own config | Tasks 4 (engine), 7 (pane), 1 (config); README |
| 3.1 channel 3, the helper switches | out of scope with Hardware (header) |
| 3.3 fixed argv, no `shell=True`, reads off the UI thread, errors never retried silently, scripted-consent variable removed from the child, status header shows no value | Tasks 4, 5 (`load`), 7, 6, 16 |
| 4.1 Home | Task 8 |
| 4.2 Install, the stopgap for E1 | Task 10 (E1 fields with unknown fallback; the spec's `update <profile>` stopgap is not built: the plan treats E1 as present, per the maintainer) |
| 4.3 Station | Task 11 |
| 4.4 Hardware, 4.5 Maps | deferred by ruling 12.3 |
| 4.6 Logs | Task 12 |
| 4.7 Update | Task 13 |
| 4.8 Help | Task 14 |
| 5 the install flow (plan first, sections, privacy of `plan`, Run, Result, Interrupt) | Tasks 9, 7 (`runner.py` Ctrl-C), 6 (`hangup`) |
| 6 first-run walkthrough | Task 15 |
| 7 error handling: engine missing/old/unknown schema, exit codes, helper (n/a), no tty, pane death, too small, crash | Tasks 4, 6, 1, 7 |
| 8 packaging: layout, release and pin, dependency floor | Tasks 17, 18, 20 |
| 9 testing: fixtures with schema check, pty test against the fake, the consent test (falsified), no station values, no non-JSON verbs, no sockets, headless widgets (canvas render, no screen stub), CI matrix | Tasks 2, 3, 7, 10, 4 (grep), 16, 18 |
| 10 documentation: README, docs page, generated reference, man page, system modifications, changelog | Tasks 19, 20, 14, 18 |
| 11 engine prerequisites | E1 and E2 treated as present (Global Constraints, fixtures with and without, `docs/contract.md`); E3 to E10 not required |
| 12 rulings | name, urwid, first-release screens honoured; the `hammunition console` subcommand is not in this plan |

Gaps noted and accepted: the spec's "regenerate fixtures by a script" is `scripts/capture_fixtures.py` (Task 2); the "unknown schema major must be refused" fixture is built inline in `tests/test_engine.py` (the engine never prints one, so it cannot be recorded).

**Placeholder scan:** the only deliberate draft value is the all-zero digest in Task 20 Phase A, guarded by a test that fails until Phase B replaces it with a measured one; the commands that produce it are written out. Pin tokens in the workflows are replaced in Task 18 Step 4 by commands that resolve them.

**Type consistency:** `Context.pop(count)` is defined in Task 5 and used by Tasks 6, 9 and 11; `Context.open_screen(name, **kwargs)` by Tasks 6, 8, 15; `Screen.on_show` must end with `redraw()` (stated in Task 6); `PaneScreen.finish` calls `on_exit(code)` and each caller's `on_exit` pops or replaces the pane (Tasks 9, 11, 13, 15); `FakeContext.run_pane` calls `guard.checked_argv`, so every pane argv in every test is checked.

**Review Focus coverage:** (1) control characters: Tasks 5, 8, 9, 10, 12, 13, 14; (2) typed names starting with `-`: Task 10 and Task 11 (region search); (3) corrupt config: Task 1; (4) log path escape and rotation: Task 12; (5) nulls: Tasks 8, 9, 10, 14.
