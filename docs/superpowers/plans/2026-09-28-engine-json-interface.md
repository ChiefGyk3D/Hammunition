# Engine JSON Interface and `hammunition` on the PATH Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every read-only engine command a `--json` form that prints exactly one versioned document on stdout, rendered from the same dataclass the text is rendered from, and make `bootstrap.sh` put `hammunition` on the PATH with `doctor` checking it.

**Architecture:** A new package `src/hammunition/interface/` holds one module per document kind (a frozen dataclass with a `KIND` class variable, its builder, and its text renderer) plus `envelope.py` (the `{"schema","kind","engine"}` envelope, the `--json` plumbing, the error document) and `text.py`. `cli/main.py` gains a global `--json` flag walked onto every subparser, and a JSON path in `main()` that points both standard streams at a recording tee over stderr so only `envelope.emit()` can reach stdout. Each command builds its document once and either emits it or prints the renderer's lines. `scripts/gen_json_reference.py` generates `docs/reference/json-interface.md` from the dataclasses (tables plus the pydantic-derived JSON Schema), and golden fixtures pin every document and every text output.

**Tech Stack:** Python 3.11+, stdlib `dataclasses`/`json`/`argparse`, pydantic 2 `TypeAdapter` (already a dependency) for the published schema and validation, pytest, mypy `--strict`, ruff 0.16.5, bash for the PATH link.

**Spec:** `docs/superpowers/specs/2026-09-28-engine-json-interface-design.md` (approved by the maintainer 2026-09-28). Read it with this plan; where they disagree, the spec wins and this plan is the bug.

## Global Constraints

- Every document carries `{"schema": "hammunition/1", "kind": "<kind>", "engine": "<version>", ...}`.
- "With it, a command prints one JSON document on stdout and nothing else there; diagnostics go to stderr; the exit code is unchanged."
- "`--json` never writes anything but the one document to stdout, including on a refusal (exit code kept, reason in the document)."
- "`schema` versions the whole interface: a field is added freely within a major version; removing or changing a field's meaning bumps it."
- "A real install is never driven through JSON." `install`/`uninstall` accept `--json` only with `--dry-run`.
- "The text output and the JSON come from the same objects." A test asserts, per command, "that every value the text shows is present in the JSON".
- Out of scope: "changing any command's text output" and "a network API of any kind". Every text refactor is proven byte-for-byte against a golden captured from the code before the refactor.
- "`station show --json` and `plan` include the operator's regions and callsign ... The reference says plainly that these documents are for local programs, not for pasting into an issue, and `doctor --json` and `update --json` keep the count-only rule the text output follows."
- `bootstrap.sh` links `~/.local/bin/hammunition` to the checkout's `.venv/bin/hammunition`: "disclosed, idempotent, refusing to replace a file it did not create", and prints the one line to add when `~/.local/bin` is not on the PATH.
- `docs/reference/json-interface.md` is generated from the dataclasses, "never hand-written"; its generator takes `--check` and is in `CHECKED_GENERATORS` in `tests/test_docs_generated.py`.
- Tests are offline: `tests/conftest.py` blocks every non-loopback socket and every `apt-get`/`apt-cache`/`dpkg`/`sudo` call. Mock at the backend, as `tests/test_cli.py::_mock_apt` does.
- `mypy --strict` (no args, the `files` in `pyproject.toml`), `ruff check .` and `ruff format --check .` are CI gates; run all three before every commit.
- SPDX headers: `GPL-3.0-or-later` on every new `.py`/`.sh`, `CC0-1.0` on YAML fixtures; copyright "Renegade Penguin LLC".
- Never write a real callsign, grid square, hostname, serial or location anywhere. Placeholders only: `N0TST`, `N0CALL`, `FN31pr`, `north-america/us/vermont`.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Enable the commit-claims hook once per worktree: `git config core.hooksPath .githooks`.

## Review Focus

- `--json` typed after the verb (`hammunition status --json`) instead of before it: the same document as `hammunition --json status`. Owned by Task 1 (`test_the_flag_works_on_either_side_of_the_verb`) and every per-command test, which put the flag after the verb.
- A `--json` run on a real terminal where the text run would prompt (a station value missing, a suggestion group, `Proceed?`): it must never ask; a front end cannot answer. Owned by Task 1 (`test_a_json_run_never_asks_a_question`) and Task 4 (`test_a_real_install_is_never_driven_through_json`).
- `install --json --yes NAME` without `--dry-run` from a script that assumes `--yes` is enough: refused with exit 2 before resolution, so no gate, sudo prompt or command is reachable. Owned by Task 4.
- Arguments that do not parse, a missing catalog, or an unreadable `/etc/os-release` under `--json`: one `error` document with the text run's exit code, never an empty stdout or a traceback. Owned by Task 1 (argparse, `SystemExit`) and Task 2 (`DetectionError`).
- A `~/.local/bin/hammunition` already there that bootstrap did not make (a pipx install, a hand-written wrapper, a link to another worktree): left byte-for-byte as it is, named, and the switch printed. Owned by Task 8.

## Branches, order and parallel work

Build on `main` (branch `engine-json`, worktree `/home/chiefgyk3d/src/Hammunition-json`). `main` does **not** contain PR #121 (branch `navigation-maps`: `maps regions`, the plan's map-region section, the station map fields, D-057) or PR #119 (branch `device-kept-off`: `kept`/`attached` in `hardware state`).

| Task | What | Depends on | Runs in parallel with |
|---|---|---|---|
| 1 | Envelope, `--json` plumbing, error document, fixture catalog, test helpers, reference generator | main | nothing: everything builds on it |
| 2 | `status --json` | 1 | 3, 4, 5, 6, 7 |
| 3 | `list --json`, `show --json` | 1 | 2, 4, 5, 6, 7 |
| 4 | Plan view; `install`/`uninstall --dry-run --json` | 1 | 2, 3, 5, 6, 7 |
| 5 | `station show --json`, `hardware state --json` | 1 | 2, 3, 4, 6, 7 |
| 6 | `update --json` | 1 | 2, 3, 4, 5, 7 |
| 7 | `doctor --json` | 1 | 2, 3, 4, 5, 6 |
| 8 | `bootstrap.sh` PATH link; `doctor`'s `hammunition` check | 7 | 2 to 6 |
| 9 | After #121 merges: `maps regions --json`, the plan's map section, station map fields | 3, 4, 5, 6, 7 and #121 | 10 |
| 10 | After #119 merges: `hardware state --json` carries real `kept`/`attached` | 5 and #119 | 9 |
| 11 | Docs: D-059, getting-started, `cli.md` verbs, README | 1 to 8 | 9, 10 |

**How the parallel tasks avoid conflicting in `src/hammunition/cli/main.py`.** Each of Tasks 2 to 7 edits only the bodies of its own command functions and adds one `@envelope.json_capable(...)` line directly above its own `def`. They **import inside the function body** (as `cmd_doctor` already does) and never touch the module-level import block, except where a task below says otherwise: Task 4 lets `ruff check --fix` delete the imports its move leaves unused (lines 57-98), and Task 6 adds one line inside the `if TYPE_CHECKING:` block (line 127); those regions are 30 lines apart. Registration is a decorator, not a shared list, and kinds are discovered by walking `hammunition.interface`, not listed, so no task edits a shared registry. Each task writes its own `src/hammunition/interface/<kind>.py`, its own `tests/test_json_<kind>.py` and its own golden files.

**The one shared output.** Every task regenerates `docs/reference/json-interface.md`. When two parallel branches merge, that file conflicts by design: never hand-merge it; take either side and run `.venv/bin/python scripts/gen_json_reference.py`, then commit the result.

**#121 and #119.** Task 4 rewrites `render_plan`, which #121 also edits, and Task 5 rewrites `cmd_hardware_state` and `cmd_station_show`, which #119 and #121 also edit. Whichever lands second resolves the conflict with Task 9 or Task 10, which say exactly how. Task 5's test `test_every_station_field_is_in_the_document` goes red on the first CI run that has both Task 5 and #121: that is intended, it is what forces Task 9.

---

### Task 1: Envelope, `--json` plumbing, error document, reference generator

**Files:**
- Create: `src/hammunition/interface/__init__.py`, `src/hammunition/interface/envelope.py`, `src/hammunition/interface/text.py`
- Create: `scripts/gen_json_reference.py`, `docs/reference/json-interface.md` (generated)
- Create: `tests/json_support.py`, `tests/test_json_interface.py`
- Create: `tests/fixtures/json/catalog/packages/fixture-apt.yaml`, `tests/fixtures/json/catalog/packages/fixture-source.yaml`, `tests/fixtures/json/catalog/profiles/fixture-station.yaml`, `tests/fixtures/json/catalog/profiles/fixture-gated.yaml`
- Modify: `src/hammunition/cli/main.py` (imports at 31-130, `_wrap` at 1594-1607, `_engine_version` at 2370-2375, end of `build_parser` at 2584-2586, `main` at 2589-2624)
- Modify: `tests/test_docs_generated.py:622-676` (`CHECKED_GENERATORS`), `docs/reference/cli.md:40-43` (Global flags), `pyproject.toml` (`[tool.ruff.lint]`), `REUSE.toml`

**Interfaces:**
- Consumes: `hammunition.distro.Target` (`distro`, `version`, `arch`, `id_like`, `pretty_name`, `describe()`, `is_debian_family`).
- Produces, in `hammunition.interface.envelope`:
  - `SCHEMA: str = "hammunition/1"`
  - `class Strict` — base of every document dataclass (pydantic `extra="forbid"`).
  - `described(doc: str) -> Any` — a dataclass field carrying `metadata={"doc": doc}`; every document field uses it.
  - `engine_version() -> str`
  - `@dataclass(frozen=True) class TargetView(Strict)` with `distro, version, arch, id_like: tuple[str, ...], pretty_name: str | None, description: str, debian_family: bool`; `target_view(target: Target) -> TargetView`
  - `@dataclass(frozen=True) class ErrorDocument(Strict)`, `KIND = "error"`, fields `command: str, exit_code: int, message: str`
  - `document(result: object) -> dict[str, Any]`, `dumps(result: object) -> str`
  - `class Tee(io.TextIOBase)` with `.text() -> str`; `isatty()` is always False
  - `begin(stream: TextIO) -> None`, `end() -> None`, `emit(result: object) -> None`, `emitted() -> bool`, `wanted(args: argparse.Namespace) -> bool`
  - `json_capable(*, dry_run_only: bool = False) -> Callable[[CommandFunc], CommandFunc]` — the decorator Tasks 2 to 7 put on their command
  - `command_name(args) -> str`, `refusal(args) -> str | None`, `kinds() -> dict[str, type]`
- Produces, in `hammunition.interface.text`: `wrap(text: str, *, indent: str, width: int = 88) -> list[str]` (moved from `cli/main.py::_wrap`, which becomes an import alias).
- Produces, in `tests/json_support.py`: `FIXTURE_CATALOG: Path`, `parse_one(stdout: str) -> dict[str, Any]`, `validate(doc) -> None`, `assert_golden(name, doc, replacements=None) -> None`, `assert_golden_text(name, text) -> None`, `assert_text_values_in_json(text, doc, *renderers) -> None`, `UPDATE_ENV = "HAMMUNITION_UPDATE_GOLDEN"`.
- Produces: the fixture catalog every later golden runs against (units `fixture-apt`, `fixture-source`; profiles `fixture-station`, `fixture-gated`).

- [ ] **Step 1: Write the fixture catalog**

`tests/fixtures/json/catalog/packages/fixture-apt.yaml`:

````yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0
#
# Test fixture for the --json golden documents (D-059). Not part of the catalog.

name: fixture-apt
version: "1.0"
summary: A fixture unit installed with apt — em dash kept on purpose
categories: [digital-modes]
install:
  - install:
      method: apt
      packages: [fixture-apt]
update:
  probe:
    method: apt_policy
documentation:
  what_it_does: Stands in for an apt unit in the JSON interface tests.
  why_you_want_it: The golden documents need a catalog that never changes under them.
  upstream_url: https://example.invalid/fixture-apt
````

`tests/fixtures/json/catalog/packages/fixture-source.yaml`:

````yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0
#
# Test fixture for the --json golden documents (D-059). Not part of the catalog.

name: fixture-source
version: "2.1"
summary: A fixture unit built from a pinned tarball
categories: [digital-modes]
install:
  - install:
      method: source
      source:
        url: https://example.invalid/fixture-source-2.1.tar.gz
        sha256: 30cf6db1a2b495975a499b45f3e760758579b81c99157b2d52d699f0c46ff9a4
      build_system: autotools
    build_depends: [build-essential]
update:
  probe:
    method: none
  strategy: rebuild
documentation:
  what_it_does: Stands in for a source build in the JSON interface tests.
  why_you_want_it: The golden documents need a built unit with a pin to report.
  upstream_url: https://example.invalid/fixture-source
````

`tests/fixtures/json/catalog/profiles/fixture-station.yaml`:

````yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0
#
# Test fixture for the --json golden documents (D-059). Not part of the catalog.

name: fixture-station
summary: Both fixture units, as a profile
packages: [fixture-apt, fixture-source]
documentation:
  what_it_installs: The two fixture units, one from apt and one built from source.
  why_together: One of each install method the golden documents need to show.
  deliberately_excludes: Everything real.
  manual_configuration: Nothing; it is a fixture.
````

`tests/fixtures/json/catalog/profiles/fixture-gated.yaml`:

````yaml
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0
#
# Test fixture for the --json golden documents (D-059). Not part of the catalog.

name: fixture-gated
summary: A consent-gated fixture profile
stage: post-1.0
consent:
  env_var: HAMMUNITION_ACCEPT_FIXTURE_GATED
  risk_categories: [identifier_collection]
  disclosure: >-
    This fixture profile stands in for software that can receive and store
    identifiers belonging to people and their devices.
  affirmation: >-
    Do you affirm that you have the authorization you need for this fixture?
packages: [fixture-apt]
documentation:
  what_it_installs: The apt fixture unit, behind a consent gate.
  why_together: A gated profile is the shape `show --json` must carry a disclosure for.
  deliberately_excludes: Everything real.
  manual_configuration: Nothing; it is a fixture.
````

Add the golden files' licence to `REUSE.toml` (JSON and plain text cannot carry an SPDX comment), after the `.github/**` annotation:

````toml
[[annotations]]
path = "tests/fixtures/**"
precedence = "aggregate"
SPDX-FileCopyrightText = "Copyright (C) 2026 Renegade Penguin LLC"
SPDX-License-Identifier = "GPL-3.0-or-later"
````

- [ ] **Step 2: Write the shared test helpers**

`tests/json_support.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared checks for the ``--json`` interface tests.  D-059.

Golden files live in ``tests/fixtures/json/``. A change to a document is a
deliberate diff: run the failing test once with ``HAMMUNITION_UPDATE_GOLDEN=1``,
read the diff to the golden file, and commit it with the change that caused it.
"""

from __future__ import annotations

import inspect
import json
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from hammunition.interface.envelope import SCHEMA, kinds

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
GOLDEN = HERE / "fixtures" / "json"
FIXTURE_CATALOG = GOLDEN / "catalog"
UPDATE_ENV = "HAMMUNITION_UPDATE_GOLDEN"

#: A value as the text shows it: two or more word characters, dots, slashes,
#: at-signs, pluses, tildes or hyphens. A single character (a one-digit count)
#: is too common to attribute and is not checked.
TOKEN = re.compile(r"[\w./@+~-]{2,}")


def parse_one(stdout: str) -> dict[str, Any]:
    """The whole of stdout as exactly one JSON object, envelope checked."""
    doc = json.loads(stdout)
    assert isinstance(doc, dict), f"stdout is a {type(doc).__name__}, not one document"
    assert doc.get("schema") == SCHEMA, doc.get("schema")
    assert isinstance(doc.get("kind"), str) and isinstance(doc.get("engine"), str)
    return doc


def validate(doc: Mapping[str, Any]) -> None:
    """*doc* validates against the published schema of its kind."""
    body = {k: v for k, v in doc.items() if k not in ("schema", "kind", "engine")}
    cls = kinds()[str(doc["kind"])]
    TypeAdapter(cls).validate_python(body)


def _normalise(doc: Mapping[str, Any], replacements: Mapping[str, str]) -> Any:
    text = json.dumps(doc, ensure_ascii=False)
    for real, placeholder in replacements.items():
        text = text.replace(json.dumps(real, ensure_ascii=False)[1:-1], placeholder)
    loaded = json.loads(text)
    loaded["engine"] = "<engine>"
    return loaded


def assert_golden(
    name: str, doc: Mapping[str, Any], replacements: Mapping[str, str] | None = None
) -> None:
    """*doc* equals ``tests/fixtures/json/<name>.json``, engine version and
    machine paths replaced by placeholders so the file is the same everywhere."""
    rendered = json.dumps(_normalise(doc, replacements or {}), ensure_ascii=False, indent=2) + "\n"
    _compare(GOLDEN / f"{name}.json", rendered)


def assert_golden_text(name: str, text: str) -> None:
    """*text* equals ``tests/fixtures/json/<name>.txt`` byte for byte."""
    _compare(GOLDEN / f"{name}.txt", text)


def _compare(path: Path, rendered: str) -> None:
    if os.environ.get(UPDATE_ENV) == "1":
        path.write_text(rendered)
        return
    assert path.exists(), (
        f"no golden file {path.relative_to(REPO_ROOT)}: run this test once with "
        f"{UPDATE_ENV}=1, review the file, and commit it"
    )
    expected = path.read_text()
    assert rendered == expected, (
        f"{path.relative_to(REPO_ROOT)} differs from what the engine now prints. If the "
        f"change is intended, re-run with {UPDATE_ENV}=1 and commit the diff."
    )


def assert_text_values_in_json(
    text: str, doc: Mapping[str, Any], *renderers: Callable[..., object]
) -> None:
    """Every value the text shows is carried by the JSON.

    A token of *text* is chrome when it occurs in the source of one of the
    *renderers* (a label, a fixed sentence) and a value otherwise; every value
    must occur somewhere in the serialised document.
    """
    chrome = "\n".join(inspect.getsource(r) for r in renderers)
    flat = json.dumps(doc, ensure_ascii=False)
    missing = sorted({t for t in TOKEN.findall(text) if t not in chrome and t not in flat})
    assert not missing, (
        f"the text shows {len(missing)} value(s) the JSON does not carry: {missing[:12]}"
    )
````

- [ ] **Step 3: Write the failing plumbing tests**

`tests/test_json_interface.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``--json`` plumbing every command shares.  D-059.

One document on stdout and nothing else there, diagnostics on stderr, the
exit code the text run would return -- on every path, including a refusal
before anything was resolved. The per-command documents are tested beside
their commands; this file tests the envelope, the flag, and the helpers
those tests lean on.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from hammunition.interface import envelope
from hammunition.interface.envelope import SCHEMA, ErrorDocument, Strict, described
from json_support import assert_text_values_in_json, parse_one, validate

# The module, not the `main` function `hammunition.cli` re-exports.
cli = importlib.import_module("hammunition.cli.main")


@dataclass(frozen=True)
class _Probe(Strict):
    """A document only this test emits."""

    KIND: ClassVar[str] = "probe"
    value: str = described("what the probe command was given")


def _install_probe(monkeypatch: pytest.MonkeyPatch, body: Any) -> None:
    """Make `status` a JSON-capable probe running *body*, for plumbing tests
    that must not depend on any real command's document."""

    @envelope.json_capable()
    def probe(args: argparse.Namespace) -> int:
        result: int = body(args)
        return result

    monkeypatch.setattr(cli, "cmd_status", probe)


def test_the_flag_works_on_either_side_of_the_verb(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def body(args: argparse.Namespace) -> int:
        envelope.emit(_Probe(value="N0TST"))
        return 0

    _install_probe(monkeypatch, body)
    for argv in (["--json", "status"], ["status", "--json"]):
        assert cli.main(argv) == 0
        doc = parse_one(capsys.readouterr().out)
        assert doc == {"schema": SCHEMA, "kind": "probe", "engine": doc["engine"], "value": "N0TST"}


def test_without_the_flag_nothing_changes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[bool] = []

    def body(args: argparse.Namespace) -> int:
        seen.append(envelope.wanted(args))
        print("text as before")
        return 0

    _install_probe(monkeypatch, body)
    assert cli.main(["status"]) == 0
    assert seen == [False]
    assert capsys.readouterr().out == "text as before\n"


def test_anything_a_command_prints_goes_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def body(args: argparse.Namespace) -> int:
        print("note: a stray line of text")
        envelope.emit(_Probe(value="x"))
        return 0

    _install_probe(monkeypatch, body)
    assert cli.main(["status", "--json"]) == 0
    captured = capsys.readouterr()
    parse_one(captured.out)
    assert "note: a stray line of text" in captured.err


def test_a_json_run_never_asks_a_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review focus: on a real terminal a prompt under --json would put a
    question in front of a front end that cannot answer it."""
    from hammunition import station

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    answers: list[bool] = []

    def body(args: argparse.Namespace) -> int:
        answers.append(station.is_interactive())
        envelope.emit(_Probe(value="x"))
        return 0

    _install_probe(monkeypatch, body)
    assert cli.main(["status", "--json"]) == 0
    assert answers == [False]
    parse_one(capsys.readouterr().out)


def test_a_command_that_ends_without_a_document_gets_an_error_document(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def body(args: argparse.Namespace) -> int:
        print("error: the target could not be read", file=sys.stderr)
        return 1

    _install_probe(monkeypatch, body)
    assert cli.main(["status", "--json"]) == 1
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error"
    assert doc["exit_code"] == 1
    assert doc["command"] == "status"
    assert "the target could not be read" in doc["message"]
    validate(doc)


def test_a_catalog_that_cannot_be_found_is_a_document_with_exit_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """find_catalog raises SystemExit(str); the interpreter would print it and
    exit 1, and under --json that becomes the document's message."""

    def body(args: argparse.Namespace) -> int:
        raise SystemExit("could not find the catalog")

    _install_probe(monkeypatch, body)
    assert cli.main(["status", "--json"]) == 1
    captured = capsys.readouterr()
    doc = parse_one(captured.out)
    assert doc["kind"] == "error" and doc["exit_code"] == 1
    assert "could not find the catalog" in doc["message"]
    assert "could not find the catalog" in captured.err


def test_arguments_that_do_not_parse_are_a_document_with_argparses_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--json", "list", "nonsense"]) == 2
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error" and doc["exit_code"] == 2 and doc["command"] == ""
    assert "invalid choice" in doc["message"]


def test_a_command_with_no_json_form_is_refused_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """`station set` writes a file; under --json it must refuse before that."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    rc = cli.main(["station", "set", "--callsign", "N0TST", "--json"])
    assert rc == cli.EXIT_UNPLANNABLE
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error" and doc["command"] == "station set"
    assert "no --json form" in doc["message"]
    assert not any(tmp_path.rglob("station.yml")), "a refused --json run wrote the station file"


def test_help_under_json_prints_no_document(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--json", "--help"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err


def test_every_subcommand_accepts_the_flag() -> None:
    """Walked, not listed: a verb added later must carry --json without
    anyone remembering to add it."""
    parser = cli.build_parser()

    def leaves(p: argparse.ArgumentParser, path: list[str]) -> list[tuple[list[str], Any]]:
        subs = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            return [(path, p)]
        return [
            leaf for name, child in subs[0].choices.items() for leaf in leaves(child, [*path, name])
        ]

    for path, leaf in leaves(parser, []):
        options = {o for a in leaf._actions for o in a.option_strings}
        assert "--json" in options, f"`hammunition {' '.join(path)}` does not accept --json"


def test_a_second_document_is_a_bug_not_a_second_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def body(args: argparse.Namespace) -> int:
        envelope.emit(_Probe(value="one"))
        envelope.emit(_Probe(value="two"))
        return 0

    _install_probe(monkeypatch, body)
    with pytest.raises(RuntimeError, match="exactly one document"):
        cli.main(["status", "--json"])


def test_non_ascii_is_written_as_utf8_not_escaped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The text is full of em dashes and arrows; a front end reads them as-is."""

    def body(args: argparse.Namespace) -> int:
        envelope.emit(_Probe(value="not parkable right now — unplugged → wake"))
        return 0

    _install_probe(monkeypatch, body)
    cli.main(["status", "--json"])
    out = capsys.readouterr().out
    assert "—" in out and "\\u2014" not in out
    assert parse_one(out)["value"] == "not parkable right now — unplugged → wake"


def test_every_kind_has_a_docstring_and_every_field_a_description() -> None:
    kinds = envelope.kinds()
    assert "error" in kinds, "kind discovery found nothing; the checks below would pass empty"
    for kind, cls in kinds.items():
        for c in (cls, *_nested(cls)):
            assert c.__doc__ and not c.__doc__.startswith(f"{c.__name__}("), (
                f"{c.__name__} ({kind}) has no docstring; the reference page prints it"
            )
            for f in dataclasses.fields(c):
                assert f.metadata.get("doc"), f"{c.__name__}.{f.name} has no described() text"


def _nested(cls: type) -> list[type]:
    import typing

    found: list[type] = []

    def walk(tp: object) -> None:
        for arg in typing.get_args(tp):
            walk(arg)
        if isinstance(tp, type) and dataclasses.is_dataclass(tp) and tp not in found:
            found.append(tp)
            for hint in typing.get_type_hints(tp).values():
                walk(hint)

    for hint in typing.get_type_hints(cls).values():
        walk(hint)
    return found


def test_the_error_document_validates_and_rejects_an_unknown_field() -> None:
    body = dataclasses.asdict(ErrorDocument(command="status", exit_code=1, message="m"))
    validate({"schema": SCHEMA, "kind": "error", "engine": "x", **body})
    with pytest.raises(ValidationError, match="surprise"):
        validate({"schema": SCHEMA, "kind": "error", "engine": "x", **body, "surprise": 1})


def _chrome() -> None:
    print("Target:")


def test_the_parity_check_goes_red_when_the_json_drops_a_value() -> None:
    """Falsified first (CLAUDE.md): a value in the text and not in the JSON fails."""
    text = "Target: Parrot-7.3 N0TST"
    assert_text_values_in_json(text, {"target": "Parrot-7.3", "call": "N0TST"}, _chrome)
    with pytest.raises(AssertionError, match="N0TST"):
        assert_text_values_in_json(text, {"target": "Parrot-7.3"}, _chrome)


def test_document_refuses_a_class_without_a_kind() -> None:
    @dataclass(frozen=True)
    class NoKind:
        value: int

    with pytest.raises(TypeError, match="not a document kind"):
        envelope.document(NoKind(1))
    assert json.loads(envelope.dumps(_Probe(value="v")))["kind"] == "probe"
````

- [ ] **Step 4: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_json_interface.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'hammunition.interface'`.

- [ ] **Step 5: Write the interface package**

`src/hammunition/interface/__init__.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The engine's machine-readable interface.  D-059.

One module per document kind. Each defines a frozen dataclass with a ``KIND``
class variable, and :func:`hammunition.interface.envelope.kinds` finds them by
walking this package, so adding a kind edits no shared registry. The text a
command prints and the JSON it emits under ``--json`` are rendered from the
same dataclass instance, which is what keeps the two from drifting.
"""
````

`src/hammunition/interface/text.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Text helpers shared by the command renderers."""

from __future__ import annotations

import textwrap

__all__ = ["wrap"]


def wrap(text: str, *, indent: str, width: int = 88) -> list[str]:
    """Wrap manifest prose to a readable width.

    The `detail` on a system modification is a paragraph — it has to be, since
    it is the operator's only account of what a group membership actually
    grants — and printing it as one 400-column line is how a disclosure becomes
    something nobody reads.
    """
    return textwrap.wrap(
        " ".join(text.split()),
        width=width,
        initial_indent=indent,
        subsequent_indent=indent,
    )
````

`src/hammunition/interface/envelope.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The envelope every ``--json`` document shares, and the plumbing that
guarantees one document on stdout.  D-059.

Every document is ``{"schema": "hammunition/1", "kind": ..., "engine": ...}``
followed by the fields of one dataclass. ``schema`` versions the whole
interface: a field may be added within a major version; removing one or
changing what it means bumps the major, and a front end refuses a major it
does not know, by name.

Under ``--json`` both ``sys.stdout`` and ``sys.stderr`` point at a
:class:`Tee` over the real stderr, so anything a command prints -- a note, a
warning, a stray line of its text form -- is a diagnostic on stderr, never a
second thing on stdout. The one document goes to the real stdout through
:func:`emit`. A command that ends without emitting one (it refused before
anything was resolved, or the catalog would not load) gets an
:class:`ErrorDocument` carrying its exit code and everything it wrote to
stderr, so stdout parses as exactly one document on every path.
"""

from __future__ import annotations

import argparse
import importlib
import io
import json
import pkgutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from importlib import metadata
from typing import Any, ClassVar, TextIO

from pydantic import ConfigDict

from hammunition.distro import Target

__all__ = [
    "SCHEMA",
    "ErrorDocument",
    "Strict",
    "TargetView",
    "Tee",
    "begin",
    "command_name",
    "described",
    "document",
    "dumps",
    "emit",
    "emitted",
    "end",
    "engine_version",
    "json_capable",
    "kinds",
    "refusal",
    "target_view",
    "wanted",
]

SCHEMA = "hammunition/1"

CommandFunc = Callable[[argparse.Namespace], int]


class Strict:
    """Base of every document dataclass. The published schema forbids a field
    it does not name, so a validator catches a document that grew one."""

    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


def described(doc: str) -> Any:
    """A dataclass field carrying its description for the reference page."""
    return field(metadata={"doc": doc})


def engine_version() -> str:
    """The installed package version, or a marker when running uninstalled."""
    try:
        return metadata.version("hammunition")
    except metadata.PackageNotFoundError:
        return "0+uninstalled"


@dataclass(frozen=True)
class TargetView(Strict):
    """What `/etc/os-release` said, verbatim, with the one line the text prints."""

    distro: str = described("`ID` from /etc/os-release")
    version: str = described("`VERSION_ID`; empty when the file declares none")
    arch: str = described("the machine architecture install blocks are selected by")
    id_like: tuple[str, ...] = described("`ID_LIKE`, split on whitespace")
    pretty_name: str | None = described("`PRETTY_NAME`, when declared")
    description: str = described("exactly what the text prints after `Target:`")
    debian_family: bool = described("whether the engine will install on this system")


def target_view(target: Target) -> TargetView:
    return TargetView(
        distro=target.distro,
        version=target.version,
        arch=target.arch,
        id_like=tuple(target.id_like),
        pretty_name=target.pretty_name,
        description=target.describe(),
        debian_family=target.is_debian_family,
    )


@dataclass(frozen=True)
class ErrorDocument(Strict):
    """Printed when a command ends without a document of its own: its
    arguments did not parse, it has no JSON form, a real install was asked
    for under `--json`, or it refused before resolving anything (no catalog,
    an unreadable target). The exit code is the one the text run returns."""

    KIND: ClassVar[str] = "error"

    command: str = described(
        "the verb, e.g. `status` or `hardware state`; empty when the arguments did not parse"
    )
    exit_code: int = described("the process exit code; the table is in docs/reference/cli.md")
    message: str = described("everything the command wrote to stderr, which is where the reason is")


def document(result: object) -> dict[str, Any]:
    """The envelope plus the fields of *result*, a document dataclass."""
    kind = getattr(type(result), "KIND", None)
    if not isinstance(kind, str) or not is_dataclass(result) or isinstance(result, type):
        raise TypeError(f"{type(result).__name__} is not a document kind")
    return {"schema": SCHEMA, "kind": kind, "engine": engine_version(), **asdict(result)}


def dumps(result: object) -> str:
    """One document as the interface prints it: UTF-8, never ASCII-escaped."""
    return json.dumps(document(result), indent=2, ensure_ascii=False)


class Tee(io.TextIOBase):
    """The real stderr, recorded. Under ``--json`` stdout points here too."""

    def __init__(self, stream: TextIO) -> None:
        super().__init__()
        self._stream = stream
        self._parts: list[str] = []

    def write(self, text: str) -> int:
        self._parts.append(text)
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        # A --json run never asks a question: `station.is_interactive()` and
        # every prompt read `sys.stdout.isatty()`, and this answers no even
        # when the stderr underneath is a terminal.
        return False

    def text(self) -> str:
        return "".join(self._parts)


class _Sink:
    stream: TextIO | None = None
    emitted: bool = False


_SINK = _Sink()


def begin(stream: TextIO) -> None:
    """Start a ``--json`` run whose one document goes to *stream*."""
    _SINK.stream = stream
    _SINK.emitted = False


def end() -> None:
    _SINK.stream = None
    _SINK.emitted = False


def emitted() -> bool:
    return _SINK.emitted


def emit(result: object) -> None:
    """Write the run's one document. A second call is a bug, and raises."""
    if _SINK.stream is None:
        raise RuntimeError("emit() outside a --json run")
    if _SINK.emitted:
        raise RuntimeError("a --json run prints exactly one document")
    _SINK.stream.write(dumps(result) + "\n")
    _SINK.stream.flush()
    _SINK.emitted = True


def wanted(args: argparse.Namespace) -> bool:
    """Whether this run was asked for JSON."""
    return bool(getattr(args, "json", False))


_CAPABLE: dict[CommandFunc, bool] = {}


def json_capable(*, dry_run_only: bool = False) -> Callable[[CommandFunc], CommandFunc]:
    """Mark a command function as having a ``--json`` form.

    ``dry_run_only`` is for ``install`` and ``uninstall``: their JSON is the
    plan, and a real run is never driven through JSON (D-059, D-021).
    """

    def mark(func: CommandFunc) -> CommandFunc:
        _CAPABLE[func] = dry_run_only
        return func

    return mark


def command_name(args: argparse.Namespace) -> str:
    """``status``, ``hardware state``: the verb as the operator typed it."""
    verb = str(getattr(args, "command", None) or "")
    sub = getattr(args, f"{verb}_command", None) if verb else None
    return f"{verb} {sub}" if sub else verb


def refusal(args: argparse.Namespace) -> str | None:
    """Why this ``--json`` run must not start, or None when it may."""
    func = getattr(args, "func", None)
    if func is None:
        return "name a command; `hammunition --help` lists them"
    if func not in _CAPABLE:
        return (
            f"`hammunition {command_name(args)}` has no --json form. The commands "
            f"that have one, and their documents, are in docs/reference/json-interface.md."
        )
    if _CAPABLE[func] and not getattr(args, "dry_run", False):
        return (
            f"a real {command_name(args)} is never driven through --json (D-059). Run "
            f"it in a terminal, where sudo, every consent gate and every disclosure "
            f"are the CLI's own; --json is for --dry-run, and `status --json` reads "
            f"the result afterwards."
        )
    return None


def kinds() -> dict[str, type]:
    """Every document class in :mod:`hammunition.interface`, by kind."""
    import hammunition.interface as package

    found: dict[str, type] = {}
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda i: i.name):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        for value in vars(module).values():
            if not isinstance(value, type) or value.__module__ != module.__name__:
                continue
            kind = vars(value).get("KIND")
            if not isinstance(kind, str):
                continue
            if kind in found and found[kind] is not value:
                raise RuntimeError(f"two document classes claim kind {kind!r}")
            found[kind] = value
    return dict(sorted(found.items()))
````

Tell ruff that `described()` is a field call (RUF009 otherwise flags every nullable field). In `pyproject.toml`, directly above `[tool.ruff.lint.per-file-ignores]`:

````toml
# `described()` is `dataclasses.field(metadata=...)` under a name (D-059); tell
# RUF009 so, rather than silencing it per line.
[tool.ruff.lint.flake8-bugbear]
extend-immutable-calls = ["hammunition.interface.envelope.described"]
````

- [ ] **Step 6: Wire `--json` into the CLI**

In `src/hammunition/cli/main.py`:

1. Imports: delete `from importlib import metadata`; change `from typing import TYPE_CHECKING` to `from typing import TYPE_CHECKING, TextIO, cast`; after `from hammunition.hardware.polkit import HELPER_PATH, POLICY_PATH, describe_refusal` add:

````python
from hammunition.interface import envelope
from hammunition.interface.text import wrap as _wrap
````

2. Delete the whole `def _wrap(...)` function (lines 1594-1607); the import above replaces it, so `render_plan` keeps calling `_wrap` unchanged.

3. Replace `_engine_version` (lines 2370-2375) with these two functions:

````python
def _engine_version() -> str:
    """The installed package version, or a marker when running uninstalled."""
    return envelope.engine_version()


def _add_json_flag(parser: argparse.ArgumentParser, *, top: bool) -> None:
    """``--json`` on the top-level parser and on every subcommand, recursively.

    Accepted on both sides of the verb, ``hammunition --json status`` and
    ``hammunition status --json``. A subcommand's copy defaults to SUPPRESS,
    so an absent flag after the verb does not overwrite one given before it.
    Walked rather than listed, so a verb added later carries it without
    anyone remembering to (D-059).
    """
    parser.add_argument(
        "--json",
        action="store_true",
        default=False if top else argparse.SUPPRESS,
        help="print one JSON document on stdout instead of text (docs/reference/json-interface.md)",
    )
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                _add_json_flag(child, top=False)
````

4. At the end of `build_parser`, replace `    return parser` with:

````python
    _add_json_flag(parser, top=True)
    return parser
````

5. Replace `main` (lines 2589-2624) with:

````python
def _dispatch(args: argparse.Namespace) -> int:
    """Run the chosen command, turning operator-input errors into exit codes."""
    try:
        result: int = args.func(args)
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    except StationError as exc:
        # A bad --callsign is operator input, not an engine fault: it gets the
        # validator's message and the planning exit code, never a traceback.
        # Found on the first Parrot VM run that passed one.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing further was run.", file=sys.stderr)
        return EXIT_FAILED
    return result


def _exit_code(exc: SystemExit) -> int:
    """The status the interpreter would exit with for *exc*."""
    if exc.code is None:
        return EXIT_OK
    if isinstance(exc.code, int):
        return exc.code
    return EXIT_FAILED  # SystemExit("message") prints it and exits 1


def _main_json(arguments: list[str]) -> int:
    """``--json``: exactly one document on stdout, on every path.  D-059.

    Both standard streams point at a recording tee over the real stderr
    while the command runs, so nothing it prints can reach stdout; the
    document goes to the real stdout through :func:`envelope.emit`. A run
    that ends without one gets an error document with the same exit code.
    """
    real_stdout, real_stderr = sys.stdout, sys.stderr
    tee = envelope.Tee(real_stderr)
    sys.stdout = sys.stderr = cast(TextIO, tee)
    envelope.begin(real_stdout)
    try:
        try:
            args = build_parser().parse_args(arguments)
        except SystemExit as exc:
            code = _exit_code(exc)
            if code == EXIT_OK:
                return EXIT_OK  # --help or --version: printed to stderr, not a document
            envelope.emit(
                envelope.ErrorDocument(command="", exit_code=code, message=tee.text().strip())
            )
            return code
        command = envelope.command_name(args)
        why = envelope.refusal(args)
        if why is not None:
            print(f"error: {why}", file=sys.stderr)
            envelope.emit(
                envelope.ErrorDocument(
                    command=command, exit_code=EXIT_UNPLANNABLE, message=tee.text().strip()
                )
            )
            return EXIT_UNPLANNABLE
        try:
            code = _dispatch(args)
        except SystemExit as exc:
            code = _exit_code(exc)
            if isinstance(exc.code, str):
                print(exc.code, file=sys.stderr)
        if not envelope.emitted():
            envelope.emit(
                envelope.ErrorDocument(command=command, exit_code=code, message=tee.text().strip())
            )
        return code
    finally:
        envelope.end()
        sys.stdout, sys.stderr = real_stdout, real_stderr


def main(argv: Sequence[str] | None = None) -> int:
    # Line-buffer stdout even when it is not a terminal. A whole-profile
    # install redirected to a file showed 0 bytes for the forty minutes it
    # ran (Kali VM, 2026-09-02): Python block-buffers a pipe, so every `$
    # command` header sat in memory while the child processes, which write
    # to the same descriptor directly, streamed past it -- a log that is
    # empty until exit, and then out of order. An install that is killed
    # mid-way loses the whole record. Line buffering costs nothing an
    # installer notices.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(line_buffering=True)
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--json" in arguments:
        return _main_json(arguments)
    parser = build_parser()
    args = parser.parse_args(arguments)
    if not getattr(args, "func", None):
        # Bare `hammunition`: print the top-level help and exit cleanly, which
        # is friendlier than argparse's "command is required" error for someone
        # running it for the first time. (Group verbs keep required sub-verbs,
        # so `hammunition hardware` still gets argparse's standard message.)
        parser.print_help()
        return EXIT_OK
    return _dispatch(args)
````

- [ ] **Step 7: Run the plumbing tests**

Run: `.venv/bin/pytest tests/test_json_interface.py -q`
Expected: `16 passed`.

- [ ] **Step 8: Falsify the parity helper before trusting it**

Temporarily change `assert not missing` in `tests/json_support.py::assert_text_values_in_json` to `assert True`, run `.venv/bin/pytest tests/test_json_interface.py -q -k parity_check`, and confirm `test_the_parity_check_goes_red_when_the_json_drops_a_value` FAILS with `DID NOT RAISE`. Restore the line and rerun: PASS.

- [ ] **Step 9: Write the reference generator**

`scripts/gen_json_reference.py` (then `chmod +x scripts/gen_json_reference.py`):

~~~~python
#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/json-interface.md from the document dataclasses.

The documents ``--json`` prints are the published interface front ends are
written against (D-059). A hand-written page describing them would drift the
first time a field was added, so this walks every document class under
``src/hammunition/interface/`` -- found by their ``KIND`` class variable, not
listed -- and renders each one's docstring, a table of its fields with the
text their ``described()`` call carries, and the JSON Schema pydantic derives
from the same class. The tests validate every golden document against that
schema.

Usage:
    scripts/gen_json_reference.py            # regenerate
    scripts/gen_json_reference.py --check    # fail if out of date
"""

from __future__ import annotations

import argparse
import dataclasses
import inspect
import json
import sys
import types
import typing
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from pydantic import TypeAdapter  # noqa: E402

from hammunition.interface.envelope import SCHEMA, kinds  # noqa: E402

OUT = REPO_ROOT / "docs" / "reference" / "json-interface.md"
HEADER = "<!-- Generated by scripts/gen_json_reference.py. Do not edit by hand -->"

INTRO = f"""
Every command in the table below takes `--json`, before or after the verb:
`hammunition --json status` and `hammunition status --json` are the same run.
With it, the command prints **one JSON document on stdout and nothing else
there**. Everything else it would have printed -- notes, warnings, the reason
for a refusal -- goes to stderr. The exit code is the one the text run returns
(the table is in `docs/reference/cli.md`), and a run that refuses still prints
a document: its own kind when it got far enough to have one (a refused plan is
a `plan` with `outcome: "refused"`), otherwise an `error` document carrying
the exit code and everything written to stderr.

Every document starts with the same three fields:

```json
{{"schema": "{SCHEMA}", "kind": "<kind>", "engine": "<version>"}}
```

`schema` versions the whole interface. A field may be added within a major
version; removing a field or changing what one means bumps the major, and a
front end refuses a major it does not know, by name. `engine` is the installed
engine's version.

**A real install is never driven through JSON.** `install --json` and
`uninstall --json` require `--dry-run`: their document is the plan. A front
end runs the real command in the operator's own terminal, where sudo, every
consent gate (D-021) and every disclosure are the CLI's, then reads
`status --json` again. A command with no JSON form refuses `--json` with an
`error` document and runs nothing.

**These documents are for local programs, not for pasting.** `station` carries
the callsign, grid square and every other station value, because a local front
end needs them to fill a form. Do not paste one into an issue, a forum or a
chat: a callsign resolves to a name and a licence address. `doctor` and
`update` keep the count-only rule their text follows.

`--help` and `--version` under `--json` print to stderr and emit no document.
"""


def _type_name(annotation: object) -> str:
    if annotation is type(None):
        return "null"
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        return " or ".join(_type_name(a) for a in args)
    if origin is tuple:
        return f"list of {_type_name(args[0])}"
    if origin is dict:
        return "object"
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return f"[`{annotation.__name__}`](#{annotation.__name__.lower()})"
    if annotation is str:
        return "string"
    if annotation is int:
        return "integer"
    if annotation is bool:
        return "boolean"
    return str(annotation)


def _nested(cls: type) -> list[type]:
    """Dataclasses reachable from *cls*, depth first, in field order, once each."""
    found: list[type] = []

    def walk(tp: object) -> None:
        for arg in typing.get_args(tp):
            walk(arg)
        if isinstance(tp, type) and dataclasses.is_dataclass(tp) and tp not in found:
            found.append(tp)
            for hint in typing.get_type_hints(tp).values():
                walk(hint)

    for hint in typing.get_type_hints(cls).values():
        walk(hint)
    return found


def _table(cls: type) -> list[str]:
    hints = typing.get_type_hints(cls)
    lines = ["| field | type | meaning |", "|---|---|---|"]
    for f in dataclasses.fields(cls):
        doc = str(f.metadata.get("doc", "")).replace("|", "\\|")
        lines.append(f"| `{f.name}` | {_type_name(hints[f.name])} | {doc} |")
    return lines


def render() -> str:
    found = kinds()
    out = [HEADER, "", "# The JSON interface", "", INTRO.strip(), "", "## Kinds", ""]
    out += ["| kind | document |", "|---|---|"]
    out += [f"| `{kind}` | [`{cls.__name__}`](#{kind}) |" for kind, cls in found.items()]
    out.append("")
    documented: list[type] = []
    for kind, cls in found.items():
        out += [f"### {kind}", "", inspect.cleandoc(cls.__doc__ or ""), "", *_table(cls), ""]
        for nested in _nested(cls):
            if nested in documented:
                continue
            documented.append(nested)
            out += [f"#### `{nested.__name__}`", "", inspect.cleandoc(nested.__doc__ or "")]
            out += ["", *_table(nested), ""]
        schema = json.dumps(TypeAdapter(cls).json_schema(), indent=2, ensure_ascii=False)
        out += ["<details><summary>JSON Schema</summary>", "", "```json", schema, "```"]
        out += ["", "</details>", ""]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if out of date")
    args = parser.parse_args()

    content = render()
    if args.check:
        current = OUT.read_text() if OUT.exists() else ""
        if current != content:
            print(
                "docs/reference/json-interface.md is out of date; run scripts/gen_json_reference.py"
            )
            return 1
        print("docs/reference/json-interface.md is up to date")
        return 0
    OUT.write_text(content)
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
~~~~

Register it in `tests/test_docs_generated.py`, as the last entry of `CHECKED_GENERATORS`:

````python
    ("gen_json_reference.py", ["docs/reference/json-interface.md"], []),
````

Document the flag in `docs/reference/cli.md` under `## Global flags`, after the `--catalog` paragraph (`test_every_install_flag_is_documented` requires a `` `--json `` mention now that `install` accepts it):

````markdown
`--json`, before or after the verb, prints one JSON document on stdout instead
of text, for a front end to read; diagnostics go to stderr and the exit code is
unchanged. Every document, and which commands have one, is in
[json-interface.md](json-interface.md), generated from the code (**D-059**).
`install` and `uninstall` accept it only with `--dry-run`: a real install is
never driven through JSON. A command with no JSON form refuses it and runs
nothing.
````

- [ ] **Step 10: Generate the page and run the gates**

Run:
```
.venv/bin/python scripts/gen_json_reference.py
.venv/bin/python scripts/gen_json_reference.py --check
.venv/bin/ruff format . && .venv/bin/ruff check .
.venv/bin/mypy --strict
.venv/bin/pytest -q
.venv/bin/python scripts/check_doc_links.py
```
Expected: `wrote docs/reference/json-interface.md`; `docs/reference/json-interface.md is up to date`; `All checks passed!`; `Success: no issues found`; pytest all passed (the new `test_check_reports_the_page_current_and_writes_nothing[gen_json_reference.py]` among them); `no broken internal references`.

- [ ] **Step 11: Commit**

```bash
git add src/hammunition/interface src/hammunition/cli/main.py scripts/gen_json_reference.py \
  docs/reference/json-interface.md docs/reference/cli.md tests/json_support.py \
  tests/test_json_interface.py tests/fixtures/json tests/test_docs_generated.py pyproject.toml REUSE.toml
git commit -m "$(cat <<'EOF'
Engine JSON interface: envelope, --json on every verb, error document (D-059)

One document on stdout under --json, on every path: both streams point at
a recording tee over stderr while the command runs, and a command that
ends without a document gets an error document with its exit code. No
command has a JSON form yet; each is added by its own change. The
reference page is generated from the dataclasses.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `status --json`

**Files:**
- Create: `src/hammunition/interface/status.py`, `tests/test_json_status.py`
- Create (generated by the tests): `tests/fixtures/json/status-{empty,failed,interrupted,unverified}.{txt,json}`
- Modify: `src/hammunition/cli/main.py:457-549` (`cmd_status`)
- Regenerate: `docs/reference/json-interface.md`

**Interfaces:**
- Consumes: `envelope.json_capable`, `envelope.wanted`, `envelope.emit`, `Strict`, `described`, `TargetView`, `target_view` (Task 1); `hammunition.update.pin_of(planned: PlannedPackage) -> str | None`; `tests/json_support.py` (Task 1).
- Produces: `hammunition.interface.status.StatusDocument` (`KIND = "status"`), `build_status(*, target, catalog_root, packages, profiles, log_path, entries) -> StatusDocument`, `render_status(doc) -> list[str]`.

One text difference on an error path, deliberate: today `status` prints its `Target:` and `Debian family:` lines before loading the catalog, so a missing catalog printed those two lines and then the error. After this task nothing reaches stdout before the error. Every successful run's text is byte-identical, which Step 3 proves.

- [ ] **Step 1: Write the tests**

`tests/test_json_status.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``status --json``: the machine, the catalog, and what the log records.  D-059."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from hammunition.distro import Target
from hammunition.state import TransactionLog, log_path
from json_support import (
    FIXTURE_CATALOG,
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(
    distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13 (trixie)"
)

BEGIN: dict[str, Any] = {
    "event": "transaction_begin",
    "version": 2,
    "timestamp": "2026-09-28T12:00:00+00:00",
    "packages": ["fixture-apt", "fixture-source", "gone-unit"],
    "apt_packages": ["fixture-apt", "build-essential"],
    "deferred": [
        {
            "kind": "config",
            "subject": "fixture-source",
            "what": "/etc/fixture.conf not written",
            "why": "no callsign set",
        }
    ],
}
SCENARIOS: dict[str, list[dict[str, Any]]] = {
    "empty": [],
    "unverified": [
        BEGIN,
        {
            "event": "transaction_end",
            "version": 2,
            "completed": 4,
            "verified": False,
            "checks": [
                {"subject": "fixture-apt: installed", "confirmed": True},
                {
                    "subject": "fixture-source: /usr/local/bin/fixture",
                    "detail": "not on disk",
                    "confirmed": False,
                },
            ],
        },
    ],
    "failed": [BEGIN, {"event": "transaction_failed", "version": 1, "completed": 2}],
    "interrupted": [BEGIN, {"event": "command_begin", "version": 1, "argv": ["apt-get"]}],
}


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    entries: list[dict[str, Any]],
    *flags: str,
) -> tuple[int, str]:
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "root")
    log = TransactionLog(log_path())
    for entry in entries:
        log.append(entry)
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), "status", *flags])
    out = capsys.readouterr().out
    return rc, out.replace(str(tmp_path), "<state>").replace(str(FIXTURE_CATALOG), "<catalog>")


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_text_is_unchanged(
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc, out = _run(monkeypatch, tmp_path, capsys, SCENARIOS[scenario])
    assert rc == 0
    assert_golden_text(f"status-{scenario}", out)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_document_matches_its_golden_and_its_schema(
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc, out = _run(monkeypatch, tmp_path, capsys, SCENARIOS[scenario], "--json")
    assert rc == 0
    doc = parse_one(out)
    assert doc["kind"] == "status"
    validate(doc)
    assert_golden(f"status-{scenario}", doc)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_every_value_the_text_shows_is_in_the_json(
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hammunition.interface.status import render_status

    _rc, text = _run(monkeypatch, tmp_path, capsys, SCENARIOS[scenario])
    _rc, out = _run(monkeypatch, tmp_path / "again", capsys, SCENARIOS[scenario], "--json")
    assert_text_values_in_json(text, parse_one(out), render_status)


def test_recorded_units_say_how_the_last_transaction_naming_them_ended(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not a claim the unit is installed now -- `update --json` asks the
    machine -- but what the log recorded, with the catalog's method and pin."""
    _rc, out = _run(monkeypatch, tmp_path, capsys, SCENARIOS["failed"], "--json")
    units = {u["name"]: u for u in parse_one(out)["recorded_units"]}
    assert units["fixture-apt"]["last_outcome"] == "failed"
    assert units["fixture-apt"]["method"] == "apt" and units["fixture-apt"]["pin"] is None
    assert units["fixture-source"]["pin"].startswith("sha256 30cf6db1a2b4")
    assert units["gone-unit"]["method"] is None, "a unit the catalog no longer has is not guessed"


def test_an_unreadable_target_is_an_error_document_with_exit_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.distro import DetectionError

    def refuse(cls: type) -> Target:
        raise DetectionError("/etc/os-release declares no ID")

    monkeypatch.setattr(Target, "detect", classmethod(refuse))
    assert cli.main(["--catalog", str(FIXTURE_CATALOG), "status", "--json"]) == 1
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error" and "declares no ID" in doc["message"]
````

- [ ] **Step 2: Capture the text goldens from the code as it is now**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_status.py -q -k text_is_unchanged`
Expected: `4 passed`, and four files written. `tests/fixtures/json/status-unverified.txt` must read exactly:

```
Target: Debian GNU/Linux 13 (trixie) (ID=debian, version=13, arch=x86_64)
Debian family: yes
Catalog: <catalog>
  2 packages, 2 of which resolve on this target
  2 profiles
Transaction log: <state>/hammunition/transactions.jsonl
  2 entries
  most recent transaction completed 4 command(s); 2 package(s) intended
  UNVERIFIED: 1 effect(s) could not be confirmed:
    fixture-source: /usr/local/bin/fixture: not on disk
    fixture-apt
    build-essential
  deferred in that transaction, by design (1):
    fixture-source: /etc/fixture.conf not written -- no callsign set
```

Read all four; commit nothing yet.

- [ ] **Step 3: Run the rest to verify they fail**

Run: `.venv/bin/pytest tests/test_json_status.py -q`
Expected: the text tests PASS; the document tests FAIL (`status` has no `--json` form yet, so `doc["kind"] == "error"`); `test_every_value_the_text_shows_is_in_the_json` FAILS with `ModuleNotFoundError: No module named 'hammunition.interface.status'`.

- [ ] **Step 4: Write the status module**

`src/hammunition/interface/status.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``status`` as data: the machine, the catalog, and what the log records.  D-059."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from hammunition.distro import Target
from hammunition.interface.envelope import Strict, TargetView, described, target_view
from hammunition.manifest.schema import PackageManifest, ProfileManifest
from hammunition.plan import PlannedPackage
from hammunition.update import pin_of

__all__ = ["StatusDocument", "build_status", "render_status"]


@dataclass(frozen=True)
class CatalogSummary(Strict):
    """The catalog this run read."""

    path: str = described("the catalog directory")
    packages: int = described("manifests loaded")
    resolvable: int = described("of those, the ones with an install block for this target")
    profiles: int = described("profiles loaded")


@dataclass(frozen=True)
class CheckLine(Strict):
    """An effect the transaction could not confirm afterwards (D-031)."""

    subject: str = described("what was checked")
    detail: str = described("what was found instead")


@dataclass(frozen=True)
class LoggedDeferral(Strict):
    """Something that transaction deferred by design (D-035, D-039)."""

    kind: str = described("`config` or `package`")
    subject: str = described("what was deferred")
    what: str = described("what did not happen")
    why: str = described("what was missing")


@dataclass(frozen=True)
class LatestTransaction(Strict):
    """The most recent `transaction_begin` in the log, and how it ended."""

    when: str | None = described("its timestamp, ISO 8601, when recorded")
    outcome: str = described(
        "`completed`, `failed`, or `interrupted` (no ending recorded: killed, or still running)"
    )
    completed_commands: int | None = described("commands that ran; null when interrupted")
    intended: tuple[str, ...] = described("the apt packages it set out to install")
    verified: bool | None = described(
        "the D-031 effect check's verdict; null when the log predates it or the run did not end"
    )
    checks: int = described("effect checks recorded")
    unconfirmed: tuple[CheckLine, ...] = described("the checks that failed")
    deferred: tuple[LoggedDeferral, ...] = described("what it deferred")


@dataclass(frozen=True)
class RecordedUnit(Strict):
    """A unit some transaction here named, and how the latest such one ended.

    Not a claim that the unit is installed now: `update --json` compares the
    machine. A unit the catalog no longer carries has null method and pin."""

    name: str = described("the catalog unit")
    last_named: str | None = described("when the latest transaction naming it began")
    last_outcome: str = described("`completed`, `failed` or `interrupted`")
    catalog_version: str | None = described("the manifest's version today")
    method: str | None = described("the install method that resolves on this target")
    pin: str | None = described("the catalog's pin for a built unit; null for apt")


@dataclass(frozen=True)
class StatusDocument(Strict):
    """What this machine is, what the catalog holds, and what has been done here."""

    KIND: ClassVar[str] = "status"

    target: TargetView = described("the system")
    catalog: CatalogSummary = described("the catalog read")
    log_path: str = described("the transaction log file")
    log_entries: int = described("events in the log")
    latest: LatestTransaction | None = described(
        "the most recent transaction; null when the log records none"
    )
    recorded_units: tuple[RecordedUnit, ...] = described(
        "every unit a transaction here named, first-seen order"
    )


def _latest(entries: Sequence[Mapping[str, Any]]) -> LatestTransaction | None:
    begin_index = max(
        (i for i, e in enumerate(entries) if e.get("event") == "transaction_begin"),
        default=None,
    )
    if begin_index is None:
        return None
    begin = entries[begin_index]
    tail = entries[begin_index + 1 :]
    ended = next((e for e in tail if e.get("event") == "transaction_end"), None)
    failed = next((e for e in tail if e.get("event") == "transaction_failed"), None)
    verified: bool | None = None
    checks: list[Mapping[str, Any]] = []
    if failed is not None:
        outcome, completed = "failed", int(failed.get("completed", 0))
    elif ended is not None:
        outcome, completed = "completed", int(ended.get("completed", 0))
        # transaction_end version 2 carries the D-031 effect check; a version 1
        # entry has no `verified` key, and nothing is inferred from its absence.
        if "verified" in ended:
            verified = bool(ended.get("verified"))
            checks = list(ended.get("checks", []))
    else:
        outcome, completed = "interrupted", None
    return LatestTransaction(
        when=begin.get("timestamp"),
        outcome=outcome,
        completed_commands=completed,
        intended=tuple(str(p) for p in begin.get("apt_packages", [])),
        verified=verified,
        checks=len(checks),
        unconfirmed=tuple(
            CheckLine(subject=str(c.get("subject", "?")), detail=str(c.get("detail", "")))
            for c in checks
            if not c.get("confirmed", False)
        ),
        deferred=tuple(
            LoggedDeferral(
                kind=str(d.get("kind", "config")),
                subject=str(d.get("subject", "?")),
                what=str(d.get("what", "")),
                why=str(d.get("why", "")),
            )
            for d in begin.get("deferred", [])
        ),
    )


def _recorded(
    entries: Sequence[Mapping[str, Any]], packages: Mapping[str, PackageManifest], target: Target
) -> tuple[RecordedUnit, ...]:
    last: dict[str, tuple[str | None, str]] = {}
    current: tuple[str | None, list[str]] | None = None

    def close(outcome: str) -> None:
        if current is not None:
            for name in current[1]:
                last[name] = (current[0], outcome)

    for entry in entries:
        event = entry.get("event")
        if event == "transaction_begin":
            close("interrupted")
            current = (entry.get("timestamp"), [str(p) for p in entry.get("packages", [])])
            for name in current[1]:
                last.setdefault(name, (current[0], "interrupted"))
        elif event in ("transaction_end", "transaction_failed") and current is not None:
            close("completed" if event == "transaction_end" else "failed")
            current = None
    close("interrupted")

    units: list[RecordedUnit] = []
    for name, (when, outcome) in last.items():
        manifest = packages.get(name)
        block = manifest.resolve(target.distro, target.version, target.arch) if manifest else None
        pin = (
            pin_of(PlannedPackage(manifest=manifest, block=block, apt_packages=()))
            if manifest is not None and block is not None
            else None
        )
        units.append(
            RecordedUnit(
                name=name,
                last_named=when,
                last_outcome=outcome,
                catalog_version=manifest.version if manifest else None,
                method=block.install.method if block else None,
                pin=pin,
            )
        )
    return tuple(units)


def build_status(
    *,
    target: Target,
    catalog_root: Path,
    packages: Mapping[str, PackageManifest],
    profiles: Mapping[str, ProfileManifest],
    log_path: Path,
    entries: Sequence[Mapping[str, Any]],
) -> StatusDocument:
    resolvable = sum(
        1 for m in packages.values() if m.resolve(target.distro, target.version, target.arch)
    )
    return StatusDocument(
        target=target_view(target),
        catalog=CatalogSummary(
            path=str(catalog_root),
            packages=len(packages),
            resolvable=resolvable,
            profiles=len(profiles),
        ),
        log_path=str(log_path),
        log_entries=len(entries),
        latest=_latest(entries),
        recorded_units=_recorded(entries, packages, target),
    )


def render_status(doc: StatusDocument) -> list[str]:
    """``status`` as the terminal shows it."""
    lines = [
        f"Target: {doc.target.description}",
        "Debian family: "
        + ("yes" if doc.target.debian_family else "no — installation is refused here"),
        f"Catalog: {doc.catalog.path}",
        f"  {doc.catalog.packages} packages, {doc.catalog.resolvable} of which resolve on this target",
        f"  {doc.catalog.profiles} profiles",
        f"Transaction log: {doc.log_path}",
    ]
    if not doc.log_entries:
        return [*lines, "  no transactions recorded"]
    lines.append(f"  {doc.log_entries} entries")
    latest = doc.latest
    if latest is None:
        return [*lines, "  no transaction start recorded (log holds only other events)"]
    intended = len(latest.intended)
    if latest.outcome == "failed":
        lines.append(
            f"  most recent transaction FAILED after {latest.completed_commands} command(s); "
            f"{intended} package(s) were intended, not necessarily installed"
        )
    elif latest.outcome == "completed":
        lines.append(
            f"  most recent transaction completed {latest.completed_commands} "
            f"command(s); {intended} package(s) intended"
        )
        if latest.verified is True:
            lines.append(f"  effects confirmed afterwards: {latest.checks} check(s) passed (D-031)")
        elif latest.verified is False:
            lines.append(
                f"  UNVERIFIED: {len(latest.unconfirmed)} effect(s) could not be confirmed:"
            )
            lines += [f"    {c.subject}: {c.detail}" for c in latest.unconfirmed]
    else:
        lines.append(
            f"  most recent transaction did not record an ending (interrupted or "
            f"still running); {intended} package(s) were intended"
        )
    lines += [f"    {name}" for name in latest.intended]
    if latest.deferred:
        lines.append(f"  deferred in that transaction, by design ({len(latest.deferred)}):")
        lines += [f"    {d.subject}: {d.what} -- {d.why}" for d in latest.deferred]
    return lines
````

- [ ] **Step 5: Route `cmd_status` through it**

Replace `cmd_status` (lines 457-549) with:

````python
@envelope.json_capable()
def cmd_status(args: argparse.Namespace) -> int:
    """What this machine is, what the catalog holds, and what has been done here.

    The most recent transaction is reported by how it actually ended, not by
    what it intended: reading only transaction_begin once reported a run that
    died on package 3 of 20 as if all 20 landed.
    """
    from hammunition.interface.status import build_status, render_status

    try:
        target = Target.detect()
    except DetectionError as exc:
        print(f"Target: unidentified — {exc}", file=sys.stderr)
        return EXIT_FAILED

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    log = TransactionLog(owner=operator(args) or None)
    doc = build_status(
        target=target,
        catalog_root=catalog_root,
        packages=packages,
        profiles=profiles,
        log_path=log.path,
        entries=list(log.read()),
    )
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_status(doc):
        print(line)
    return EXIT_OK
````

- [ ] **Step 6: Create the JSON goldens, then run everything**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_status.py -q -k document_matches` then `.venv/bin/pytest tests/test_json_status.py tests/test_cli.py -q`
Expected: first `4 passed`, four `status-*.json` written; read `status-failed.json` and confirm `recorded_units` names `gone-unit` with `"method": null`. Second: all passed, the text goldens unchanged from Step 2 (`git status` shows them as new files only, never modified after Step 2).

- [ ] **Step 7: Regenerate the page, run the gates, commit**

Run: `.venv/bin/python scripts/gen_json_reference.py && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q`
Expected: `wrote docs/reference/json-interface.md`, `All checks passed!`, `Success: no issues found`, all passed.

```bash
git add src/hammunition/interface/status.py src/hammunition/cli/main.py tests/test_json_status.py \
  tests/fixtures/json/status-* docs/reference/json-interface.md
git commit -m "$(cat <<'EOF'
status --json: the machine, the catalog, and what the log recorded (D-059)

Text and document render from one StatusDocument; the text is byte-for-byte
what it was, held by goldens captured before the change. The document adds
every unit a transaction named, with how the last one ended.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `list --json` and `show --json`

**Files:**
- Create: `src/hammunition/interface/catalog.py`, `tests/test_json_catalog.py`
- Create (generated by the tests): `tests/fixtures/json/{list-all,list-packages,list-profiles,show-gated,show-station}.{txt,json}`, `tests/fixtures/json/show-unit.json`
- Modify: `src/hammunition/cli/main.py:409-440` (`cmd_list`), `src/hammunition/cli/main.py:1572-1591` (`cmd_show`)
- Regenerate: `docs/reference/json-interface.md`

**Interfaces:**
- Consumes: Task 1's envelope and helpers; `hammunition.consent.render_disclosure(gate, profile) -> str`.
- Produces: `hammunition.interface.catalog`: `CatalogDocument` (`KIND = "catalog"`), `ProfileDocument` (`"profile"`), `UnitDocument` (`"unit"`), `build_catalog(what, packages, profiles, target) -> CatalogDocument`, `build_profile(profile) -> ProfileDocument`, `build_unit(manifest, target) -> UnitDocument`, `render_catalog(doc) -> list[str]`, `render_profile(doc) -> list[str]`, `detect_target() -> Target | None`.

`show` describes profiles today and refuses a unit's name with exit 2. Under `--json` it also accepts a unit and emits a `unit` document (the manifest as its YAML sets it); the text form is unchanged, so it still refuses a unit.

- [ ] **Step 1: Write the tests**

`tests/test_json_catalog.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``list --json`` and ``show --json``: what the catalog offers.  D-059."""

from __future__ import annotations

import importlib

import pytest

from hammunition.distro import DetectionError, Target
from json_support import (
    FIXTURE_CATALOG,
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(
    distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13 (trixie)"
)
RUNS = {
    "list-all": ["list"],
    "list-packages": ["list", "packages"],
    "list-profiles": ["list", "profiles"],
    "show-gated": ["show", "fixture-gated"],
    "show-station": ["show", "fixture-station"],
}


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    *,
    target: Target | None = TARGET,
) -> tuple[int, str]:
    def detect(cls: type) -> Target:
        if target is None:
            raise DetectionError("no /etc/os-release")
        return target

    monkeypatch.setattr(Target, "detect", classmethod(detect))
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), *argv])
    return rc, capsys.readouterr().out


@pytest.mark.parametrize("name", sorted(RUNS))
def test_the_text_is_unchanged(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, RUNS[name])
    assert rc == 0
    assert_golden_text(name, out)


@pytest.mark.parametrize("name", sorted(RUNS))
def test_the_document_matches_its_golden_and_its_schema(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, [*RUNS[name], "--json"])
    assert rc == 0
    doc = parse_one(out)
    validate(doc)
    assert_golden(name, doc)


@pytest.mark.parametrize("name", sorted(RUNS))
def test_every_value_the_text_shows_is_in_the_json(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.catalog import render_catalog, render_profile

    _rc, text = _run(monkeypatch, capsys, RUNS[name])
    _rc, out = _run(monkeypatch, capsys, [*RUNS[name], "--json"])
    assert_text_values_in_json(text, parse_one(out), render_catalog, render_profile)


def test_an_unknown_target_lists_every_package_as_unknown_not_unsupported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, ["list", "--json"], target=None)
    doc = parse_one(out)
    assert rc == 0 and doc["target"] is None
    assert {p["resolves_here"] for p in doc["packages"]} == {None}


def test_show_of_a_unit_is_json_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, ["show", "fixture-apt", "--json"])
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "unit"
    validate(doc)
    assert doc["manifest"]["name"] == "fixture-apt"
    assert_golden("show-unit", doc)
    # The text form is unchanged: it describes profiles, and says so.
    rc, _out = _run(monkeypatch, capsys, ["show", "fixture-apt"])
    assert rc == cli.EXIT_UNPLANNABLE


def test_show_of_an_unknown_name_is_an_error_document_with_exit_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _run(monkeypatch, capsys, ["show", "no-such-thing", "--json"])
    doc = parse_one(out)
    assert rc == cli.EXIT_UNPLANNABLE and doc["kind"] == "error"
    assert "no-such-thing" in doc["message"]
````

- [ ] **Step 2: Capture the text goldens from the code as it is now**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_catalog.py -q -k text_is_unchanged`
Expected: `5 passed`; five `.txt` files written. `show-gated.txt` must contain the line `Profile 'fixture-gated' is consent-gated.` and end with `  fixture-apt`.

- [ ] **Step 3: Run the rest to verify they fail**

Run: `.venv/bin/pytest tests/test_json_catalog.py -q`
Expected: text tests PASS; every document test FAILS (`kind` is `error`: no JSON form yet) or errors with `No module named 'hammunition.interface.catalog'`.

- [ ] **Step 4: Write the catalog module**

`src/hammunition/interface/catalog.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``list`` and ``show`` as data: what the catalog offers.  D-059."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from hammunition.consent import render_disclosure
from hammunition.distro import DetectionError, Target
from hammunition.interface.envelope import Strict, TargetView, described, target_view
from hammunition.manifest.schema import PackageManifest, ProfileManifest

__all__ = [
    "CatalogDocument",
    "ProfileDocument",
    "UnitDocument",
    "build_catalog",
    "build_profile",
    "build_unit",
    "detect_target",
    "render_catalog",
    "render_profile",
]


def detect_target() -> Target | None:
    """The target, or None where /etc/os-release cannot be read."""
    try:
        return Target.detect()
    except DetectionError:
        return None


@dataclass(frozen=True)
class ProfileDocs(Strict):
    """The documentation every profile carries (CLAUDE.md)."""

    what_it_installs: str = described("what the profile installs")
    why_together: str = described("why those things belong together")
    deliberately_excludes: str = described("what it leaves out, and why")
    manual_configuration: str = described("what the operator still sets up by hand")
    disk_footprint_hint: str | None = described("a disk estimate, when the profile states one")


@dataclass(frozen=True)
class ProfileEntry(Strict):
    """One profile in the catalog."""

    name: str = described("the profile")
    summary: str = described("one line")
    stage: str = described("`1.0` or `post-1.0`")
    packages: tuple[str, ...] = described("its member units")
    consent_gated: bool = described("installing it presents a consent gate (D-021)")
    documentation: ProfileDocs = described("its documentation")


@dataclass(frozen=True)
class PackageEntry(Strict):
    """One unit in the catalog."""

    name: str = described("the unit")
    version: str = described("the manifest's version")
    summary: str = described("one line")
    categories: tuple[str, ...] = described("its tags")
    status: str = described("`supported`, `broken`, `retired` or `unverifiable`")
    methods: tuple[str, ...] = described("the install method of every block, in manifest order")
    resolves_here: str | None = described(
        "the method that resolves on this target; null when none does or the target is unknown"
    )


@dataclass(frozen=True)
class CatalogDocument(Strict):
    """Every profile and unit the catalog offers, and what resolves here."""

    KIND: ClassVar[str] = "catalog"

    what: str = described("`all`, `packages` or `profiles`, as asked")
    target: TargetView | None = described("the system; null when /etc/os-release is unreadable")
    profiles: tuple[ProfileEntry, ...] = described("by name; empty when `what` is `packages`")
    packages: tuple[PackageEntry, ...] = described("by name; empty when `what` is `profiles`")


@dataclass(frozen=True)
class ConsentView(Strict):
    """A profile's consent gate, as `show` discloses it."""

    env_var: str = described("the scripted-consent variable")
    risk_categories: tuple[str, ...] = described("the capabilities disclosed")
    disclosure: str = described("the exact text the gate shows")


@dataclass(frozen=True)
class SuggestionView(Strict):
    """A choice the profile offers when nothing already answers it."""

    name: str = described("what is suggested, e.g. a logger")
    reason: str = described("why")
    options: tuple[str, ...] = described("the units offered")
    recommended: str | None = described("the default choice")
    detect_commands: tuple[str, ...] = described("commands whose presence means one is installed")


@dataclass(frozen=True)
class ProfileDocument(Strict):
    """One profile, everything `show` prints, disclosure included."""

    KIND: ClassVar[str] = "profile"

    name: str = described("the profile")
    summary: str = described("one line")
    stage: str = described("`1.0` or `post-1.0`")
    documentation: ProfileDocs = described("its documentation")
    consent: ConsentView | None = described("its consent gate; null when ungated")
    packages: tuple[str, ...] = described("its member units")
    suggests_one_of: tuple[SuggestionView, ...] = described("choices it offers")


@dataclass(frozen=True)
class UnitDocument(Strict):
    """One unit's manifest. JSON only: the text `show` describes profiles."""

    KIND: ClassVar[str] = "unit"

    name: str = described("the unit")
    resolves_here: str | None = described("the method that resolves on this target")
    manifest: dict[str, Any] = described(
        "the manifest as its YAML sets it, unset fields left out; every field is documented in "
        "docs/reference/schema.md"
    )


def _docs(profile: ProfileManifest) -> ProfileDocs:
    d = profile.documentation
    return ProfileDocs(
        what_it_installs=d.what_it_installs.strip(),
        why_together=d.why_together.strip(),
        deliberately_excludes=d.deliberately_excludes.strip(),
        manual_configuration=d.manual_configuration.strip(),
        disk_footprint_hint=d.disk_footprint_hint.strip() if d.disk_footprint_hint else None,
    )


def _resolves(manifest: PackageManifest, target: Target | None) -> str | None:
    if target is None:
        return None
    block = manifest.resolve(target.distro, target.version, target.arch)
    return block.install.method if block else None


def build_catalog(
    what: str,
    packages: Mapping[str, PackageManifest],
    profiles: Mapping[str, ProfileManifest],
    target: Target | None,
) -> CatalogDocument:
    return CatalogDocument(
        what=what,
        target=target_view(target) if target is not None else None,
        profiles=tuple(
            ProfileEntry(
                name=name,
                summary=profiles[name].summary,
                stage=profiles[name].stage,
                packages=tuple(profiles[name].packages),
                consent_gated=profiles[name].consent is not None,
                documentation=_docs(profiles[name]),
            )
            for name in sorted(profiles)
        )
        if what in {"profiles", "all"}
        else (),
        packages=tuple(
            PackageEntry(
                name=name,
                version=packages[name].version,
                summary=packages[name].summary,
                categories=tuple(packages[name].categories),
                status=packages[name].status.value,
                methods=tuple(block.install.method for block in packages[name].install),
                resolves_here=_resolves(packages[name], target),
            )
            for name in sorted(packages)
        )
        if what in {"packages", "all"}
        else (),
    )


def render_catalog(doc: CatalogDocument) -> list[str]:
    """``list`` as the terminal shows it."""
    lines: list[str] = []
    if doc.what in {"profiles", "all"}:
        lines.append(f"Profiles ({len(doc.profiles)}):")
        for profile in doc.profiles:
            gate = "  [consent gate]" if profile.consent_gated else ""
            lines.append(
                f"  {profile.name:<16} {profile.stage:<9} {len(profile.packages):>3} pkg{gate}"
            )
            lines.append(f"      {profile.summary}")
        lines.append("")
    if doc.what in {"packages", "all"}:
        lines.append(f"Packages ({len(doc.packages)}):")
        for package in doc.packages:
            where = "?" if doc.target is None else package.resolves_here or "unsupported here"
            flag = "" if package.status == "supported" else f"  [{package.status}]"
            lines.append(f"  {package.name:<28} {where:<18}{flag}")
            lines.append(f"      {package.summary}")
    return lines


def build_profile(profile: ProfileManifest) -> ProfileDocument:
    gate = profile.consent
    return ProfileDocument(
        name=profile.name,
        summary=profile.summary,
        stage=profile.stage,
        documentation=_docs(profile),
        consent=ConsentView(
            env_var=gate.env_var,
            risk_categories=tuple(c.value for c in gate.risk_categories),
            disclosure=render_disclosure(gate, profile.name),
        )
        if gate is not None
        else None,
        packages=tuple(profile.packages),
        suggests_one_of=tuple(
            SuggestionView(
                name=g.name,
                reason=g.reason,
                options=tuple(g.options),
                recommended=g.recommended,
                detect_commands=tuple(g.detect_commands),
            )
            for g in profile.suggests_one_of
        ),
    )


def render_profile(doc: ProfileDocument) -> list[str]:
    """``show`` as the terminal shows it."""
    d = doc.documentation
    lines = [
        f"{doc.name} — {doc.summary}",
        f"stage: {doc.stage}",
        "",
        d.what_it_installs,
        "",
        "Why together:",
        f"  {d.why_together}",
        "",
        "Deliberately excludes:",
        f"  {d.deliberately_excludes}",
        "",
        "You still configure by hand:",
        f"  {d.manual_configuration}",
    ]
    if doc.consent is not None:
        lines += ["", doc.consent.disclosure]
    lines += ["", f"Packages ({len(doc.packages)}):"]
    lines += [f"  {name}" for name in doc.packages]
    return lines


def build_unit(manifest: PackageManifest, target: Target | None) -> UnitDocument:
    return UnitDocument(
        name=manifest.name,
        resolves_here=_resolves(manifest, target),
        manifest=manifest.model_dump(mode="json", exclude_unset=True),
    )
````

- [ ] **Step 5: Route the two commands through it**

Replace `cmd_list` (lines 409-440) with:

````python
@envelope.json_capable()
def cmd_list(args: argparse.Namespace) -> int:
    from hammunition.interface.catalog import build_catalog, detect_target, render_catalog

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    doc = build_catalog(args.what, packages, profiles, detect_target())
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_catalog(doc):
        print(line)
    return EXIT_OK
````

Replace `cmd_show` (lines 1572-1591) with:

````python
@envelope.json_capable()
def cmd_show(args: argparse.Namespace) -> int:
    """Print a profile, its consent disclosure included, without installing it.

    Under --json a unit's name is accepted too, and emits its manifest (D-059);
    the text form describes profiles only, as it always has.
    """
    from hammunition.interface.catalog import (
        build_profile,
        build_unit,
        detect_target,
        render_profile,
    )

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    profile = profiles.get(args.profile)
    if profile is None:
        manifest = packages.get(args.profile)
        if manifest is not None and envelope.wanted(args):
            envelope.emit(build_unit(manifest, detect_target()))
            return EXIT_OK
        print(f"error: no profile named {args.profile!r}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    doc = build_profile(profile)
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_profile(doc):
        print(line)
    return EXIT_OK
````

- [ ] **Step 6: Create the JSON goldens, then run everything**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_catalog.py -q -k "document_matches or unit_is_json_only"` then `.venv/bin/pytest tests/test_json_catalog.py tests/test_cli.py -q`
Expected: first `6 passed`; read `show-unit.json` and confirm `manifest.install[0].install.method` is `"apt"` (an unset-only dump keeps it because the YAML sets it; a defaults-excluding dump would drop the discriminator). Second: all passed.

- [ ] **Step 7: Regenerate the page, run the gates, commit**

Run: `.venv/bin/python scripts/gen_json_reference.py && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q`
Expected: as Task 2 Step 7.

```bash
git add src/hammunition/interface/catalog.py src/hammunition/cli/main.py tests/test_json_catalog.py \
  tests/fixtures/json/list-* tests/fixtures/json/show-* docs/reference/json-interface.md
git commit -m "$(cat <<'EOF'
list --json and show --json: the catalog as data (D-059)

A catalog document for list, a profile document for show, and under
--json a unit document for a unit's name. Text unchanged, held by goldens.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: The plan as data; `install`/`uninstall --dry-run --json`

**Files:**
- Create: `src/hammunition/interface/plan.py`, `tests/test_json_plan.py`, `tests/test_json_install.py`
- Create (generated by the tests): `tests/fixtures/json/plan-install-text.txt`, `tests/fixtures/json/{install,uninstall}-dry-run.{txt,json}`
- Modify: `src/hammunition/cli/main.py:185-401` (`_plan_state`, `render_plan`), `887-1158` (`cmd_install`), `1190-1347` (`cmd_uninstall`), and the imports `ruff check --fix` removes (lines 57-98)
- Regenerate: `docs/reference/json-interface.md`

**Interfaces:**
- Consumes: Task 1's envelope, `text.wrap`, helpers; `hammunition.plan` (`InstallPlan`, `PlannedPackage`, `Blocker`, `Deferral`, `GroupMembership`, `RepoAddition`); `hammunition.state.RemovalPlan`, `ArtifactRemoval`; `hammunition.execute.Step`; `hammunition.consent.repo_env_var`; `hammunition.backends.data.human_size`.
- Produces, in `hammunition.interface.plan`: `PlanDocument` (`KIND = "plan"`: `action, requested, outcome, target, blockers, install, removal`), `InstallPlanView`, `RemovalPlanView`, `StepView`, `BlockerLine`, `plan_state(planned, built) -> str` (moved from `cli/main.py::_plan_state`), `build_install_view(plan, commands, *, euid, log_destination=None, hands_log_to=None, built=frozenset(), suggestion_notes=()) -> InstallPlanView`, `render_plan_view(view, *, target: TargetView) -> list[str]`, `build_removal_view(plan, commands, *, euid) -> RemovalPlanView`, `render_removal_view(view, *, target) -> list[str]`, `refused_plan(action, requested, target, blockers) -> PlanDocument`, `NOT_REVERSED: str`.
- `cli.main.render_plan(plan, commands, *, euid, log_destination=None, hands_log_to=None, built=frozenset()) -> list[str]` keeps its signature (tests and #121 call it); it becomes a thin wrapper over `build_install_view` + `render_plan_view`.

The plan text is the operator's whole disclosure. This task moves every line of it into a renderer that reads a dataclass, and must not move a byte: the goldens in Steps 2 and 3 are captured from the code **before** the refactor.

- [ ] **Step 1: Write the render-level golden test**

`tests/test_json_plan.py` (a plan with every section populated, rendered by `render_plan` directly):

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The plan as data: ``install``/``uninstall --dry-run --json``.  D-059.

The text plan is the operator's whole disclosure, so the refactor that makes
it render from a dataclass must not move a byte: the golden text below was
captured from ``render_plan`` *before* the refactor and is compared after it.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import Action, Command
from hammunition.distro import Target
from hammunition.manifest.schema import AptRepo, ConfigFile, ConsentGate, PackageManifest
from hammunition.plan import Deferral, GroupMembership, InstallPlan, PlannedPackage, RepoAddition
from json_support import assert_golden_text

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(
    distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13 (trixie)"
)


def _unit(name: str, install: dict[str, Any], **extra: Any) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "1.0",
            "summary": f"The {name} fixture",
            "categories": ["digital-modes"],
            "install": [{"install": install, **extra}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for a unit in the plan golden test.",
                "why_you_want_it": "Every section of the plan needs something to show.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def rich_plan() -> tuple[InstallPlan, list[Any]]:
    """An install plan with every section of the text populated."""
    apt = _unit("fixture-apt", {"method": "apt", "packages": ["fixture-apt", "libfixture1"]})
    quiet = _unit(
        "fixture-quiet",
        {"method": "apt", "packages": ["fixture-quiet"], "install_recommends": False},
    )
    source = _unit(
        "fixture-source",
        {
            "method": "source",
            "source": {
                "url": "https://example.invalid/fixture-source-2.1.tar.gz",
                "sha256": "30cf6db1a2b495975a499b45f3e760758579b81c99157b2d52d699f0c46ff9a4",
            },
            "build_system": "autotools",
        },
        build_depends=["build-essential"],
    )
    data = _unit(
        "fixture-data",
        {
            "method": "data",
            "artifacts": [
                {
                    "url": "https://example.invalid/cty.dat",
                    "sha256": "30cf6db1a2b495975a499b45f3e760758579b81c99157b2d52d699f0c46ff9a4",
                    "size": 1_433_600,
                    "install_as": "cty.dat",
                }
            ],
            "licence": "free with notice ",
            "licence_url": "https://example.invalid/licence",
        },
    )
    repo = AptRepo(
        name="fixture-repo",
        uri="https://example.invalid/apt",
        suites=["stable"],
        components=["main"],
        key_url="https://example.invalid/key.asc",
        key_fingerprint="0123456789ABCDEF0123456789ABCDEF01234567",
        rationale="The fixture archive is the only source of fixture-repo-tool.",
    )
    gate = ConsentGate.model_validate(
        {
            "env_var": "HAMMUNITION_ACCEPT_FIXTURE_GATED",
            "risk_categories": ["identifier_collection"],
            "disclosure": "This fixture stands in for software that can receive identifiers.",
            "affirmation": "Do you affirm that you have the authorization you need?",
        }
    )
    plan = InstallPlan(
        target=TARGET,
        packages=(
            PlannedPackage(
                manifest=apt,
                block=apt.install[0],
                apt_packages=("fixture-apt", "libfixture1"),
                already_installed=("libfixture1",),
                requested_by=("fixture-station",),
                displaces=("fixture-apt-legacy",),
            ),
            PlannedPackage(manifest=quiet, block=quiet.install[0], apt_packages=("fixture-quiet",)),
            PlannedPackage(
                manifest=source,
                block=source.install[0],
                apt_packages=("build-essential",),
                build_only=("build-essential",),
            ),
            PlannedPackage(manifest=data, block=data.install[0], apt_packages=()),
        ),
        group_memberships=(
            GroupMembership(
                group="dialout",
                user="op",
                package="fixture-apt",
                description="serial access",
                detail="Lets the operator open serial ports: rig CAT cables, TNCs and GPS "
                "receivers. It also grants every other serial device on the machine.",
                reverse_hint="sudo gpasswd -d op dialout ",
            ),
        ),
        consent_gates=(("fixture-gated", gate),),
        notes=("fixture-source shadows nothing on PATH; this note is here to be wrapped " * 2,),
        deferrals=(
            Deferral(
                subject="fixture-apt",
                what="/etc/fixture.conf not written",
                why="no callsign set",
                remedy="hammunition station set --callsign N0TST",
            ),
        ),
        config_files=(
            (
                "fixture-apt",
                ConfigFile(path="/etc/fixture-apt.conf", template="call {station.callsign}"),
                "call N0TST",
            ),
        ),
        apt_release="trixie-backports",
        apt_from_release=("libfixture1",),
        apt_repos=(
            RepoAddition(
                unit="fixture-apt",
                repo=repo,
                sources="/etc/apt/sources.list.d/fixture-repo.sources",
                keyring="/etc/apt/keyrings/fixture-repo.gpg",
                packages=("fixture-repo-tool",),
            ),
        ),
    )
    commands: list[Any] = [
        Command(
            argv=("apt-get", "install", "--yes", "--", "fixture-apt"),
            description="Install the apt packages",
            requires_root=True,
        ),
        Action(
            kind="fetch",
            description="Fetch and verify the fixture-source tarball",
            detail="https://example.invalid/fixture-source-2.1.tar.gz",
            perform=lambda: "fetched",
        ),
    ]
    return plan, commands


def test_the_text_plan_is_unchanged_byte_for_byte() -> None:
    plan, commands = rich_plan()
    lines = cli.render_plan(
        plan,
        commands,
        euid=1000,
        built=frozenset(),
        log_destination=Path("/home/op/.local/state/hammunition/transactions.jsonl"),
        hands_log_to="op",
    )
    assert_golden_text("plan-install-text", "\n".join(lines) + "\n")


def test_every_section_of_the_fixture_is_populated() -> None:
    """Guards the guard: a section left empty in the fixture is a section the
    byte-for-byte test does not cover."""
    plan, _commands = rich_plan()
    for name in (f.name for f in dataclasses.fields(plan)):
        assert getattr(plan, name), f"rich_plan() leaves {name} empty"
    assert plan.apt_to_install_no_recommends


@pytest.mark.parametrize("euid", [0, 1000])
def test_the_rendered_plan_names_every_command(euid: int) -> None:
    plan, commands = rich_plan()
    text = "\n".join(cli.render_plan(plan, commands, euid=euid))
    for command in commands:
        assert command.display(euid=euid) in text
````

- [ ] **Step 2: Capture its golden from the code as it is now**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_plan.py -q`
Expected: `4 passed`; `tests/fixtures/json/plan-install-text.txt` written and reading exactly:

```
Target: Debian GNU/Linux 13 (trixie) (ID=debian, version=13, arch=x86_64)

Packages (4):
  fixture-apt                  will install       [fixture-station]
      + fixture-apt
      = libfixture1
  fixture-quiet                will install       [requested]
      + fixture-quiet
  fixture-source               will build         [requested]
      + build-essential  (to build)
  fixture-data                 will fetch+install [requested]

Installed distribution packages displaced or shadowed (D-022):
  fixture-apt-legacy  — declared by fixture-apt; the distribution package stays installed, see that manifest's notes

apt packages resolved from trixie-backports (D-038):
  apt refused the default release because a package this machine already installs from
  trixie-backports would have been downgraded; the apt step runs with --target-release
  trixie-backports, which takes these from there:
      libfixture1

apt packages installed without Recommends (D-052):
  fixture-quiet asked for --no-install-recommends in the manifest, because the
  Recommends of these packages conflict with software this target installs; a second
  apt-get install carries the flag for them alone. Everything else in this transaction
  keeps apt's defaults, and both commands run with --no-remove:
      fixture-quiet

Third-party apt repositories that will be added (D-040):
  fixture-repo  [fixture-apt: fixture-repo-tool]
      https://example.invalid/apt  stable  main
      key 0123456789ABCDEF0123456789ABCDEF01234567
      writes /etc/apt/sources.list.d/fixture-repo.sources
      writes /etc/apt/keyrings/fixture-repo.gpg
      consent: HAMMUNITION_ACCEPT_APT_REPO_FIXTURE_REPO must equal the key fingerprint

Offline data that will be downloaded and installed (D-049):
  fixture-data                 1.4 MB total, licence: free with notice
      stated at https://example.invalid/licence
         1.4 MB  https://example.invalid/cty.dat
      installs under <prefix>/share/hammunition/data/fixture-data/

Group membership changes:
  op → dialout  (fixture-apt)
      Lets the operator open serial ports: rig CAT cables, TNCs and GPS receivers. It
      also grants every other serial device on the machine.
      reverse: sudo gpasswd -d op dialout

Consent gates that will be presented:
  fixture-gated (HAMMUNITION_ACCEPT_FIXTURE_GATED)
      - identifier_collection: Can collect identifiers associated with people or their
        devices, such as IMSI, IMEI, MAC addresses, or subscriber records.

Configuration that will be written:
  /etc/fixture-apt.conf  (written, mode 0644, existing file backed up)  [fixture-apt]

Will NOT happen (the rest of the transaction still will):
  fixture-apt: /etc/fixture.conf not written
      why: no callsign set
      → hammunition station set --callsign N0TST

Notes:
  - fixture-source shadows nothing on PATH; this note is here to be wrapped fixture-
      source shadows nothing on PATH; this note is here to be wrapped

Records:
  transaction log written to /home/op/.local/state/hammunition/transactions.jsonl
  the log and any directories created for it are given to 'op' (chown), since root is writing into their home

Commands (2):
  # Install the apt packages
  $ sudo apt-get install --yes -- fixture-apt
  # Fetch and verify the fixture-source tarball
  $ [fetch] https://example.invalid/fixture-source-2.1.tar.gz
```

If any line differs, stop: the fixture or the environment is not what this plan assumes.

- [ ] **Step 3: Write the command-level tests and capture their text goldens**

`tests/test_json_install.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``install``/``uninstall --dry-run --json`` through main().  D-059."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.apt import AptBackend, AptPackageState, AptSimulation
from hammunition.distro import Target
from hammunition.state import ArtifactRemoval, RemovalPlan
from json_support import (
    FIXTURE_CATALOG,
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(
    distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13 (trixie)"
)


def _machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    """A target and an apt that need no real machine, as an unprivileged
    operator `op`; returns the placeholders for the machine paths."""
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    for var in ("XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "op")
    monkeypatch.setattr(AptBackend, "lists_populated", lambda self: True)
    monkeypatch.setattr(
        AptBackend,
        "probe",
        lambda self, pkgs: {
            p: AptPackageState(name=p, installed=None, candidate="1.0") for p in pkgs
        },
    )
    monkeypatch.setattr(
        AptBackend,
        "simulate",
        lambda self, pkgs, *, release=None, no_recommends=False: AptSimulation(
            ok=True, installs={p: frozenset({"stable"}) for p in pkgs}, release=release
        ),
    )
    return {str(tmp_path): "<tmp>", str(FIXTURE_CATALOG): "<catalog>"}


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), *argv])
    return rc, capsys.readouterr().out


def _placeholders(text: str, replacements: dict[str, str]) -> str:
    for real, placeholder in replacements.items():
        text = text.replace(real, placeholder)
    return text


def test_the_install_text_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "install", "--dry-run", "fixture-apt")
    assert rc == 0
    assert_golden_text("install-dry-run", _placeholders(out, paths))


def test_the_install_plan_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.plan import render_plan_view

    paths = _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "install", "--dry-run", "--json", "fixture-apt")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "plan" and doc["outcome"] == "planned"
    validate(doc)
    assert_golden("install-dry-run", doc, paths)
    _rc, text = _run(capsys, "install", "--dry-run", "fixture-apt")
    assert_text_values_in_json(text, doc, render_plan_view, cli.cmd_install)


def test_a_refused_plan_is_a_plan_document_with_every_blocker_and_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "install", "--dry-run", "--json", "no-such-unit")
    doc = parse_one(out)
    assert rc == cli.EXIT_UNPLANNABLE
    assert doc["kind"] == "plan" and doc["outcome"] == "refused"
    assert doc["install"] is None
    assert any(b["subject"] == "no-such-unit" for b in doc["blockers"])
    validate(doc)


def test_a_real_install_is_never_driven_through_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review focus: without --dry-run, --json is refused before resolution,
    so no consent gate, sudo prompt or command can be reached."""
    _machine(monkeypatch, tmp_path)

    def must_not_resolve(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a --json install without --dry-run reached resolution")

    monkeypatch.setattr(cli, "resolve", must_not_resolve)
    for verb in ("install", "uninstall"):
        rc, out = _run(capsys, verb, "--json", "--yes", "fixture-apt")
        doc = parse_one(out)
        assert rc == cli.EXIT_UNPLANNABLE and doc["kind"] == "error"
        assert "never driven through --json" in doc["message"]


def _removal(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = RemovalPlan(
        to_remove={"fixture-apt": ["fixture-apt"]},
        left_foreign={"fixture-station": ["libfixture1"]},
        already_absent={"fixture-source": []},
        artifacts={
            "fixture-source": [
                ArtifactRemoval(
                    kind="binary", path=Path("/usr/local/bin/fixture-source"), basis="log"
                )
            ]
        },
        left_unattributed={"fixture-source": ["/usr/local/share/fixture-source/extra"]},
    )
    monkeypatch.setattr(cli, "plan_removal", lambda *args, **kwargs: plan)


def test_the_uninstall_text_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _machine(monkeypatch, tmp_path)
    _removal(monkeypatch)
    rc, out = _run(capsys, "uninstall", "--dry-run", "fixture-apt")
    assert rc == 0
    assert_golden_text("uninstall-dry-run", _placeholders(out, paths))


def test_the_uninstall_plan_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.plan import render_removal_view

    paths = _machine(monkeypatch, tmp_path)
    _removal(monkeypatch)
    rc, out = _run(capsys, "uninstall", "--dry-run", "--json", "fixture-apt")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "plan" and doc["action"] == "uninstall"
    validate(doc)
    assert_golden("uninstall-dry-run", doc, paths)
    _rc, text = _run(capsys, "uninstall", "--dry-run", "fixture-apt")
    assert_text_values_in_json(text, doc, render_removal_view, cli.cmd_uninstall)
````

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_install.py -q -k text_is_unchanged`
Expected: `2 passed`; `install-dry-run.txt` reads exactly:

```
Target: Debian GNU/Linux 13 (trixie) (ID=debian, version=13, arch=x86_64)

Packages (1):
  fixture-apt                  will install       [requested]
      + fixture-apt

Records:
  transaction log written to <tmp>/xdg_state_home/hammunition/transactions.jsonl

Commands (2):
  # Refresh apt package lists
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get update
  # Install 1 package(s) with apt
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-remove -- fixture-apt

Afterwards: the Hammunition menu is re-applied for this user (per-user files, unprivileged, D-050).

Dry run: nothing above was executed.
```

and `uninstall-dry-run.txt` reads exactly:

```
Target: Debian GNU/Linux 13 (trixie) (ID=debian, version=13, arch=x86_64)

Removing (1 unit(s)):
  fixture-apt                  - fixture-apt

Removing artifacts (1):
  fixture-source               binary         /usr/local/bin/fixture-source  [log]

Left in place — present, but the transaction log does not attribute it:
  fixture-source               /usr/local/share/fixture-source/extra

Left in place — installed, but not installed by Hammunition:
  fixture-station              libfixture1

Already absent:
  fixture-source               (nothing resolves here)

Not reversed, by design: dependencies apt pulled in (run `sudo apt autoremove` to clear orphans), group memberships, and any config files written — all recorded in the transaction log (D-004).

Commands (2):
  # Remove 1 package(s) with apt
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get remove --yes -- fixture-apt
  # Remove fixture-source's installed binary (log)
  $ rm -f -- /usr/local/bin/fixture-source

Dry run: nothing above was executed.
```

- [ ] **Step 4: Run the rest to verify they fail**

Run: `.venv/bin/pytest tests/test_json_install.py -q`
Expected: the two text tests PASS; `test_the_install_plan_document`, `test_the_uninstall_plan_document`, `test_a_refused_plan_...` FAIL (`kind` is `error`: no JSON form); `test_a_real_install_is_never_driven_through_json` FAILS on the message (it says "has no --json form", not "never driven through --json").

- [ ] **Step 5: Write the plan module**

`src/hammunition/interface/plan.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The plan as data: what ``install`` and ``uninstall`` will do.  D-059.

:func:`build_install_view` turns a resolved :class:`~hammunition.plan.InstallPlan`
and its steps into an :class:`InstallPlanView`; :func:`render_plan_view` prints
it, byte for byte what ``render_plan`` printed before the view existed (the
golden text test holds that); ``install --dry-run --json`` emits it inside a
:class:`PlanDocument`. The removal side is the same shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from hammunition.backends import Action
from hammunition.backends.data import human_size
from hammunition.consent import repo_env_var
from hammunition.execute import Step
from hammunition.interface.envelope import Strict, TargetView, described
from hammunition.interface.text import wrap
from hammunition.manifest.schema import (
    AptInstall,
    BinaryInstall,
    DataInstall,
    GitInstall,
    NodeInstall,
    SourceInstall,
    VenvInstall,
)
from hammunition.plan import Blocker, InstallPlan, PlannedPackage
from hammunition.state import RemovalPlan

__all__ = [
    "PlanDocument",
    "build_install_view",
    "build_removal_view",
    "plan_state",
    "refused_plan",
    "render_plan_view",
    "render_removal_view",
]

NOT_REVERSED = (
    "Not reversed, by design: dependencies apt pulled in (run "
    "`sudo apt autoremove` to clear orphans), group memberships, and any "
    "config files written — all recorded in the transaction log (D-004)."
)


def plan_state(planned: PlannedPackage, built: frozenset[str] = frozenset()) -> str:
    """What the plan will do to this unit, in two words.

    "already installed" is apt's answer and only apt's: it means every apt
    package the block names is present. A source or binary unit's apt list is
    its build dependencies, or nothing at all, so for those it was saying
    "already installed" one line above a build -- sdrangel's .deb block on
    the Ubuntu 26.04 VM read that way (2026-09-02). The one carve-out is a
    vendor .deb the plan has attributed to this engine and dpkg still holds
    (#63): nothing is planned for it, and the line says so.
    """
    method = planned.block.install
    if isinstance(method, AptInstall):
        return "already installed" if not planned.outstanding else "will install"
    if isinstance(method, BinaryInstall) and planned.deb_installed:
        return "already installed"
    if planned.name in built:
        return "already installed"  # built at this pin, D-051
    if isinstance(method, SourceInstall | GitInstall):
        return "will build"
    if isinstance(method, VenvInstall):
        return "will install"  # into its own venv, reported by the venv step
    if isinstance(method, NodeInstall):
        return "will build"
    return "will fetch+install"


@dataclass(frozen=True)
class AptLine(Strict):
    """One apt package a unit resolves to."""

    package: str = described("the apt package name")
    outstanding: bool = described("not installed yet; `+` in the text, `=` when already present")
    build_only: bool = described("a build dependency, not the software asked for")


@dataclass(frozen=True)
class PackageLine(Strict):
    """One catalog unit in the plan."""

    name: str = described("the catalog unit")
    method: str = described("the install method of the block that resolved here")
    state: str = described(
        "`will install`, `will build`, `will fetch+install` or `already installed`"
    )
    requested_by: tuple[str, ...] = described(
        "`requested`, or the profiles and units that pulled it in"
    )
    apt: tuple[AptLine, ...] = described(
        "the apt packages it resolves to, build dependencies included"
    )


@dataclass(frozen=True)
class DisplacedLine(Strict):
    """An installed distribution package a unit displaces or shadows (D-022)."""

    package: str = described("the distribution package, which stays installed")
    declared_by: str = described("the unit whose manifest declares the conflict")


@dataclass(frozen=True)
class ReleaseSection(Strict):
    """apt packages taken from another release this machine installs from (D-038)."""

    release: str = described("the `--target-release` the apt step runs with")
    packages: tuple[str, ...] = described("the packages that come from that release")


@dataclass(frozen=True)
class NoRecommendsSection(Strict):
    """apt packages installed by a second command without Recommends (D-052)."""

    units: tuple[str, ...] = described("the units whose manifests asked for it")
    packages: tuple[str, ...] = described("the packages that second command installs")


@dataclass(frozen=True)
class RepoLine(Strict):
    """A third-party apt repository the transaction adds, behind its own gate (D-040)."""

    name: str = described("the repository's name, which names its two files")
    unit: str = described("the unit that needs it")
    packages: tuple[str, ...] = described("the apt packages it is expected to supply")
    uri: str = described("the archive URI")
    suites: tuple[str, ...] = described("apt suites")
    components: tuple[str, ...] = described("apt components")
    key_fingerprint: str = described("the pinned signing-key fingerprint")
    sources: str = described("the .sources file written")
    keyring: str = described("the keyring file written")
    consent_env_var: str = described("must equal the key fingerprint for a scripted run")


@dataclass(frozen=True)
class DataArtifactLine(Strict):
    """One file of an offline dataset."""

    url: str = described("where it is fetched from")
    size: int = described("bytes, as declared and verified on fetch")
    size_human: str = described("the size as the text prints it")


@dataclass(frozen=True)
class DataLine(Strict):
    """An offline-data unit: sizes and licence, before anything downloads (D-049)."""

    unit: str = described("the data unit")
    total_size: int = described("bytes, every artifact together")
    total_human: str = described("the total as the text prints it")
    licence: str = described("the licence the data is under")
    licence_url: str = described("where that licence is stated")
    artifacts: tuple[DataArtifactLine, ...] = described("each file fetched")
    installs_under: str = described("where it is installed, relative to the prefix")


@dataclass(frozen=True)
class MembershipLine(Strict):
    """A group the operator is added to, and what it grants."""

    user: str = described("the account added")
    group: str = described("the group")
    package: str = described("the unit that needs it")
    detail: str = described("what membership grants")
    reverse_hint: str | None = described("how to undo it by hand, when the manifest says")


@dataclass(frozen=True)
class GateLine(Strict):
    """A consent gate the real run will present (D-021). Never answered through JSON."""

    profile: str = described("the gated profile")
    env_var: str = described("the scripted-consent variable the gate reads")
    risk_lines: tuple[str, ...] = described("one line per disclosed capability")


@dataclass(frozen=True)
class ConfigLine(Strict):
    """A configuration file the transaction writes."""

    unit: str = described("the unit whose manifest templates it")
    path: str = described("the file written")
    mode: str = described("its octal mode")
    append: bool = described("appended to rather than written")
    backup_existing: bool = described("an existing file is backed up first")


@dataclass(frozen=True)
class DeferralLine(Strict):
    """Part of the request that will not happen; the rest still does (D-035, D-039)."""

    kind: str = described("`config` (a file not written) or `package` (a member not installed)")
    subject: str = described("what is deferred")
    what: str = described("what will not happen")
    why: str = described("what is missing")
    remedy: str = described("what the operator can do about it")


@dataclass(frozen=True)
class RecordsLine(Strict):
    """Where the transaction log is written."""

    log: str = described("the transaction log file")
    handed_to: str | None = described("the operator it is chowned to, under sudo")


@dataclass(frozen=True)
class StepView(Strict):
    """One step, exactly as the real run performs it."""

    description: str = described("why the step runs")
    display: str = described("the line the text prints after `$`, copy-pasteable")
    argv: tuple[str, ...] = described(
        "the argv executed, escalation applied; empty for an in-process step"
    )
    action: str | None = described(
        "the in-process step's kind (`fetch`, `extract`, ...); null for a command"
    )
    requires_root: bool = described("whether it runs as root")


@dataclass(frozen=True)
class InstallPlanView(Strict):
    """Everything an install will do, section by section as the text prints it."""

    packages: tuple[PackageLine, ...] = described("every unit, in the order it installs")
    displaced: tuple[DisplacedLine, ...] = described("distribution packages displaced or shadowed")
    apt_release: ReleaseSection | None = described("present when apt resolves from another release")
    no_recommends: NoRecommendsSection | None = described(
        "present when a unit opted out of Recommends"
    )
    repos: tuple[RepoLine, ...] = described("third-party repositories added")
    data: tuple[DataLine, ...] = described("offline data downloaded")
    memberships: tuple[MembershipLine, ...] = described("group membership changes")
    consent_gates: tuple[GateLine, ...] = described("gates the real run presents")
    config_files: tuple[ConfigLine, ...] = described("configuration written")
    deferrals: tuple[DeferralLine, ...] = described("what will NOT happen")
    notes: tuple[str, ...] = described("the plan's notes")
    records: RecordsLine | None = described("where the transaction log goes")
    commands: tuple[StepView, ...] = described("every step, in order")
    suggestion_notes: tuple[str, ...] = described(
        "what happened to the profiles' suggestion groups; the text prints these as `note:` lines"
    )


@dataclass(frozen=True)
class UnitPackages(Strict):
    """A unit and apt packages."""

    unit: str = described("the catalog unit")
    packages: tuple[str, ...] = described("apt packages")


@dataclass(frozen=True)
class UnitFiles(Strict):
    """A unit and files."""

    unit: str = described("the catalog unit")
    paths: tuple[str, ...] = described("files on disk")


@dataclass(frozen=True)
class ArtifactLine(Strict):
    """A file or tree the removal deletes, and why it is this engine's to delete."""

    unit: str = described("the catalog unit")
    kind: str = described("`venv`, `tree`, `binary`, `wrapper`, `desktop-entry` or `apt-repo`")
    path: str = described("what is removed")
    basis: str = described("`namespaced`, `log` or `marker`: how it is known to be ours")


@dataclass(frozen=True)
class RemovalPlanView(Strict):
    """Everything an uninstall will do, section by section as the text prints it."""

    to_remove: tuple[UnitPackages, ...] = described("apt packages removed, per unit")
    artifacts: tuple[ArtifactLine, ...] = described("files and trees removed")
    left_unattributed: tuple[UnitFiles, ...] = described(
        "present, but the log does not attribute it"
    )
    left_foreign: tuple[UnitPackages, ...] = described("installed, but not by this engine")
    already_absent: tuple[UnitPackages, ...] = described("nothing to remove")
    not_reversed: str = described("what uninstall does not undo, by design (D-004)")
    commands: tuple[StepView, ...] = described("every step, in order")


@dataclass(frozen=True)
class BlockerLine(Strict):
    """One reason the transaction cannot be planned."""

    subject: str = described("what is blocked")
    reason: str = described("why")
    remedy: str | None = described("what to do about it")


@dataclass(frozen=True)
class PlanDocument(Strict):
    """The plan `install --dry-run` or `uninstall --dry-run` prints, as data.

    A refused transaction is still a `plan`, with `outcome: "refused"`, every
    blocker, and exit code 2. Includes the paths of files written for the
    operator; for local programs, not for pasting."""

    KIND: ClassVar[str] = "plan"

    action: str = described("`install` or `uninstall`")
    requested: tuple[str, ...] = described("the names given on the command line")
    outcome: str = described("`planned`, or `refused` with the blockers")
    target: TargetView = described("the system planned against")
    blockers: tuple[BlockerLine, ...] = described("empty unless refused")
    install: InstallPlanView | None = described(
        "the install plan; null for an uninstall or a refusal"
    )
    removal: RemovalPlanView | None = described(
        "the removal plan; null for an install or a refusal"
    )


def step_view(step: Step, *, euid: int) -> StepView:
    if isinstance(step, Action):
        return StepView(
            description=step.description,
            display=step.display(euid=euid),
            argv=(),
            action=step.kind,
            requires_root=step.requires_root,
        )
    return StepView(
        description=step.description,
        display=step.display(euid=euid),
        argv=tuple(step.argv_for(euid=euid)),
        action=None,
        requires_root=step.requires_root,
    )


def build_install_view(
    plan: InstallPlan,
    commands: Sequence[Step],
    *,
    euid: int,
    log_destination: Path | None = None,
    hands_log_to: str | None = None,
    built: frozenset[str] = frozenset(),
    suggestion_notes: Sequence[str] = (),
) -> InstallPlanView:
    data: list[DataLine] = []
    for planned in plan.packages:
        block = planned.block.install
        if not isinstance(block, DataInstall):
            continue
        total = sum(a.size for a in block.artifacts)
        data.append(
            DataLine(
                unit=planned.name,
                total_size=total,
                total_human=human_size(total),
                licence=block.licence.strip(),
                licence_url=block.licence_url,
                artifacts=tuple(
                    DataArtifactLine(url=a.url, size=a.size, size_human=human_size(a.size))
                    for a in block.artifacts
                ),
                installs_under=f"<prefix>/share/hammunition/data/{planned.name}/",
            )
        )
    return InstallPlanView(
        packages=tuple(
            PackageLine(
                name=p.name,
                method=p.block.install.method,
                state=plan_state(p, built),
                requested_by=tuple(p.requested_by),
                apt=tuple(
                    AptLine(package=a, outstanding=a in p.outstanding, build_only=a in p.build_only)
                    for a in p.apt_packages
                ),
            )
            for p in plan.packages
        ),
        displaced=tuple(
            DisplacedLine(package=c, declared_by=p.name) for p in plan.packages for c in p.displaces
        ),
        apt_release=(
            ReleaseSection(release=plan.apt_release, packages=tuple(plan.apt_from_release))
            if plan.apt_release is not None
            else None
        ),
        no_recommends=(
            NoRecommendsSection(
                units=plan.apt_no_recommends_units, packages=plan.apt_to_install_no_recommends
            )
            if plan.apt_to_install_no_recommends
            else None
        ),
        repos=tuple(
            RepoLine(
                name=a.repo.name,
                unit=a.unit,
                packages=tuple(a.packages),
                uri=a.repo.uri,
                suites=tuple(a.repo.suites),
                components=tuple(a.repo.components),
                key_fingerprint=a.repo.key_fingerprint,
                sources=a.sources,
                keyring=a.keyring,
                consent_env_var=repo_env_var(a.repo),
            )
            for a in plan.apt_repos
        ),
        data=tuple(data),
        memberships=tuple(
            MembershipLine(
                user=m.user,
                group=m.group,
                package=m.package,
                detail=m.detail,
                reverse_hint=m.reverse_hint.strip() if m.reverse_hint else None,
            )
            for m in plan.group_memberships
        ),
        consent_gates=tuple(
            GateLine(profile=name, env_var=gate.env_var, risk_lines=tuple(gate.risk_lines))
            for name, gate in plan.consent_gates
        ),
        config_files=tuple(
            ConfigLine(
                unit=unit,
                path=config.path,
                mode=config.mode,
                append=config.append,
                backup_existing=config.backup_existing,
            )
            for unit, config, _body in plan.config_files
        ),
        deferrals=tuple(
            DeferralLine(kind=d.kind, subject=d.subject, what=d.what, why=d.why, remedy=d.remedy)
            for d in plan.deferrals
        ),
        notes=tuple(plan.notes),
        records=(
            RecordsLine(log=str(log_destination), handed_to=hands_log_to)
            if log_destination is not None
            else None
        ),
        commands=tuple(step_view(c, euid=euid) for c in commands),
        suggestion_notes=tuple(suggestion_notes),
    )


def render_plan_view(view: InstallPlanView, *, target: TargetView) -> list[str]:
    """The complete account of what will happen, as the terminal shows it."""
    lines = [f"Target: {target.description}", ""]

    if view.packages:
        lines.append(f"Packages ({len(view.packages)}):")
        for package in view.packages:
            why = ", ".join(package.requested_by)
            lines.append(f"  {package.name:<28} {package.state:<18} [{why}]")
            for apt in package.apt:
                mark = "+" if apt.outstanding else "="
                note = "  (to build)" if apt.build_only else ""
                lines.append(f"      {mark} {apt.package}{note}")
        lines.append("")

    if view.displaced:
        lines.append("Installed distribution packages displaced or shadowed (D-022):")
        for displaced in view.displaced:
            lines.append(
                f"  {displaced.package}  — declared by {displaced.declared_by}; the distribution "
                f"package stays installed, see that manifest's notes"
            )
        lines.append("")

    if view.apt_release is not None:
        release = view.apt_release.release
        lines.append(f"apt packages resolved from {release} (D-038):")
        lines.extend(
            wrap(
                f"apt refused the default release because a package this machine "
                f"already installs from {release} would have been "
                f"downgraded; the apt step runs with --target-release "
                f"{release}, which takes these from there:",
                indent="  ",
            )
        )
        for apt_package in view.apt_release.packages:
            lines.append(f"      {apt_package}")
        lines.append("")

    if view.no_recommends is not None:
        units = ", ".join(view.no_recommends.units)
        lines.append("apt packages installed without Recommends (D-052):")
        lines.extend(
            wrap(
                f"{units} asked for --no-install-recommends in the manifest, because the "
                f"Recommends of these packages conflict with software this target installs; "
                f"a second apt-get install carries the flag for them alone. Everything else "
                f"in this transaction keeps apt's defaults, and both commands run with "
                f"--no-remove:",
                indent="  ",
            )
        )
        for apt_package in view.no_recommends.packages:
            lines.append(f"      {apt_package}")
        lines.append("")

    if view.repos:
        lines.append("Third-party apt repositories that will be added (D-040):")
        for repo in view.repos:
            lines.append(f"  {repo.name}  [{repo.unit}: {', '.join(repo.packages)}]")
            lines.append(f"      {repo.uri}  {' '.join(repo.suites)}  {' '.join(repo.components)}")
            lines.append(f"      key {repo.key_fingerprint}")
            lines.append(f"      writes {repo.sources}")
            lines.append(f"      writes {repo.keyring}")
            lines.append(f"      consent: {repo.consent_env_var} must equal the key fingerprint")
        lines.append("")

    if view.data:
        lines.append("Offline data that will be downloaded and installed (D-049):")
        for data in view.data:
            lines.append(f"  {data.unit:<28} {data.total_human} total, licence: {data.licence}")
            lines.append(f"      stated at {data.licence_url}")
            for artifact in data.artifacts:
                lines.append(f"      {artifact.size_human:>9}  {artifact.url}")
            lines.append(f"      installs under {data.installs_under}")
        lines.append("")

    if view.memberships:
        lines.append("Group membership changes:")
        for membership in view.memberships:
            lines.append(f"  {membership.user} → {membership.group}  ({membership.package})")
            lines.extend(wrap(membership.detail, indent="      "))
            if membership.reverse_hint is not None:
                lines.append(f"      reverse: {membership.reverse_hint}")
        lines.append("")

    if view.consent_gates:
        lines.append("Consent gates that will be presented:")
        for gate in view.consent_gates:
            lines.append(f"  {gate.profile} ({gate.env_var})")
            for risk in gate.risk_lines:
                wrapped = wrap(risk, indent="        ")
                lines.append("      - " + wrapped[0].strip())
                lines.extend(wrapped[1:])
        lines.append("")

    if view.config_files:
        lines.append("Configuration that will be written:")
        for config in view.config_files:
            backup = "existing file backed up" if config.backup_existing else "NOT backed up"
            verb = "appended to" if config.append else "written"
            lines.append(
                f"  {config.path}  ({verb}, mode {config.mode}, {backup})  [{config.unit}]"
            )
        lines.append("")

    if view.deferrals:
        # After the packages and before the notes: this is the part of the
        # request that will NOT happen, and burying it under a heading called
        # "notes" is how it stops being read. D-035.
        lines.append("Will NOT happen (the rest of the transaction still will):")
        for deferral in view.deferrals:
            lines.append(f"  {deferral.subject}: {deferral.what}")
            lines.extend(wrap(f"why: {deferral.why}", indent="      "))
            lines.extend(wrap(f"→ {deferral.remedy}", indent="      "))
        lines.append("")

    if view.notes:
        lines.append("Notes:")
        for note in view.notes:
            wrapped = wrap(note, indent="      ")
            lines.append("  - " + wrapped[0].strip())
            lines.extend(wrapped[1:])
        lines.append("")

    if view.records is not None:
        lines.append("Records:")
        lines.append(f"  transaction log written to {view.records.log}")
        if view.records.handed_to is not None:
            lines.append(
                f"  the log and any directories created for it are given to "
                f"{view.records.handed_to!r} (chown), since root is writing into their home"
            )
        lines.append("")

    lines.append(f"Commands ({len(view.commands)}):")
    if not view.commands:
        lines.append("  (none — everything this plan asks for is already in place)")
    for command in view.commands:
        lines.append(f"  # {command.description}")
        lines.append(f"  $ {command.display}")
    return lines


def build_removal_view(
    plan: RemovalPlan, commands: Sequence[Step], *, euid: int
) -> RemovalPlanView:
    def shown(mapping: dict[str, list[str]]) -> tuple[UnitPackages, ...]:
        # The text lists a unit here only when it has packages, or is not
        # also being removed; the view carries exactly what the text shows.
        return tuple(
            UnitPackages(unit=unit, packages=tuple(packages))
            for unit, packages in mapping.items()
            if packages or unit not in plan.to_remove
        )

    return RemovalPlanView(
        to_remove=tuple(
            UnitPackages(unit=unit, packages=tuple(packages))
            for unit, packages in plan.to_remove.items()
        ),
        artifacts=tuple(
            ArtifactLine(unit=unit, kind=r.kind, path=str(r.path), basis=r.basis)
            for unit, removals in plan.artifacts.items()
            for r in removals
        ),
        left_unattributed=tuple(
            UnitFiles(unit=unit, paths=tuple(paths))
            for unit, paths in plan.left_unattributed.items()
        ),
        left_foreign=shown(plan.left_foreign),
        already_absent=shown(plan.already_absent),
        not_reversed=NOT_REVERSED,
        commands=tuple(step_view(c, euid=euid) for c in commands),
    )


def render_removal_view(view: RemovalPlanView, *, target: TargetView) -> list[str]:
    """What an uninstall will do, as the terminal shows it, up to the commands."""
    lines = [f"Target: {target.description}", ""]
    if view.to_remove:
        lines.append(f"Removing ({len(view.to_remove)} unit(s)):")
        for removal in view.to_remove:
            lines.append(f"  {removal.unit:28} - {' '.join(removal.packages)}")
    if view.artifacts:
        lines += ["", f"Removing artifacts ({len(view.artifacts)}):"]
        for artifact in view.artifacts:
            lines.append(
                f"  {artifact.unit:28} {artifact.kind:14} {artifact.path}  [{artifact.basis}]"
            )
    if view.left_unattributed:
        lines += ["", "Left in place — present, but the transaction log does not attribute it:"]
        for files in view.left_unattributed:
            for path in files.paths:
                lines.append(f"  {files.unit:28} {path}")
    for label, shown in (
        ("Left in place — installed, but not installed by Hammunition:", view.left_foreign),
        ("Already absent:", view.already_absent),
    ):
        if shown:
            lines += ["", label]
            for entry in shown:
                packages = " ".join(entry.packages) or "(nothing resolves here)"
                lines.append(f"  {entry.unit:28} {packages}")
    lines += ["", view.not_reversed]
    if view.commands:
        lines += ["", f"Commands ({len(view.commands)}):"]
        for command in view.commands:
            lines.append(f"  # {command.description}")
            lines.append(f"  $ {command.display}")
    else:
        lines += ["", "Nothing to do: none of this is installed, or none of it was ours."]
    return lines


def refused_plan(
    action: str, requested: Sequence[str], target: TargetView, blockers: Sequence[Blocker]
) -> PlanDocument:
    return PlanDocument(
        action=action,
        requested=tuple(requested),
        outcome="refused",
        target=target,
        blockers=tuple(
            BlockerLine(subject=b.subject, reason=b.reason, remedy=b.remedy) for b in blockers
        ),
        install=None,
        removal=None,
    )
````

- [ ] **Step 6: Make `render_plan` a wrapper over the view**

Replace everything from `def _plan_state(` (line 185) to the end of `render_plan` (line 401) with:

````python
def render_plan(
    plan: InstallPlan,
    commands: Sequence[Step],
    *,
    euid: int,
    log_destination: Path | None = None,
    hands_log_to: str | None = None,
    built: frozenset[str] = frozenset(),
) -> list[str]:
    """The complete account of what will happen. Printed for every run.

    Not only for ``--dry-run``. An operator who is about to say yes should be
    reading the same text the dry run would have shown them, because a
    disclosure that appears only when you ask for it is one most people never
    see.

    ``log_destination`` and ``hands_log_to`` disclose the transaction log — a
    file written to the machine, and under ``sudo`` a file (and the directories
    on the way to it) chowned to the operator. CLAUDE.md: nothing happens to a
    machine that is not written down, before it happens.

    Rendered from :class:`hammunition.interface.plan.InstallPlanView`, the same
    object ``install --dry-run --json`` emits (D-059), so the two cannot drift.
    """
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import build_install_view, render_plan_view

    view = build_install_view(
        plan,
        commands,
        euid=euid,
        log_destination=log_destination,
        hands_log_to=hands_log_to,
        built=built,
    )
    return render_plan_view(view, target=target_view(plan.target))
````

Run: `.venv/bin/ruff check --fix src/hammunition/cli/main.py`
Expected: `Found 9 errors (9 fixed, 0 remaining).` — the imports only the old body used: `human_size`, `repo_env_var`, `DataInstall`, `GitInstall`, `NodeInstall`, `SourceInstall`, `VenvInstall`, `PlannedPackage`, and the `_wrap` alias Task 1 added.

Run: `.venv/bin/pytest tests/test_json_plan.py tests/test_cli.py -q`
Expected: all passed, `plan-install-text.txt` byte-identical (`git diff --stat tests/fixtures` empty).

- [ ] **Step 7: Emit the plan from `cmd_install`**

Put the decorator and local imports at the top of `cmd_install`:

````python
@envelope.json_capable(dry_run_only=True)
def cmd_install(args: argparse.Namespace) -> int:
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import (
        PlanDocument,
        build_install_view,
        refused_plan,
        render_plan_view,
    )

    try:
        target = Target.detect()
````

In its `except PlanError as exc:` block, after the two `print(..., file=sys.stderr)` calls and before `return EXIT_UNPLANNABLE`, add:

````python
        if envelope.wanted(args):
            envelope.emit(refused_plan("install", args.names, target_view(target), exc.blockers))
````

Replace this block (lines 1019-1029):

````python
    for note in suggestion_notes:
        print(f"note: {note}")
    for line in render_plan(
        plan,
        commands,
        euid=euid,
        built=built,
        log_destination=log_destination,
        hands_log_to=hands_log_to,
    ):
        print(line)
````

with:

````python
    view = build_install_view(
        plan,
        commands,
        euid=euid,
        built=built,
        log_destination=log_destination,
        hands_log_to=hands_log_to,
        suggestion_notes=suggestion_notes,
    )
    if envelope.wanted(args):
        # Reached only with --dry-run: main() refuses a real install under
        # --json before this command runs (D-059).
        envelope.emit(
            PlanDocument(
                action="install",
                requested=tuple(args.names),
                outcome="planned",
                target=target_view(target),
                blockers=(),
                install=view,
                removal=None,
            )
        )
        return EXIT_OK
    for note in suggestion_notes:
        print(f"note: {note}")
    for line in render_plan_view(view, target=target_view(plan.target)):
        print(line)
````

- [ ] **Step 8: Emit the plan from `cmd_uninstall`**

Put the decorator and local imports at the top of `cmd_uninstall`:

````python
@envelope.json_capable(dry_run_only=True)
def cmd_uninstall(args: argparse.Namespace) -> int:
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import (
        BlockerLine,
        PlanDocument,
        build_removal_view,
        render_removal_view,
    )

    try:
        target = Target.detect()
````

In `except RemovalError as exc:`, before `return EXIT_UNPLANNABLE`, add:

````python
        if envelope.wanted(args):
            envelope.emit(
                PlanDocument(
                    action="uninstall",
                    requested=tuple(args.names),
                    outcome="refused",
                    target=target_view(target),
                    blockers=(BlockerLine(subject="uninstall", reason=str(exc), remedy=None),),
                    install=None,
                    removal=None,
                )
            )
````

Replace everything from `    print(f"Target: {target.describe()}\n")` (line 1265) through `        return EXIT_OK` after `print("\nNothing to do: ...")` (line 1302) with:

````python
    view = build_removal_view(plan, commands, euid=euid)
    if envelope.wanted(args):
        # Reached only with --dry-run (D-059).
        envelope.emit(
            PlanDocument(
                action="uninstall",
                requested=tuple(args.names),
                outcome="planned",
                target=target_view(target),
                blockers=(),
                install=None,
                removal=view,
            )
        )
        return EXIT_OK
    for line in render_removal_view(view, target=target_view(target)):
        print(line)
    if not commands:
        return EXIT_OK

````

The `if args.dry_run:` block that follows is unchanged.

- [ ] **Step 9: Create the JSON goldens, then run everything**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_install.py -q -k document` then `.venv/bin/pytest tests/test_json_install.py tests/test_json_plan.py tests/test_cli.py tests/test_uninstall.py -q`
Expected: first `2 passed`, two `.json` written (read them: `install.commands[1].argv` starts `["sudo", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install"`); second all passed, and `git diff --stat tests/fixtures` shows no `.txt` changed since Steps 2-3.

- [ ] **Step 10: Regenerate the page, run the gates, commit**

Run: `.venv/bin/python scripts/gen_json_reference.py && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q`
Expected: as Task 2 Step 7.

```bash
git add src/hammunition/interface/plan.py src/hammunition/cli/main.py tests/test_json_plan.py \
  tests/test_json_install.py tests/fixtures/json/plan-* tests/fixtures/json/install-* \
  tests/fixtures/json/uninstall-* docs/reference/json-interface.md
git commit -m "$(cat <<'EOF'
install/uninstall --dry-run --json: the plan as data (D-059)

render_plan and the uninstall report now render from InstallPlanView and
RemovalPlanView, the objects the plan document carries; goldens captured
before the move hold the text byte for byte. A refused plan is a plan
document with every blocker. Without --dry-run, --json is refused before
resolution: a real install is never driven through JSON.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `station show --json` and `hardware state --json`

**Files:**
- Create: `src/hammunition/interface/station.py`, `src/hammunition/interface/hardware.py`, `tests/test_json_station_hardware.py`
- Create (generated by the tests): `tests/fixtures/json/station-{none,set}.{txt,json}`, `tests/fixtures/json/hardware-{one,none}.{txt,json}`
- Modify: `src/hammunition/cli/main.py:552-575` (`cmd_station_show`), `2155-2170` (`cmd_hardware_state`)
- Modify: `tests/test_cli.py:1493-1521` (`test_hardware_state_needs_no_privilege_and_prints_a_table`)
- Regenerate: `docs/reference/json-interface.md`

**Interfaces:**
- Consumes: Task 1's envelope and helpers; `hammunition.station` (`Station`, `STATION_FIELDS`, `config_path`, `save_station`); `hammunition.hardware.power.Parkable`; `hammunition.cli.devctl._state`/`_survey` (read only, in a test).
- Produces: `hammunition.interface.station`: `StationDocument` (`KIND = "station"`: `path, file_exists, callsign, grid_square, node_alias`), `build_station(path, station)`, `render_station(doc)`. `hammunition.interface.hardware`: `HardwareDocument` (`KIND = "hardware"`: `devices, skipped`), `DeviceView` (`name, summary, address, identifier, method, parked, kept, attached`), `SkippedView`, `build_hardware(found, skipped)`, `render_hardware(doc)`.

`DeviceView` carries every key the privileged helper's `state` array prints today plus `kept` and `attached`, the two #119 adds to it, so Task 10 only fills them in. On `main`, `kept` is always `false` (nothing on main can keep a device parked across a reboot) and `attached` always `true` (every device listed was found on the bus).

- [ ] **Step 1: Write the tests**

`tests/test_json_station_hardware.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``station show --json`` and ``hardware state --json``.  D-059."""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path

import pytest

from hammunition.hardware.power import Parkable
from hammunition.interface.station import StationDocument
from hammunition.station import STATION_FIELDS, Station, save_station
from json_support import (
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

GPS = Parkable(
    name="gps-receiver",
    summary="USB GNSS receivers",
    method="usb_deauthorize",
    quiet=(),
    sysfs_path="/sys/bus/usb/devices/1-4",
    identifier="1234:5678",
    parked=True,
)


def _station(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    station: Station | None,
    *flags: str,
) -> tuple[int, str]:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "op")
    if station is not None:
        save_station(station, path=tmp_path / "hammunition" / "station.yml")
    rc = cli.main(["station", "show", *flags])
    return rc, capsys.readouterr().out.replace(str(tmp_path), "<config>")


STATIONS = {
    "station-none": None,
    "station-set": Station(callsign="N0TST", grid_square="FN31pr"),
}


@pytest.mark.parametrize("name", sorted(STATIONS))
def test_station_text_is_unchanged(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _station(monkeypatch, tmp_path, capsys, STATIONS[name])
    assert rc == 0
    assert_golden_text(name, out)


@pytest.mark.parametrize("name", sorted(STATIONS))
def test_station_document_matches_its_golden_and_its_schema(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _station(monkeypatch, tmp_path, capsys, STATIONS[name], "--json")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "station"
    validate(doc)
    assert_golden(name, doc, {str(tmp_path): "<config>"})


@pytest.mark.parametrize("name", sorted(STATIONS))
def test_station_text_values_are_in_the_json(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.station import render_station

    _rc, text = _station(monkeypatch, tmp_path, capsys, STATIONS[name])
    _rc, out = _station(monkeypatch, tmp_path, capsys, STATIONS[name], "--json")
    assert_text_values_in_json(text, parse_one(out), render_station)


def test_every_station_field_is_in_the_document() -> None:
    """When a station field is added (map regions, D-057) the document must
    carry it, or the form a front end fills from it silently lacks one."""
    carried = {f.name for f in dataclasses.fields(StationDocument)}
    assert set(STATION_FIELDS) <= carried, sorted(set(STATION_FIELDS) - carried)


def _hardware(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    found: list[Parkable],
    *flags: str,
) -> tuple[int, str]:
    skipped = [("fixture-radio", "its port has no power control")]
    monkeypatch.setattr(cli, "_survey_parkables", lambda args: (found, skipped))
    rc = cli.main(["hardware", "state", *flags])
    return rc, capsys.readouterr().out


HARDWARE = {"hardware-one": [GPS], "hardware-none": []}


@pytest.mark.parametrize("name", sorted(HARDWARE))
def test_hardware_text_is_unchanged(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _hardware(monkeypatch, capsys, HARDWARE[name])
    assert rc == 0
    assert_golden_text(name, out)


@pytest.mark.parametrize("name", sorted(HARDWARE))
def test_hardware_document_matches_its_golden_and_its_schema(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.hardware import render_hardware

    rc, out = _hardware(monkeypatch, capsys, HARDWARE[name], "--json")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "hardware"
    validate(doc)
    assert_golden(name, doc)
    _rc, text = _hardware(monkeypatch, capsys, HARDWARE[name])
    assert_text_values_in_json(text, doc, render_hardware)


def test_a_device_carries_every_key_the_helper_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    """The helper's `state` array is what the tray reads; a front end reading
    the CLI must get the same keys, so either can be the source."""
    import io
    import json
    from contextlib import redirect_stdout

    devctl = importlib.import_module("hammunition.cli.devctl")
    from hammunition.interface.hardware import build_hardware

    buf = io.StringIO()
    monkeypatch.setattr(devctl, "_survey", lambda: ([GPS], []))
    with redirect_stdout(buf):
        devctl._state()
    helper_keys = set(json.loads(buf.getvalue())[0])
    ours = set(dataclasses.asdict(build_hardware([GPS], []))["devices"][0])
    assert helper_keys <= ours, sorted(helper_keys - ours)
````

- [ ] **Step 2: Capture the text goldens from the code as it is now**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_station_hardware.py -q -k text_is_unchanged`
Expected: `4 passed`. `station-set.txt` reads exactly:

```
Station configuration: <config>/hammunition/station.yml

  callsign       N0TST
  grid_square    FN31pr
  node_alias     (not set)
```

and `hardware-one.txt` reads exactly:

```
  fixture-radio: not parkable right now — its port has no power control
device                   address    state    summary
gps-receiver             1-4        parked   USB GNSS receivers

`hammunition hardware park NAME` / `wake NAME`. A reboot wakes everything.
```

- [ ] **Step 3: Run the rest to verify they fail**

Run: `.venv/bin/pytest tests/test_json_station_hardware.py -q`
Expected: text tests PASS; document tests FAIL (`kind` is `error`); the field and helper-key tests error with `No module named 'hammunition.interface.station'`.

- [ ] **Step 4: Write the two modules**

`src/hammunition/interface/station.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``station show`` as data.  D-059."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from hammunition.interface.envelope import Strict, described
from hammunition.station import STATION_FIELDS, Station

__all__ = ["StationDocument", "build_station", "render_station"]


@dataclass(frozen=True)
class StationDocument(Strict):
    """The saved station values, the values themselves included.

    For a local front end filling in a form. Not for pasting into an issue,
    a forum or a chat: a callsign resolves to a name and a licence address,
    and a grid square to where the station is."""

    KIND: ClassVar[str] = "station"

    path: str = described("the station file")
    file_exists: bool = described("whether that file exists yet")
    callsign: str | None = described("the callsign; null when not set")
    grid_square: str | None = described("the Maidenhead locator; null when not set")
    node_alias: str | None = described("the packet node alias; null when not set")


def build_station(path: Path, station: Station) -> StationDocument:
    return StationDocument(
        path=str(path),
        file_exists=path.exists(),
        callsign=station.callsign,
        grid_square=station.grid_square,
        node_alias=station.node_alias,
    )


def render_station(doc: StationDocument) -> list[str]:
    """``station show`` as the terminal shows it."""
    lines = [f"Station configuration: {doc.path}"]
    if not doc.file_exists:
        lines.append("  (no file yet)")
    values = {name: getattr(doc, name) for name in sorted(STATION_FIELDS)}
    if not any(values.values()):
        return [
            *lines,
            "",
            "Nothing set. `hammunition station set --callsign <yours>` starts it off.",
            "Nothing is invented on your behalf: a configuration file needing a value",
            "you have not given is reported as not written, and the package still installs.",
        ]
    lines.append("")
    lines += [f"  {name:<14} {value if value else '(not set)'}" for name, value in values.items()]
    return lines
````

`src/hammunition/interface/hardware.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hardware state`` as data.  D-059, D-056.

Each device carries the same keys the privileged helper's ``state`` array
does (name, summary, address, identifier, method, parked), plus ``kept`` and
``attached`` -- the two the kept-off work adds to the helper -- so a front
end reading either source reads one shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hammunition.interface.envelope import Strict, described

if TYPE_CHECKING:
    from hammunition.hardware.power import Parkable

__all__ = ["HardwareDocument", "build_hardware", "render_hardware"]


@dataclass(frozen=True)
class DeviceView(Strict):
    """A catalogued, parkable device."""

    name: str = described("the catalog entry")
    summary: str = described("one line")
    address: str = described("the USB bus address, e.g. `1-4`: what tells two of a kind apart")
    identifier: str = described("`vendor:product` as the bus reported it")
    method: str = described("how it is parked, e.g. `usb_deauthorize`")
    parked: bool = described("parked now")
    kept: bool = described(
        "kept parked across reboots; always false until an engine that can keep one"
    )
    attached: bool = described("plugged in now; a kept entry may name a device that is not")


@dataclass(frozen=True)
class SkippedView(Strict):
    """A catalogued device that is attached but cannot be parked right now."""

    unit: str = described("the catalog entry")
    why: str = described("why not")


@dataclass(frozen=True)
class HardwareDocument(Strict):
    """Which catalogued devices can be parked, and which are parked now.

    Read fresh from sysfs on every call, unprivileged."""

    KIND: ClassVar[str] = "hardware"

    devices: tuple[DeviceView, ...] = described("by name, then address")
    skipped: tuple[SkippedView, ...] = described("attached but not parkable right now")


def build_hardware(
    found: Sequence[Parkable], skipped: Sequence[tuple[str, str]]
) -> HardwareDocument:
    return HardwareDocument(
        devices=tuple(
            DeviceView(
                name=p.name,
                summary=p.summary,
                address=p.address,
                identifier=p.identifier,
                method=str(p.method),
                parked=p.parked,
                kept=False,
                attached=True,
            )
            for p in sorted(found, key=lambda p: (p.name, p.address))
        ),
        skipped=tuple(SkippedView(unit=unit, why=why) for unit, why in skipped),
    )


def render_hardware(doc: HardwareDocument) -> list[str]:
    """``hardware state`` as the terminal shows it."""
    lines = [f"  {s.unit}: not parkable right now — {s.why}" for s in doc.skipped]
    if not doc.devices:
        lines.append(
            "No parkable device is attached. A device is parkable when its catalog "
            "entry carries a power_control block and it is plugged in now."
        )
        return lines
    lines.append(f"{'device':24} {'address':10} {'state':8} summary")
    for d in doc.devices:
        lines.append(
            f"{d.name:24} {d.address:10} {'parked' if d.parked else 'awake':8} {d.summary}"
        )
    lines += ["", "`hammunition hardware park NAME` / `wake NAME`. A reboot wakes everything."]
    return lines
````

- [ ] **Step 5: Route the two commands through them**

Replace `cmd_station_show` (lines 552-575) with:

````python
@envelope.json_capable()
def cmd_station_show(args: argparse.Namespace) -> int:
    """What is saved, and where. Says plainly when nothing is."""
    from hammunition.interface.station import build_station, render_station

    user = operator(args)
    try:
        station = load_station(owner=user)
    except StationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    doc = build_station(config_path(user), station)
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_station(doc):
        print(line)
    return EXIT_OK
````

Replace `cmd_hardware_state` (lines 2155-2170) with:

````python
@envelope.json_capable()
def cmd_hardware_state(args: argparse.Namespace) -> int:
    """Which catalogued devices can be parked, and which are parked now."""
    from hammunition.interface.hardware import build_hardware, render_hardware

    found, skipped = _survey_parkables(args)
    doc = build_hardware(found, skipped)
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_hardware(doc):
        print(line)
    return EXIT_OK
````

`tests/test_cli.py::test_hardware_state_needs_no_privilege_and_prints_a_table` stubs a device with only four attributes, and the document reads all six. Replace that test (lines 1493-1521) with:

````python
def test_hardware_state_needs_no_privilege_and_prints_a_table(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataclasses
    import importlib

    cli = importlib.import_module("hammunition.cli.main")

    # A real Parkable, not a duck-typed stub: `hardware state` builds its
    # document (D-059) from every field the helper reports.
    parked = dataclasses.replace(_gps_receiver(), parked=True)
    monkeypatch.setattr(cli, "_survey_parkables", lambda args: ([parked], []))
    assert cli.main(["hardware", "state"]) == 0
    out = capsys.readouterr().out
    assert "gps-receiver" in out and "parked" in out.lower()
````

- [ ] **Step 6: Create the JSON goldens, then run everything**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_station_hardware.py -q -k document_matches` then `.venv/bin/pytest tests/test_json_station_hardware.py tests/test_cli.py tests/test_station.py tests/test_devctl.py -q`
Expected: first `4 passed`; `station-set.json` carries `"callsign": "N0TST"` and `"grid_square": "FN31pr"` (placeholders, by the fixture). Second: all passed.

- [ ] **Step 7: Regenerate the page, run the gates, commit**

Run: `.venv/bin/python scripts/gen_json_reference.py && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q`
Expected: as Task 2 Step 7. Then confirm `grep -n "not for pasting\|Not for pasting" docs/reference/json-interface.md` prints the station section's line.

```bash
git add src/hammunition/interface/station.py src/hammunition/interface/hardware.py \
  src/hammunition/cli/main.py tests/test_json_station_hardware.py tests/test_cli.py \
  tests/fixtures/json/station-* tests/fixtures/json/hardware-* docs/reference/json-interface.md
git commit -m "$(cat <<'EOF'
station show --json and hardware state --json (D-059)

The station document carries the values, for a local front end, and its
reference entry says it is not for pasting. A hardware device carries every
key the helper's state array does, plus kept and attached. Text unchanged,
held by goldens.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `update --json`

**Files:**
- Create: `src/hammunition/interface/update.py`, `tests/test_json_update.py`
- Create (generated by the tests): `tests/fixtures/json/update.{txt,json}`
- Modify: `src/hammunition/update.py:271-319` (`render`: extract `upgrade_command`, `rebuild_command`)
- Modify: `src/hammunition/cli/main.py:630-768` (`cmd_update`, `_upstream_report` → `_upstream_rows`), `src/hammunition/cli/main.py:127-128` (`if TYPE_CHECKING:` block)
- Regenerate: `docs/reference/json-interface.md`

**Interfaces:**
- Consumes: Task 1's envelope and helpers; `hammunition.update` (`UpdateReport`, `report`, `render`, the state constants); `hammunition.upstream.UpstreamRow` (`unit, method, catalog, upstream, state, detail`).
- Produces: `hammunition.update.upgrade_command(report) -> str | None`, `hammunition.update.rebuild_command(report) -> str | None`; `hammunition.interface.update.UpdateDocument` (`KIND = "update"`), `build_update(target, report, *, lists_note, from_log, upstream) -> UpdateDocument`; `cli.main._upstream_rows(plan, runner) -> list[UpstreamRow]` (replaces `_upstream_report`).

`UpdateReport` is already a dataclass and the text keeps rendering from it (`update.render`); the document is built from the same instance. Rows carry exactly what text rows carry, so the count-only rule for anything that says where the operator is (the `osm-regions` row #121 adds) holds in the document without a special case; Task 9 adds the test for that row.

- [ ] **Step 1: Write the tests**

`tests/test_json_update.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``update --json``.  D-059, D-053."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from hammunition.backends.apt import AptBackend, AptPackageState, AptSimulation
from hammunition.distro import Target
from hammunition.station import Station, save_station
from hammunition.upstream import UpstreamRow
from json_support import (
    FIXTURE_CATALOG,
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13")
LISTS = "last refreshed 2026-09-28 08:00 EDT (`sudo apt-get update` refreshes them; this report does not)"


def _machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A target, apt lists and a probe that need no real machine: fixture-apt
    is installed at 1.0 with 1.1 as the candidate; nothing is built."""
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setattr(AptBackend, "lists_populated", lambda self: True)
    monkeypatch.setattr(
        AptBackend,
        "probe",
        lambda self, pkgs: {
            p: AptPackageState(name=p, installed="1.0", candidate="1.1") for p in pkgs
        },
    )
    monkeypatch.setattr(
        AptBackend,
        "simulate",
        lambda self, pkgs, *, release=None, no_recommends=False: AptSimulation(
            ok=True, installs={p: frozenset({"stable"}) for p in pkgs}, release=release
        ),
    )
    monkeypatch.setattr(cli, "_apt_lists_note", lambda apt: LISTS)


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), "update", *argv])
    return rc, capsys.readouterr().out


def test_the_text_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "fixture-apt", "fixture-source")
    assert rc == 0
    assert_golden_text("update", out)


def test_the_document_matches_its_golden_and_its_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.update import render

    _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "fixture-apt", "fixture-source", "--json")
    doc = parse_one(out)
    assert rc == 0 and doc["kind"] == "update"
    validate(doc)
    assert_golden("update", doc)
    assert doc["upgrade_command"].endswith("-- fixture-apt")
    _rc, text = _run(capsys, "fixture-apt", "fixture-source")
    assert_text_values_in_json(text, doc, render, cli.cmd_update)


def test_nothing_to_compare_is_still_a_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _machine(monkeypatch, tmp_path)
    rc, out = _run(capsys, "--json")
    doc = parse_one(out)
    assert rc == 0 and doc["rows"] == [] and doc["from_log"] is True
    validate(doc)


def test_upstream_rows_are_carried_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _machine(monkeypatch, tmp_path)
    row = UpstreamRow(
        unit="fixture-source",
        method="github_tags",
        catalog="2.1",
        upstream="2.2",
        state="behind upstream",
        detail="2.2 tagged upstream",
    )
    monkeypatch.setattr(cli, "probe_upstream", lambda manifest, **kwargs: row)
    _rc, out = _run(capsys, "fixture-source", "--upstream", "--json")
    doc = parse_one(out)
    validate(doc)
    assert doc["upstream"][0]["upstream"] == "2.2"


def test_the_station_values_never_reach_the_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """update output is pasteable; it keeps the text's rule of saying nothing
    about where the operator is."""
    _machine(monkeypatch, tmp_path)
    save_station(
        Station(callsign="N0TST", grid_square="FN31pr"),
        path=tmp_path / "config" / "hammunition" / "station.yml",
    )
    _rc, out = _run(capsys, "fixture-apt", "fixture-source", "--json")
    assert "N0TST" not in out and "FN31pr" not in out
````

- [ ] **Step 2: Capture the text golden from the code as it is now**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_update.py -q -k text_is_unchanged`
Expected: `1 passed`; `tests/fixtures/json/update.txt` reads exactly:

```
Target: Debian GNU/Linux 13 (ID=debian, version=13, arch=x86_64)
Units (2):
  fixture-apt     candidate differs      fixture-apt 1.0 -> 1.1
  fixture-source  unknown                declares no binaries and no tree marker, so nothing on disk can be checked

0 up to date, 1 with a different apt candidate, 0 behind the catalog's pin, 0 not installed, 1 unknown, 0 re-checked on install, 0 manual.
apt lists: last refreshed 2026-09-28 08:00 EDT (`sudo apt-get update` refreshes them; this report does not)

To take apt's candidates (upgrade only, never a removal; apt decides the rest):
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --only-upgrade --no-remove -- fixture-apt

Nothing above was executed.
```

- [ ] **Step 3: Run the rest to verify they fail**

Run: `.venv/bin/pytest tests/test_json_update.py -q`
Expected: the text test PASSES; the others FAIL (`kind` is `error`) or error on `No module named 'hammunition.interface.update'`.

- [ ] **Step 4: Extract the two commands in `update.py`**

Insert before `def render(`:

````python
def upgrade_command(report: UpdateReport) -> str | None:
    """The command that takes apt's differing candidates, or None when none differ."""
    if not report.upgradable:
        return None
    return (
        "sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --only-upgrade "
        f"--no-remove -- {' '.join(report.upgradable)}"
    )


def rebuild_command(report: UpdateReport) -> str | None:
    """The command that rebuilds every unit behind the pin, or None."""
    return f"hammunition install {' '.join(report.behind)}" if report.behind else None
````

In `render`, replace the `if report.upgradable:` and `if report.behind:` blocks with:

````python
    upgrade = upgrade_command(report)
    if upgrade is not None:
        out.append("")
        out.append(
            "To take apt's candidates (upgrade only, never a removal; apt decides the rest):"
        )
        out.append(f"  $ {upgrade}")
    rebuild = rebuild_command(report)
    if rebuild is not None:
        out.append("")
        out.append("To rebuild at the catalog's pin:")
        out.append(f"  $ {rebuild}")
````

Run: `.venv/bin/pytest tests/test_update.py tests/test_json_update.py -q -k "not document and not nothing and not upstream and not station"`
Expected: all passed (the text is unchanged).

- [ ] **Step 5: Write the update module**

`src/hammunition/interface/update.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``update`` as data.  D-059, D-053.

The report is already a dataclass (:class:`hammunition.update.UpdateReport`),
and the text keeps rendering from it; this document is built from the same
instance. Rows carry what the text rows carry and no more, so the count-only
rule the text follows for anything that says where the operator is holds here
too.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from hammunition.distro import Target
from hammunition.interface.envelope import Strict, TargetView, described, target_view
from hammunition.update import (
    BEHIND_PIN,
    CANDIDATE_DIFFERS,
    MANUAL,
    NOT_INSTALLED,
    ON_INSTALL,
    UNKNOWN,
    UP_TO_DATE,
    UpdateReport,
    rebuild_command,
    upgrade_command,
)
from hammunition.upstream import UpstreamRow

__all__ = ["UpdateDocument", "build_update"]


@dataclass(frozen=True)
class UpdateRowView(Strict):
    """One unit: installed versus the catalog."""

    unit: str = described("the catalog unit")
    state: str = described(
        "`up to date`, `candidate differs`, `behind the pin`, `not installed`, `unknown`, "
        "`re-checked on install` or `manual`"
    )
    detail: str = described("what was compared, as the text prints it")
    strategy: str = described("the manifest's update strategy")
    upgradable: tuple[str, ...] = described("apt packages whose candidate differs")


@dataclass(frozen=True)
class UpdateCounts(Strict):
    """How many rows are in each state."""

    up_to_date: int = described("up to date")
    candidate_differs: int = described("apt would change them on its next upgrade")
    behind_pin: int = described("built at an earlier pin, or never verified here")
    not_installed: int = described("not on this machine")
    unknown: int = described("nothing on disk can be checked")
    on_install: int = described("resolved again on every install")
    manual: int = described("re-pinned by hand")


@dataclass(frozen=True)
class UpstreamRowView(Strict):
    """The catalog's pin against what upstream publishes (`--upstream` only)."""

    unit: str = described("the catalog unit")
    method: str = described("the probe used")
    catalog: str = described("the catalog's pin")
    upstream: str | None = described("what upstream publishes; null when it could not be read")
    state: str = described("the verdict")
    detail: str = described("what was found")


@dataclass(frozen=True)
class UpdateDocument(Strict):
    """Installed versus the catalog, as a report. Nothing runs (D-053)."""

    KIND: ClassVar[str] = "update"

    target: TargetView = described("the system")
    from_log: bool = described("the units compared are every unit the transaction log names")
    rows: tuple[UpdateRowView, ...] = described("one per unit compared")
    counts: UpdateCounts = described("rows per state")
    lists_note: str = described("how old the local apt lists are; the report compares against them")
    upgrade_command: str | None = described("takes apt's differing candidates; null when none")
    rebuild_command: str | None = described("rebuilds every unit behind the pin; null when none")
    upstream_declared: tuple[str, ...] = described("units whose probe would ask upstream")
    upstream: tuple[UpstreamRowView, ...] | None = described(
        "the upstream comparison; null unless `--upstream` asked for it"
    )


def build_update(
    target: Target,
    report: UpdateReport,
    *,
    lists_note: str,
    from_log: bool,
    upstream: Sequence[UpstreamRow] | None,
) -> UpdateDocument:
    return UpdateDocument(
        target=target_view(target),
        from_log=from_log,
        rows=tuple(
            UpdateRowView(
                unit=r.unit,
                state=r.state,
                detail=r.detail,
                strategy=r.strategy,
                upgradable=tuple(r.upgradable),
            )
            for r in report.rows
        ),
        counts=UpdateCounts(
            up_to_date=report.count(UP_TO_DATE),
            candidate_differs=report.count(CANDIDATE_DIFFERS),
            behind_pin=report.count(BEHIND_PIN),
            not_installed=report.count(NOT_INSTALLED),
            unknown=report.count(UNKNOWN),
            on_install=report.count(ON_INSTALL),
            manual=report.count(MANUAL),
        ),
        lists_note=lists_note,
        upgrade_command=upgrade_command(report),
        rebuild_command=rebuild_command(report),
        upstream_declared=tuple(report.upstream_declared),
        upstream=tuple(
            UpstreamRowView(
                unit=r.unit,
                method=r.method,
                catalog=r.catalog,
                upstream=r.upstream,
                state=r.state,
                detail=r.detail,
            )
            for r in upstream
        )
        if upstream is not None
        else None,
    )
````

- [ ] **Step 6: Route `cmd_update` through it**

In the `if TYPE_CHECKING:` block (line 127), add the second line:

````python
if TYPE_CHECKING:
    from hammunition.hardware.power import Parkable
    from hammunition.upstream import UpstreamRow
````

Replace `cmd_update` and `_upstream_report` (lines 630-768) with:

````python
@envelope.json_capable()
def cmd_update(args: argparse.Namespace) -> int:
    """Installed versus the catalog, as a report. D-053: nothing runs."""
    from hammunition.interface.update import build_update

    try:
        target = Target.detect()
    except DetectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    if not target.is_debian_family:
        print(f"error: {target.describe()} is not Debian-family.", file=sys.stderr)
        return EXIT_FAILED

    catalog_root = find_catalog(args.catalog)
    packages, profiles = load_all(catalog_root)
    runner = SubprocessRunner()
    apt = AptBackend(runner)
    user = operator(args)
    read_log = TransactionLog(owner=user or None)

    names = list(dict.fromkeys(args.names))
    from_log = not names
    if not names:
        names = list(requested_units(read_log.read()))
        if not names:
            if envelope.wanted(args):
                envelope.emit(
                    build_update(
                        target,
                        report(
                            InstallPlan(target=target, packages=()),
                            apt_states={},
                            present={},
                            built=(),
                        ),
                        lists_note=_apt_lists_note(apt),
                        from_log=True,
                        upstream=None,
                    )
                )
                return EXIT_OK
            print(f"Target: {target.describe()}")
            print(
                "Nothing to compare: the transaction log records no install request here "
                f"({read_log.path}). Name units or profiles to compare them anyway."
            )
            return EXIT_OK
        print(f"Comparing the {len(names)} unit(s) the transaction log has ever named here.")

    try:
        station = load_station(owner=user)
    except StationError:
        station = Station()
    repos = AptRepoBackend(owner=user or None)
    try:
        plan = resolve(
            names,
            catalog=packages,
            profiles=profiles,
            target=target,
            apt=apt,
            user=user,
            station=station,
            repos=repos,
            kernel=KernelProbe.detect(),
            log=read_log,
        )
    except PlanError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "\nNothing was compared. The report resolves the request the way install "
            "would, so a blocker here is the same blocker install would meet.",
            file=sys.stderr,
        )
        return EXIT_UNPLANNABLE
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    builds = build_root(user or None)
    source = SourceBackend(Fetcher(owner=user or None), build_root=builds, owner=user or None)
    git = GitBackend(
        runner=runner,
        build_root=builds,
        prefix=source.prefix,
        jobs=source.jobs,
        owner=source.owner,
    )
    binary = BinaryBackend(
        fetcher=source.fetcher,
        runner=runner,
        build_root=builds,
        prefix=source.prefix,
        owner=source.owner,
    )
    built = already_built(
        plan, log=read_log, prefix=source.prefix, source=source, git=git, binary=binary
    )
    present = {
        planned.name: build_effects_present(planned, prefix=source.prefix)
        for planned in plan.packages
        if build_dir(planned, source=source, git=git, binary=binary) is not None
    }
    apt_names: list[str] = []
    for planned in plan.packages:
        method = planned.block.install
        if isinstance(method, AptInstall):
            apt_names.extend(method.packages)
    try:
        states = apt.probe(list(dict.fromkeys(apt_names)))
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED

    result = report(plan, apt_states=states, present=present, built=built)
    lists_note = _apt_lists_note(apt)
    upstream = _upstream_rows(plan, runner) if args.upstream else None
    if envelope.wanted(args):
        envelope.emit(
            build_update(
                target, result, lists_note=lists_note, from_log=from_log, upstream=upstream
            )
        )
        return EXIT_OK
    print(f"Target: {target.describe()}")
    print(render(result, lists_note=lists_note, upstream_asked=bool(args.upstream)))
    if upstream is not None:
        print()
        print(render_upstream(upstream))
    return EXIT_OK


def _upstream_rows(plan: InstallPlan, runner: SubprocessRunner) -> list[UpstreamRow]:
    """D-053's second half: the catalog's pin against what upstream publishes.

    Opt-in because it is the one thing the engine does that talks to someone
    else's server. A GITHUB_TOKEN in the environment is sent to GitHub's API
    only, for the rate limit; tags come from `git ls-remote`, which needs no
    token on any host.
    """
    token = os.environ.get("GITHUB_TOKEN") or None

    def http(url: str) -> str:
        return http_get(url, token=token)

    def ls_remote(url: str) -> list[str]:
        result = runner.run(
            Command(
                argv=("git", "ls-remote", "--tags", "--refs", "--", url),
                description=f"List the tags at {url}",
                requires_root=False,
            )
        )
        if not result.ok:
            raise BackendError(f"git ls-remote exited {result.returncode}: {result.stderr.strip()}")
        return parse_ls_remote(result.stdout)

    rows = [
        probe_upstream(planned.manifest, http=http, ls_remote=ls_remote)
        for planned in plan.packages
    ]
    return [r for r in rows if r.state != NOT_UPSTREAM]
````

- [ ] **Step 7: Create the JSON golden, then run everything**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_update.py -q -k document_matches` then `.venv/bin/pytest tests/test_json_update.py tests/test_update.py tests/test_upstream.py tests/test_cli.py -q`
Expected: first `1 passed`; second all passed, `update.txt` unchanged.

- [ ] **Step 8: Regenerate the page, run the gates, commit**

Run: `.venv/bin/python scripts/gen_json_reference.py && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q`
Expected: as Task 2 Step 7.

```bash
git add src/hammunition/interface/update.py src/hammunition/update.py src/hammunition/cli/main.py \
  tests/test_json_update.py tests/fixtures/json/update.* docs/reference/json-interface.md
git commit -m "$(cat <<'EOF'
update --json: installed versus the catalog, as data (D-059, D-053)

Built from the same UpdateReport the text renders; rows carry what the
text rows carry and no more. Upstream rows appear only with --upstream.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `doctor --json`

**Files:**
- Create: `src/hammunition/interface/doctor.py`, `tests/test_json_doctor.py`
- Create (generated by the tests): `tests/fixtures/json/doctor-{ready,warn,blocking}.{txt,json}`
- Modify: `src/hammunition/cli/main.py:2259-2362` (`cmd_doctor`: decorator, the import line, the output block)
- Regenerate: `docs/reference/json-interface.md`

**Interfaces:**
- Consumes: Task 1's envelope and helpers; `hammunition.doctor.Check`, `summarize`, `run_checks` (patched in tests as `hammunition.doctor.run_checks`, which works because `cmd_doctor` imports it at call time).
- Produces: `hammunition.interface.doctor.DoctorDocument` (`KIND = "doctor"`: `checks, fails, warns, healthy`), `CheckView`, `build_doctor(checks) -> DoctorDocument`, `render_doctor(doc) -> list[str]`, `GLYPH`.

- [ ] **Step 1: Write the tests**

`tests/test_json_doctor.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``doctor --json``.  D-059."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from hammunition import doctor
from hammunition.distro import Target
from hammunition.doctor import Check
from hammunition.station import Station, save_station
from json_support import (
    FIXTURE_CATALOG,
    assert_golden,
    assert_golden_text,
    assert_text_values_in_json,
    parse_one,
    validate,
)

cli = importlib.import_module("hammunition.cli.main")

TARGET = Target(distro="debian", version="13", arch="x86_64", pretty_name="Debian GNU/Linux 13")

CHECKS = {
    "doctor-ready": [
        Check("system", "ok", "Debian GNU/Linux 13"),
        Check("udev rules", "info", "udev rules not yet applied", "hammunition hardware apply"),
    ],
    "doctor-warn": [
        Check("system", "ok", "Debian GNU/Linux 13"),
        Check("compiler", "warn", "no C compiler found", "sudo apt install build-essential"),
    ],
    "doctor-blocking": [
        Check("catalog", "fail", "the catalog could not be found or loaded", "pass --catalog"),
    ],
}


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    checks: list[Check],
    *flags: str,
) -> tuple[int, str]:
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setattr(doctor, "run_checks", lambda **kwargs: checks)
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), "doctor", *flags])
    return rc, capsys.readouterr().out


@pytest.mark.parametrize("name", sorted(CHECKS))
def test_the_text_is_unchanged(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _rc, out = _run(monkeypatch, capsys, CHECKS[name])
    assert_golden_text(name, out)


@pytest.mark.parametrize("name", sorted(CHECKS))
def test_the_document_matches_its_golden_schema_and_exit_code(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.doctor import render_doctor

    text_rc, text = _run(monkeypatch, capsys, CHECKS[name])
    rc, out = _run(monkeypatch, capsys, CHECKS[name], "--json")
    assert rc == text_rc, "--json changed the exit code"
    doc = parse_one(out)
    validate(doc)
    assert_golden(name, doc)
    assert_text_values_in_json(text, doc, render_doctor)


def test_the_station_values_never_reach_the_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Count-only, as the text: doctor output is what people paste."""
    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    save_station(
        Station(callsign="N0TST", grid_square="FN31pr"),
        path=tmp_path / "hammunition" / "station.yml",
    )
    cli.main(["--catalog", str(FIXTURE_CATALOG), "doctor", "--json"])
    out = capsys.readouterr().out
    doc: dict[str, Any] = parse_one(out)
    assert doc["kind"] == "doctor"
    assert "N0TST" not in out and "FN31pr" not in out
````

- [ ] **Step 2: Capture the text goldens from the code as it is now**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_doctor.py -q -k text_is_unchanged`
Expected: `3 passed`; `doctor-warn.txt` reads exactly:

```
Hammunition health check

  [✓] system         Debian GNU/Linux 13
  [!] compiler       no C compiler found
      → sudo apt install build-essential

1 ok, 1 to look at, 0 blocking.
The engine works; the items marked ! limit what you can install until fixed.
```

- [ ] **Step 3: Run the rest to verify they fail**

Run: `.venv/bin/pytest tests/test_json_doctor.py -q`
Expected: text tests PASS; the document tests FAIL (`kind` is `error`, or `No module named 'hammunition.interface.doctor'`); the station test FAILS on `doc["kind"] == "doctor"`.

- [ ] **Step 4: Write the doctor module**

`src/hammunition/interface/doctor.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``doctor`` as data.  D-059.

The checks themselves are :func:`hammunition.doctor.run_checks`, a pure
function; this is the document and the text, both read from its result.
Like the text, the document says whether a station is set, never its values.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from hammunition.doctor import Check, summarize
from hammunition.interface.envelope import Strict, described

__all__ = ["DoctorDocument", "build_doctor", "render_doctor"]

GLYPH = {"ok": "✓", "warn": "!", "fail": "✗", "info": "·"}


@dataclass(frozen=True)
class CheckView(Strict):
    """One thing looked at, its verdict, and how to fix it."""

    name: str = described("the check")
    status: str = described("`ok`, `info`, `warn` (limits what installs) or `fail` (blocking)")
    detail: str = described("what was found")
    fix: str | None = described("the one command or step that fixes it")


@dataclass(frozen=True)
class DoctorDocument(Strict):
    """The read-only health check: is this machine ready? Exit 1 when blocking."""

    KIND: ClassVar[str] = "doctor"

    checks: tuple[CheckView, ...] = described("in the order a person should read them")
    fails: int = described("blocking")
    warns: int = described("to look at")
    healthy: int = described("ok or info")


def build_doctor(checks: Sequence[Check]) -> DoctorDocument:
    fails, warns, healthy = summarize(list(checks))
    return DoctorDocument(
        checks=tuple(
            CheckView(name=c.name, status=c.status, detail=c.detail, fix=c.fix) for c in checks
        ),
        fails=fails,
        warns=warns,
        healthy=healthy,
    )


def render_doctor(doc: DoctorDocument) -> list[str]:
    """``doctor`` as the terminal shows it."""
    lines = ["Hammunition health check", ""]
    for check in doc.checks:
        lines.append(f"  [{GLYPH[check.status]}] {check.name:14} {check.detail}")
        if check.fix and check.status in ("fail", "warn"):
            lines.append(f"      → {check.fix}")
    lines += ["", f"{doc.healthy} ok, {doc.warns} to look at, {doc.fails} blocking."]
    if doc.fails:
        lines.append("Fix the blocking items above before installing.")
    elif doc.warns:
        lines.append("The engine works; the items marked ! limit what you can install until fixed.")
    else:
        lines.append("Ready.")
    return lines
````

- [ ] **Step 5: Route `cmd_doctor` through it**

Add `@envelope.json_capable()` on the line above `def cmd_doctor`. Change its import line `from hammunition.doctor import run_checks, summarize, writable_or_creatable` to `from hammunition.doctor import run_checks, writable_or_creatable`. Replace everything from `    glyph = {"ok": "✓", ...}` to the function's final `return EXIT_OK` with:

````python
    from hammunition.interface.doctor import build_doctor, render_doctor

    doc = build_doctor(checks)
    if envelope.wanted(args):
        envelope.emit(doc)
    else:
        for line in render_doctor(doc):
            print(line)
    return EXIT_FAILED if doc.fails else EXIT_OK
````

- [ ] **Step 6: Create the JSON goldens, then run everything**

Run: `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_doctor.py -q -k document_matches` then `.venv/bin/pytest tests/test_json_doctor.py tests/test_doctor.py tests/test_cli.py -q`
Expected: first `3 passed`; second all passed, `doctor-*.txt` unchanged. `doctor-blocking` exits 1 in both forms (asserted).

- [ ] **Step 7: Regenerate the page, run the gates, commit**

Run: `.venv/bin/python scripts/gen_json_reference.py && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q`
Expected: as Task 2 Step 7.

```bash
git add src/hammunition/interface/doctor.py src/hammunition/cli/main.py tests/test_json_doctor.py \
  tests/fixtures/json/doctor-* docs/reference/json-interface.md
git commit -m "$(cat <<'EOF'
doctor --json: each check as data, exit code kept (D-059)

Text and document render from one DoctorDocument; a test pins that no
station value reaches it, the rule the text already follows.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `hammunition` on the PATH, and `doctor` checks it

**Files:**
- Create: `scripts/path-link.sh`, `tests/test_path_link.py`
- Modify: `bootstrap.sh:106-123` (section 4 and the closing text)
- Modify: `src/hammunition/doctor.py` (`run_checks` signature and one new check after `PATH`), `tests/test_doctor.py` (`HEALTHY`, three new tests)
- Modify: `src/hammunition/cli/main.py` (`cmd_doctor`: compute and pass the two new inputs)
- Modify: `docs/reference/cli.md:364` ("Twelve checks" → "Thirteen checks")

**Interfaces:**
- Consumes: Task 7's `cmd_doctor` (this task edits the same function; it must start after Task 7 merges).
- Produces: `run_checks(..., engine_on_path: str | None, engine_expected: str)` — two new required keyword arguments; a check named `hammunition` (`ok` / `warn`). `scripts/path-link.sh CHECKOUT` — exit 0 when `~/.local/bin/hammunition` points at `CHECKOUT/.venv/bin/hammunition`, 1 otherwise, 2 on usage.

A link to **another** checkout is left alone and the switch printed, rather than re-pointed: two worktrees (this one and `/home/chiefgyk3d/src/Hammunition`) must not fight over the PATH each time one is bootstrapped. The only link replaced is one of ours whose target is gone.

- [ ] **Step 1: Write the failing tests**

`tests/test_path_link.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``scripts/path-link.sh``: `hammunition` on the PATH, and nothing clobbered.  D-059.

Run against a fake checkout and a scratch $HOME, never the real one.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "path-link.sh"


def _checkout(root: Path) -> Path:
    entry = root / ".venv" / "bin" / "hammunition"
    entry.parent.mkdir(parents=True)
    entry.write_text("#!/bin/sh\n")
    entry.chmod(0o755)
    return root


def _run(checkout: Path, home: Path, *, on_path: bool = True) -> subprocess.CompletedProcess[str]:
    path = f"{home / '.local' / 'bin'}:/usr/bin:/bin" if on_path else "/usr/bin:/bin"
    return subprocess.run(
        ["bash", str(SCRIPT), str(checkout)],
        env={"HOME": str(home), "PATH": path},
        capture_output=True,
        text=True,
        check=False,
    )


def test_it_creates_the_link_and_the_directory(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    result = _run(checkout, home)
    link = home / ".local" / "bin" / "hammunition"
    assert result.returncode == 0, result.stderr
    assert link.is_symlink()
    assert os.readlink(link) == str(checkout.resolve() / ".venv" / "bin" / "hammunition")


def test_it_is_idempotent(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    _run(checkout, home)
    again = _run(checkout, home)
    assert again.returncode == 0 and "already points at this checkout" in again.stdout


def test_it_refuses_to_replace_a_file_it_did_not_create(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    foreign = home / ".local" / "bin" / "hammunition"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("#!/bin/sh\necho someone else's\n")
    result = _run(checkout, home)
    assert result.returncode == 1
    assert "not a link this script created" in result.stderr
    assert foreign.read_text() == "#!/bin/sh\necho someone else's\n"


def test_it_refuses_to_repoint_a_foreign_symlink(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    link = home / ".local" / "bin" / "hammunition"
    link.parent.mkdir(parents=True)
    link.symlink_to("/usr/bin/true")
    result = _run(checkout, home)
    assert result.returncode == 1 and os.readlink(link) == "/usr/bin/true"


def test_another_checkouts_link_is_left_and_the_switch_is_printed(tmp_path: Path) -> None:
    first = _checkout(tmp_path / "Hammunition")
    second = _checkout(tmp_path / "Hammunition-json")
    home = tmp_path / "home"
    _run(first, home)
    result = _run(second, home)
    link = home / ".local" / "bin" / "hammunition"
    assert result.returncode == 1
    assert os.readlink(link) == str(first.resolve() / ".venv" / "bin" / "hammunition")
    assert "ln -sfn" in result.stderr


def test_a_dangling_link_of_ours_is_replaced(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    home = tmp_path / "home"
    link = home / ".local" / "bin" / "hammunition"
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path / "deleted-checkout" / ".venv" / "bin" / "hammunition")
    result = _run(checkout, home)
    assert result.returncode == 0, result.stderr
    assert os.readlink(link) == str(checkout.resolve() / ".venv" / "bin" / "hammunition")


def test_a_path_without_local_bin_gets_the_line_to_add(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path / "Hammunition")
    result = _run(checkout, tmp_path / "home", on_path=False)
    assert result.returncode == 0
    assert 'export PATH="$HOME/.local/bin:$PATH"' in result.stderr


def test_bootstrap_calls_it() -> None:
    assert 'scripts/path-link.sh" "$here"' in (REPO_ROOT / "bootstrap.sh").read_text()
````

In `tests/test_doctor.py`, add two keys at the end of `HEALTHY`:

````python
    "engine_on_path": "/home/op/Hammunition/.venv/bin/hammunition",
    "engine_expected": "/home/op/Hammunition/.venv/bin/hammunition",
````

and append:

````python
def test_hammunition_missing_from_path_is_a_warn_naming_bootstrap() -> None:
    checks = run_checks(**{**HEALTHY, "engine_on_path": None})  # type: ignore[arg-type]
    check = _by_name(checks)["hammunition"]
    assert check.status == "warn"
    assert check.fix is not None and "bootstrap.sh" in check.fix


def test_hammunition_from_another_checkout_is_a_warn_with_the_switch() -> None:
    other = "/home/op/Hammunition-old/.venv/bin/hammunition"
    checks = run_checks(**{**HEALTHY, "engine_on_path": other})  # type: ignore[arg-type]
    check = _by_name(checks)["hammunition"]
    assert check.status == "warn" and other in check.detail
    assert check.fix == f"ln -sfn {HEALTHY['engine_expected']} ~/.local/bin/hammunition"


def test_hammunition_resolving_to_this_checkout_is_ok() -> None:
    assert _by_name(run_checks(**HEALTHY))["hammunition"].status == "ok"  # type: ignore[arg-type]
````

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_path_link.py tests/test_doctor.py -q`
Expected: every `test_path_link.py` test FAILS (`bash: scripts/path-link.sh: No such file or directory`, returncode 127); every `test_doctor.py` test FAILS with `TypeError: run_checks() got an unexpected keyword argument 'engine_on_path'`.

- [ ] **Step 3: Write the link script**

`scripts/path-link.sh` (then `chmod +x scripts/path-link.sh`):

````bash
#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Put `hammunition` on the PATH: ~/.local/bin/hammunition -> CHECKOUT/.venv/bin/hammunition.
#
#     scripts/path-link.sh CHECKOUT
#
# Called by bootstrap.sh (D-059); safe to run by hand. Idempotent. It never
# replaces anything it did not create: a file, or a symlink pointing anywhere
# but some checkout's .venv/bin/hammunition, is left alone and named. A link
# to ANOTHER checkout is also left alone -- two worktrees must not fight over
# the PATH -- and the one command that switches it is printed. The only link
# replaced is one of ours whose target is gone.
#
# Exit 0: the link points at this checkout. Exit 1: it does not; why is on stderr.
# Either way, a ~/.local/bin that is not on PATH is reported with the line to add.

set -euo pipefail

say()  { printf '==> %s\n' "$*"; }
warn() { printf '!   %s\n' "$*" >&2; }

[ $# -eq 1 ] || { warn "usage: $0 CHECKOUT"; exit 2; }
checkout="$(cd "$1" && pwd -P)"
want="$checkout/.venv/bin/hammunition"
bindir="$HOME/.local/bin"
link="$bindir/hammunition"
status=0

path_hint() {
  case ":${PATH:-}:" in
    *":$bindir:"*) ;;
    *)
      warn "$bindir is not on your PATH, so \`hammunition\` will not be found yet."
      warn "Add this line to ~/.profile, then log out and back in:"
      printf '    export PATH="$HOME/.local/bin:$PATH"\n' >&2
      ;;
  esac
}

if [ ! -x "$want" ]; then
  warn "$want does not exist or is not executable; run ./bootstrap.sh first."
  exit 1
fi

mkdir -p -- "$bindir"

if [ -L "$link" ]; then
  current="$(readlink -- "$link")"
  if [ "$current" = "$want" ]; then
    say "$link already points at this checkout"
  elif [[ "$current" == */.venv/bin/hammunition ]] && [ ! -e "$link" ]; then
    ln -sfn -- "$want" "$link"
    say "replaced $link, whose checkout ($current) is gone, with a link to $want"
  elif [[ "$current" == */.venv/bin/hammunition ]]; then
    warn "$link points at another checkout ($current); left as it is."
    warn "To use this checkout instead: ln -sfn '$want' '$link'"
    status=1
  else
    warn "$link is a symlink to $current, which this script did not create; left as it is."
    status=1
  fi
elif [ -e "$link" ]; then
  warn "$link exists and is not a link this script created; left as it is."
  status=1
else
  ln -s -- "$want" "$link"
  say "linked $link -> $want"
fi

path_hint
exit "$status"
````

Replace section 4 and the closing heredoc of `bootstrap.sh` (from `# --- 4. Show the operator where they stand` to the end) with:

````bash
# --- 4. Put `hammunition` on the PATH ---------------------------------------
#
# ~/.local/bin/hammunition -> this checkout's .venv/bin/hammunition, so every
# `hammunition ...` in the docs works as typed (D-059). Never replaces a file
# it did not create; a link to another checkout is left and the switch printed.

say "Linking ~/.local/bin/hammunition to this checkout"
"$here/scripts/path-link.sh" "$here" \
  || warn "hammunition is not linked onto the PATH from this checkout; the reason is above. .venv/bin/hammunition works meanwhile."

# --- 5. Show the operator where they stand ----------------------------------

say "Installed. Health check:"
echo
.venv/bin/hammunition doctor || true   # doctor's non-zero exit is a report, not a bootstrap failure

cat <<'NEXT'

Next:
  hammunition station set --callsign YOURCALL --grid-square AB12cd
  hammunition list profiles
  hammunition install station --dry-run
NEXT
````

- [ ] **Step 4: Add the check to `doctor`**

In `src/hammunition/doctor.py`, extend the `run_checks` signature:

````python
    log_dir_writable: bool,
    engine_on_path: str | None,
    engine_expected: str,
) -> list[Check]:
````

and insert, directly before `    if tools.get("cc", False):`:

````python
    # `hammunition` itself on the PATH, and resolving to this checkout (D-059).
    # Without it every short command in the docs says "command not found",
    # which is how the field laptop met it; with it pointing at a different
    # checkout, a fix made here is not the engine that runs.
    if engine_on_path == engine_expected:
        checks.append(Check("hammunition", "ok", f"on PATH: {engine_expected}"))
    elif engine_on_path is None:
        checks.append(
            Check(
                "hammunition",
                "warn",
                "`hammunition` is not on PATH — commands in the docs will say command not found",
                "re-run ./bootstrap.sh, which links ~/.local/bin/hammunition to this checkout",
            )
        )
    else:
        checks.append(
            Check(
                "hammunition",
                "warn",
                f"`hammunition` on PATH runs {engine_on_path}, not this checkout's {engine_expected}",
                f"ln -sfn {engine_expected} ~/.local/bin/hammunition",
            )
        )
````

In `cmd_doctor`, after `log_dir_writable = writable_or_creatable(log_dir)`, add:

````python
    # This checkout's entry point: src/hammunition/cli/main.py -> the checkout
    # root is three parents above the package. Resolved, so a ~/.local/bin
    # link to it compares equal (D-059).
    checkout = Path(__file__).resolve().parents[3]
    engine_expected = str((checkout / ".venv" / "bin" / "hammunition").resolve())
    found_engine = shutil.which("hammunition")
    engine_on_path = str(Path(found_engine).resolve()) if found_engine else None
````

and pass `engine_on_path=engine_on_path, engine_expected=engine_expected,` as the last two arguments of its `run_checks(...)` call. In `docs/reference/cli.md` line 364 change "Twelve checks" to "Thirteen checks".

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/test_path_link.py tests/test_doctor.py tests/test_json_doctor.py -q && bash -n bootstrap.sh`
Expected: all passed; `bash -n` prints nothing.

- [ ] **Step 6: Run it for real, in a scratch home**

Run:
```
HOME="$(mktemp -d)" PATH=/usr/bin:/bin scripts/path-link.sh "$PWD"; echo "exit $?"
```
Expected: `==> linked <tmp>/.local/bin/hammunition -> <this checkout>/.venv/bin/hammunition`, the `export PATH="$HOME/.local/bin:$PATH"` hint on stderr, `exit 0`. Never run it against the real `$HOME` from a test.

- [ ] **Step 7: Run the gates and commit**

Run: `.venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q && .venv/bin/python scripts/check_doc_links.py`
Expected: `All checks passed!`, `Success: no issues found`, all passed, `no broken internal references`.

```bash
git add scripts/path-link.sh tests/test_path_link.py bootstrap.sh src/hammunition/doctor.py \
  tests/test_doctor.py src/hammunition/cli/main.py docs/reference/cli.md
git commit -m "$(cat <<'EOF'
bootstrap links hammunition onto the PATH; doctor checks it (D-059)

~/.local/bin/hammunition -> this checkout's .venv/bin/hammunition,
idempotent, never replacing a file it did not create or another
checkout's link. doctor warns when hammunition is not on PATH or
resolves to a different checkout, naming the one command that fixes it.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: After #121 — `maps regions --json`, the plan's map section, the station's map fields

**Depends on:** PR #121 merged to `main`, and Tasks 3 to 7. Every name below is as on branch `navigation-maps` at `214b5c6`; re-read `src/hammunition/cli/main.py` (`render_plan`, `cmd_install`, `cmd_station_show`, `cmd_maps_regions`), `src/hammunition/backends/regions.py` (`MapDisclosure`, `KeptRegion`, `region_lines`, `ESTIMATE`, `bin_estimate`) and `src/hammunition/geofabrik.py` (`RegionFile`) on `main` before starting, and adjust the code below if a name moved.

**Files:**
- Create: `src/hammunition/interface/regions.py`, `tests/test_json_maps.py`
- Modify: `src/hammunition/interface/plan.py` (`plan_state`, `InstallPlanView`, `build_install_view`, `render_plan_view`), `src/hammunition/interface/station.py`, `src/hammunition/cli/main.py` (`render_plan`, `cmd_install`, `cmd_station_show`, `cmd_maps_regions`)
- Regenerate: `docs/reference/json-interface.md`

**Interfaces:**
- Consumes: `hammunition.backends.regions.MapDisclosure` (`fetch, current, kept, convert`), `KeptRegion` (`region, slug, snapshot, reason`), `ESTIMATE`, `bin_estimate(size) -> int`; `hammunition.geofabrik.RegionFile` (`region, snapshot, url, size, sha256, md5`, `.verified_by`, `.slug`); `RegionalDataInstall`, `DerivedDataInstall`.
- Produces: `hammunition.interface.regions.RegionsDocument` (`KIND = "regions"`: `filter: str | None`, `regions: tuple[str, ...]`); `InstallPlanView.maps: MapSectionView | None` and `InstallPlanView.region_notes: tuple[str, ...]` (two fields added: additive, no schema bump); `StationDocument.map_regions: tuple[str, ...]`, `StationDocument.map_freshness: str`; `build_install_view(..., maps: MapDisclosure | None = None, region_notes: Sequence[str] = ())`; `render_plan(..., maps: MapDisclosure | None = None)`.

**Resolving the merge.** If #121 merged after Task 4, its rebase kept Task 4's thin `render_plan` and the map block has nowhere to live; if it merged before, Task 4's rebase met #121's `render_plan`. Either way, resolve `render_plan` to Task 4's wrapper plus a `maps` parameter passed to `build_install_view`, and put the map block in `render_plan_view` as below. Resolve `cmd_station_show` to Task 5's version and put #121's two map lines in `render_station` as below.

- [ ] **Step 1: Capture the goldens from #121's own rendering, before moving anything**

Create a throwaway worktree at #121's merge commit, where `render_plan` still renders the map block itself: `git worktree add ../Hammunition-golden <#121 merge sha>`. In it, add this test file as `tests/test_json_maps_golden.py`, copy `tests/json_support.py` and `tests/fixtures/json/` from this branch, and run `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_maps_golden.py -q` (use this checkout's venv: `../Hammunition-json/.venv/bin/pytest`). Copy the two `.txt` files it writes back here, then `git worktree remove ../Hammunition-golden`.

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Goldens for the map section and station show, captured from #121's code."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from hammunition.backends.regions import KeptRegion, MapDisclosure
from hammunition.distro import Target
from hammunition.geofabrik import RegionFile
from hammunition.manifest.schema import PackageManifest
from hammunition.plan import InstallPlan, PlannedPackage
from hammunition.station import Station, save_station
from json_support import assert_golden_text

cli = importlib.import_module("hammunition.cli.main")

VERMONT = RegionFile(
    region="north-america/us/vermont",
    snapshot="260101",
    url="https://download.geofabrik.de/north-america/us/vermont-260101.osm.pbf",
    size=52_428_800,
    sha256="30cf6db1a2b495975a499b45f3e760758579b81c99157b2d52d699f0c46ff9a4",
    md5=None,
)
MAPS = MapDisclosure(
    fetch=(VERMONT,),
    current=(),
    kept=(
        KeptRegion(
            region="north-america/us/new-hampshire",
            slug="north-america-us-new-hampshire",
            snapshot="250101",
            reason="Geofabrik did not answer; the installed map stays as it is.",
        ),
    ),
    convert=(VERMONT,),
)


def maps_plan() -> InstallPlan:
    manifest = PackageManifest.model_validate(_osm_regions())
    return InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )


def _osm_regions() -> dict[str, object]:
    import yaml

    root = Path(__file__).resolve().parent.parent
    return dict(yaml.safe_load((root / "catalog" / "packages" / "osm-regions.yaml").read_text()))


def test_the_plan_map_section_text() -> None:
    lines = cli.render_plan(maps_plan(), [], euid=1000, maps=MAPS)
    assert_golden_text("plan-maps-text", "\n".join(lines) + "\n")


def test_station_show_with_regions_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    save_station(
        Station(callsign="N0TST", map_regions=("north-america/us/vermont",)),
        path=tmp_path / "hammunition" / "station.yml",
    )
    assert cli.main(["station", "show"]) == 0
    out = capsys.readouterr().out.replace(str(tmp_path), "<config>")
    assert_golden_text("station-maps", out)
````

Expected in the throwaway worktree: `2 passed`; `plan-maps-text.txt` contains `Map regions, from station config (D-057):` and the Vermont line; `station-maps.txt` contains `map regions    1 set` and no region name.

- [ ] **Step 2: Write the failing tests here**

Copy `tests/test_json_maps_golden.py` into this branch as `tests/test_json_maps.py` and append:

````python
def test_the_plan_map_section_is_in_the_document() -> None:
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import build_install_view, render_plan_view

    plan = maps_plan()
    view = build_install_view(plan, [], euid=1000, maps=MAPS)
    assert view.maps is not None
    assert view.maps.fetch[0].region == "north-america/us/vermont"
    assert view.maps.kept[0].reason.startswith("Geofabrik did not answer")
    text = "\n".join(render_plan_view(view, target=target_view(plan.target))) + "\n"
    assert text == (Path(__file__).parent / "fixtures" / "json" / "plan-maps-text.txt").read_text()


def test_station_json_carries_the_regions_the_text_only_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from json_support import parse_one, validate

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    save_station(
        Station(callsign="N0TST", map_regions=("north-america/us/vermont",)),
        path=tmp_path / "hammunition" / "station.yml",
    )
    cli.main(["station", "show", "--json"])
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["map_regions"] == ["north-america/us/vermont"]
    assert doc["map_freshness"] == "yearly"


def test_maps_regions_json_lists_the_filtered_regions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from json_support import parse_one, validate

    class Index:
        def text(self, url: str) -> str:
            return "{}"

    monkeypatch.setattr(cli, "UrllibProbe", Index)
    monkeypatch.setattr(
        cli,
        "region_ids",
        lambda index_json: ["north-america/us/vermont", "north-america/us/virginia", "europe"],
    )
    assert cli.main(["maps", "regions", "north-america/us/v", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["kind"] == "regions" and doc["filter"] == "north-america/us/v"
    assert doc["regions"] == ["north-america/us/vermont", "north-america/us/virginia"]


def test_update_and_doctor_json_never_name_a_region(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The count-only rule (D-057) in the documents people paste."""
    from test_json_update import _machine

    _machine(monkeypatch, tmp_path)
    save_station(
        Station(callsign="N0TST", map_regions=("north-america/us/vermont",)),
        path=tmp_path / "config" / "hammunition" / "station.yml",
    )
    for argv in (["update", "osm-regions", "--json"], ["doctor", "--json"]):
        cli.main(argv)
        out = capsys.readouterr().out
        assert "vermont" not in out, f"{argv[0]} --json named a region"
````

Delete `tests/test_json_maps_golden.py` from this branch if you copied it (the two capture tests now live in `tests/test_json_maps.py`).

Run: `.venv/bin/pytest tests/test_json_maps.py -q`
Expected: the two text tests FAIL (the map block is not in `render_plan_view` yet: no `Map regions` line) or PASS if the merge kept #121's block in `render_plan`; the four new tests FAIL (`build_install_view() got an unexpected keyword argument 'maps'`, `KeyError: 'map_regions'`, `kind == "error"`).

- [ ] **Step 3: Add the regions document**

`src/hammunition/interface/regions.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps regions`` as data.  D-059, D-057."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hammunition.interface.envelope import Strict, described

__all__ = ["RegionsDocument"]


@dataclass(frozen=True)
class RegionsDocument(Strict):
    """Geofabrik's region paths, filtered. Fetched from Geofabrik's index when
    this command runs, and only then; nothing here is the operator's."""

    KIND: ClassVar[str] = "regions"

    filter: str | None = described("the case-insensitive substring asked for; null for every region")
    regions: tuple[str, ...] = described("the matching region paths, in the index's order")
````

Replace the loop at the end of `cmd_maps_regions` and decorate it:

````python
@envelope.json_capable()
def cmd_maps_regions(args: argparse.Namespace) -> int:
    ...  # unchanged down to `needle = ...`
    needle = (args.filter or "").casefold()
    matched = tuple(region for region in ids if needle in region.casefold())
    if envelope.wanted(args):
        from hammunition.interface.regions import RegionsDocument

        envelope.emit(RegionsDocument(filter=args.filter, regions=matched))
        return EXIT_OK
    for region in matched:
        print(region)
    return EXIT_OK
````

- [ ] **Step 4: Add the map section to the plan view**

In `src/hammunition/interface/plan.py`, import `from hammunition.backends.regions import ESTIMATE, MapDisclosure, bin_estimate` and `DerivedDataInstall, RegionalDataInstall` from the schema; in `plan_state`, before the final `return "will fetch+install"`, add `if isinstance(method, DerivedDataInstall): return "will convert"`. Add the views:

````python
@dataclass(frozen=True)
class RegionLine(Strict):
    """One map region file."""

    region: str = described("the Geofabrik region path")
    snapshot: str = described("the dated snapshot")
    size: int = described("bytes")
    size_human: str = described("the size as the text prints it")
    verified_by: str = described("how the download is checked")
    nothing_to_do: bool = described("already installed and not being converted")


@dataclass(frozen=True)
class ConvertLine(Strict):
    """A region converted for Navit this run."""

    region: str = described("the Geofabrik region path")
    snapshot: str = described("the dated snapshot")
    estimate: int = described("bytes the converted map is estimated to take")
    estimate_human: str = described("that estimate as the text prints it")


@dataclass(frozen=True)
class KeptLine(Strict):
    """An installed region that could not be checked for a newer map; kept."""

    region: str = described("the Geofabrik region path")
    snapshot: str | None = described("the installed snapshot, when recorded")
    reason: str = described("why it could not be checked")


@dataclass(frozen=True)
class MapSectionView(Strict):
    """The station's map regions (D-057). Names where the operator is: local only."""

    fetch: tuple[RegionLine, ...] = described("downloaded and installed this run")
    current: tuple[RegionLine, ...] = described("already installed at the resolved snapshot")
    convert: tuple[ConvertLine, ...] = described("converted for Navit this run")
    kept: tuple[KeptLine, ...] = described("could not be checked; the installed copy stays")
    licence: str = described("the map data's licence")
    licence_url: str = described("where it is stated")
    download_total: int = described("bytes downloaded")
    download_total_human: str = described("as the text prints it")
    disk_total_human: str = described("download plus converted maps, as the text prints it")
    estimate_note: str = described("how the conversion estimate was measured")
````

Add to `InstallPlanView`, after `data`:

````python
    maps: MapSectionView | None = described("the station's map regions; null when none apply")
````

and after `suggestion_notes`:

````python
    region_notes: tuple[str, ...] = described("notes from resolving the map regions")
````

Give `build_install_view` two parameters, `maps: MapDisclosure | None = None, region_notes: Sequence[str] = ()`, pass `region_notes=tuple(region_notes)`, and build the section:

````python
def _map_section(plan: InstallPlan, maps: MapDisclosure | None) -> MapSectionView | None:
    units = [
        p.block.install
        for p in plan.packages
        if isinstance(p.block.install, RegionalDataInstall | DerivedDataInstall)
    ]
    if not units or maps is None or not (maps.fetch or maps.current or maps.kept or maps.convert):
        return None
    converting = {f.slug for f in maps.convert}

    def line(f: RegionFile, *, current: bool) -> RegionLine:
        return RegionLine(
            region=f.region,
            snapshot=f.snapshot,
            size=f.size,
            size_human=human_size(f.size),
            verified_by=f.verified_by,
            nothing_to_do=current and f.slug not in converting,
        )

    total = sum(f.size for f in maps.fetch)
    disk = total + sum(bin_estimate(f.size) for f in maps.convert)
    return MapSectionView(
        fetch=tuple(line(f, current=False) for f in maps.fetch),
        current=tuple(line(f, current=True) for f in maps.current),
        convert=tuple(
            ConvertLine(
                region=f.region,
                snapshot=f.snapshot,
                estimate=bin_estimate(f.size),
                estimate_human=human_size(bin_estimate(f.size)),
            )
            for f in maps.convert
        ),
        kept=tuple(KeptLine(region=k.region, snapshot=k.snapshot, reason=k.reason) for k in maps.kept),
        licence=units[0].licence.strip(),
        licence_url=units[0].licence_url,
        download_total=total,
        download_total_human=human_size(total),
        disk_total_human=human_size(disk),
        estimate_note=ESTIMATE,
    )
````

In `render_plan_view`, directly after the offline-data block and before `if view.memberships:`, render it exactly as #121's `render_plan` did:

````python
    if view.maps is not None:
        maps = view.maps
        lines.append("Map regions, from station config (D-057):")
        if maps.fetch:
            lines.append("  will be downloaded and installed:")
            width = max(len(f.region) for f in maps.fetch)
            lines.extend(
                f"    {f.region:<{width}}  {f.snapshot}  {f.size_human:>9}  {f.verified_by}"
                for f in maps.fetch
            )
        if maps.current:
            lines.append("  already installed, current:")
            width = max(len(f.region) for f in maps.current)
            lines.extend(
                f"    {f.region:<{width}}  {f.snapshot}"
                + ("  (nothing to do)" if f.nothing_to_do else "")
                for f in maps.current
            )
        if maps.convert:
            lines.append(f"  will be converted for Navit (map sizes an {maps.estimate_note}):")
            width = max(len(f.region) for f in maps.convert)
            lines.extend(
                f"    {f.region:<{width}}  {f.snapshot}  about {f.estimate_human}"
                for f in maps.convert
            )
        for kept in maps.kept:
            lines.append(
                f"  {kept.region}: could not check for a newer map; keeping the installed "
                f"{kept.snapshot or '(snapshot not recorded)'}"
            )
            lines.extend(wrap(kept.reason, indent="      "))
        lines.append(f"      licence: {maps.licence}, stated at {maps.licence_url}")
        lines.append(
            f"      download total: {maps.download_total_human}; about "
            f"{maps.disk_total_human} of disk with Navit's maps ({maps.estimate_note})"
        )
        lines.append("      installs under <prefix>/share/hammunition/data/")
        lines.append("")
````

`render_plan` in `cli/main.py` gains `maps: MapDisclosure | None = None` and passes `maps=maps` to `build_install_view`. In `cmd_install`, pass `maps=maps, region_notes=region_notes` to `build_install_view`, and print `for note in (*suggestion_notes, *region_notes): print(f"note: {note}")` in the text branch as #121 does.

- [ ] **Step 5: Add the map fields to the station document**

In `src/hammunition/interface/station.py`, add the fields after `node_alias`:

````python
    map_regions: tuple[str, ...] = described(
        "the Geofabrik region paths; the text prints only how many (D-057)"
    )
    map_freshness: str = described("`yearly`, `monthly` or the other modes D-057 names")
````

set them in `build_station` (`map_regions=tuple(station.map_regions)`, `map_freshness=station.freshness`), and in `render_station`, after the per-field lines, append #121's two lines:

````python
    lines.append(
        f"  {'map regions':<14} {len(doc.map_regions)} set"
        if doc.map_regions
        else f"  {'map regions':<14} (not set)"
    )
    lines.append(f"  {'map freshness':<14} {doc.map_freshness}")
````

Change `test_every_station_field_is_in_the_document` in `tests/test_json_station_hardware.py` to compare against every `Station` dataclass field, since `STATION_FIELDS` excludes the map fields:

````python
def test_every_station_field_is_in_the_document() -> None:
    carried = {f.name for f in dataclasses.fields(StationDocument)}
    wanted = {f.name for f in dataclasses.fields(Station)}
    assert wanted <= carried, sorted(wanted - carried)
````

- [ ] **Step 6: Run everything, regenerate the goldens that gained fields**

Run: `.venv/bin/pytest tests/test_json_maps.py -q`, then `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_station_hardware.py tests/test_json_install.py tests/test_json_plan.py -q -k "document or golden"`, then `.venv/bin/pytest -q`.
Expected: `tests/test_json_maps.py` all passed with `plan-maps-text.txt` and `station-maps.txt` unchanged from Step 1; the regenerated `.json` goldens differ only by the added `maps`, `region_notes`, `map_regions`, `map_freshness` keys (check with `git diff tests/fixtures/json/*.json`); every `.txt` golden unchanged; full suite passed.

- [ ] **Step 7: Regenerate the page, run the gates, commit**

Run: `.venv/bin/python scripts/gen_json_reference.py && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q`
Expected: as Task 2 Step 7.

```bash
git add src/hammunition/interface src/hammunition/cli/main.py tests/test_json_maps.py \
  tests/test_json_station_hardware.py tests/fixtures/json docs/reference/json-interface.md
git commit -m "$(cat <<'EOF'
maps regions --json, the plan's map section, station map fields (D-059, D-057)

The plan document and the station document carry the regions for a local
front end; update and doctor documents never name one, pinned by test.
Text unchanged, held by goldens captured from the code before the move.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: After #119 — `hardware state --json` carries real `kept` and `attached`

**Depends on:** PR #119 merged to `main`, and Task 5. Names as on branch `device-kept-off` at `ea42711`: `cmd_hardware_state` reads `read_kept()` from `hammunition.hardware.power` and splits with `_kept_split(found_sorted, kept) -> (rows: list[tuple[Parkable, bool]], absent: list[entry])`, each absent entry carrying `name, address, vendor, product`. Re-read them on `main` first.

**Files:**
- Modify: `src/hammunition/interface/hardware.py` (`HardwareDocument`, `build_hardware`, `render_hardware`), `src/hammunition/cli/main.py` (`cmd_hardware_state`), `tests/test_json_station_hardware.py`
- Regenerate: `tests/fixtures/json/hardware-*.{txt,json}` (text from #119's code, Step 1), `docs/reference/json-interface.md`

**Interfaces:**
- Consumes: #119's `read_kept`, `_kept_split`, `PowerError`.
- Produces: `build_hardware(rows: Sequence[tuple[Parkable, bool]], absent: Sequence[KeptEntry], skipped, kept_error: str | None) -> HardwareDocument`; `HardwareDocument.kept_error: str | None` (additive). `DeviceView` keys unchanged.

- [ ] **Step 1: Capture the text goldens from #119's rendering, before moving anything**

As Task 9 Step 1: a throwaway worktree at #119's merge commit, `tests/json_support.py` and `tests/fixtures/json/` copied in, and Task 5's `tests/test_json_station_hardware.py` with `_hardware` extended to also patch the kept list:

````python
def _hardware(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    found: list[Parkable],
    *flags: str,
    kept: list[object] | None = None,
) -> tuple[int, str]:
    from hammunition.hardware import power

    skipped = [("fixture-radio", "its port has no power control")]
    monkeypatch.setattr(cli, "_survey_parkables", lambda args: (found, skipped))
    monkeypatch.setattr(power, "read_kept", lambda: kept or [])
    rc = cli.main(["hardware", "state", *flags])
    return rc, capsys.readouterr().out
````

and a third scenario in `HARDWARE`, `"hardware-kept-absent": []` run with `kept=[<a KeptEntry for gps-receiver@1-9, 1234:5678>]` (build it with #119's `KeptEntry` constructor). Run `HAMMUNITION_UPDATE_GOLDEN=1 ... -k text_is_unchanged`, copy the three `.txt` back, remove the worktree.
Expected there: `3 passed`; `hardware-one.txt` now has the `kept` column; `hardware-kept-absent.txt` has the `Kept parked, not attached` section.

- [ ] **Step 2: Run here to verify the text tests fail**

Run: `.venv/bin/pytest tests/test_json_station_hardware.py -q -k hardware`
Expected: the three text tests FAIL (Task 5's `render_hardware` has no `kept` column).

- [ ] **Step 3: Fill `kept` and `attached`, render #119's text**

In `src/hammunition/interface/hardware.py`, add `kept_error: str | None = described("why the kept-off entries could not be read; null when they were")` to `HardwareDocument`, and replace `build_hardware` and `render_hardware`:

````python
def build_hardware(
    rows: Sequence[tuple[Parkable, bool]],
    absent: Sequence[Any],
    skipped: Sequence[tuple[str, str]],
    kept_error: str | None = None,
) -> HardwareDocument:
    attached = [
        DeviceView(
            name=p.name,
            summary=p.summary,
            address=p.address,
            identifier=p.identifier,
            method=str(p.method),
            parked=p.parked,
            kept=is_kept,
            attached=True,
        )
        for p, is_kept in rows
    ]
    # Same shape the helper prints for a kept entry with nothing attached.
    missing = [
        DeviceView(
            name=e.name,
            summary="",
            address=e.address,
            identifier=f"{e.vendor}:{e.product}",
            method="",
            parked=True,
            kept=True,
            attached=False,
        )
        for e in absent
    ]
    return HardwareDocument(
        devices=(*attached, *missing),
        skipped=tuple(SkippedView(unit=unit, why=why) for unit, why in skipped),
        kept_error=kept_error,
    )


def render_hardware(doc: HardwareDocument) -> list[str]:
    """``hardware state`` as the terminal shows it (the kept-off form, D-056)."""
    lines = [f"  {s.unit}: not parkable right now — {s.why}" for s in doc.skipped]
    if doc.kept_error is not None:
        lines += ["", f"Kept-off entries could not be read: {doc.kept_error}"]
    here = [d for d in doc.devices if d.attached]
    gone = [d for d in doc.devices if not d.attached]
    if here:
        lines.append(f"{'device':24} {'address':10} {'state':8} {'kept':5} summary")
        for d in here:
            lines.append(
                f"{d.name:24} {d.address:10} {'parked' if d.parked else 'awake':8} "
                f"{'yes' if d.kept else 'no':5} {d.summary}"
            )
    if gone:
        lines += [
            "",
            "Kept parked, not attached (cleared with `hammunition hardware wake NAME@ADDRESS`):",
        ]
        lines += [f"  {d.name}@{d.address}  {d.identifier}" for d in gone]
    if not here and not gone:
        lines.append(
            "No parkable device is attached. A device is parkable when its catalog "
            "entry carries a power_control block and it is plugged in now."
        )
        return lines
    lines += [
        "",
        "`hammunition hardware park NAME` keeps it parked across reboots; "
        "`park --until-reboot NAME` lets a reboot wake it; `wake NAME` brings it back.",
    ]
    return lines
````

(import `Any` from `typing`; `absent` entries are #119's kept-entry type, typed `Any` here to keep the privileged helper's types out of the interface package). Replace `cmd_hardware_state` with:

````python
@envelope.json_capable()
def cmd_hardware_state(args: argparse.Namespace) -> int:
    """Which catalogued devices can be parked, which are parked now, and which
    are kept parked across reboots — attached or not."""
    from hammunition.hardware.power import PowerError, read_kept
    from hammunition.interface.hardware import build_hardware, render_hardware

    found, skipped = _survey_parkables(args)
    kept_error: str | None = None
    try:
        kept = read_kept()
    except (OSError, PowerError) as exc:
        kept_error, kept = str(exc), []
    rows, absent = _kept_split(sorted(found, key=lambda p: (p.name, p.address)), kept)
    doc = build_hardware(rows, absent, skipped, kept_error)
    if envelope.wanted(args):
        envelope.emit(doc)
        return EXIT_OK
    for line in render_hardware(doc):
        print(line)
    return EXIT_OK
````

In Task 5's `test_a_device_carries_every_key_the_helper_prints`, assert equality now, not a subset: `assert helper_keys == ours`.

- [ ] **Step 4: Run, regenerate the JSON goldens, run everything**

Run: `.venv/bin/pytest tests/test_json_station_hardware.py -q -k text_is_unchanged` (Expected: 3 passed against the goldens from Step 1), then `HAMMUNITION_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_json_station_hardware.py -q -k document_matches`, then `.venv/bin/pytest -q`.
Expected: all passed; in `hardware-kept-absent.json` the device reads `"kept": true, "attached": false`.

- [ ] **Step 5: Regenerate the page, run the gates, commit**

Run: `.venv/bin/python scripts/gen_json_reference.py && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q`

```bash
git add src/hammunition/interface/hardware.py src/hammunition/cli/main.py \
  tests/test_json_station_hardware.py tests/fixtures/json/hardware-* docs/reference/json-interface.md
git commit -m "$(cat <<'EOF'
hardware state --json carries kept and attached (D-059, D-056)

The document's device keys now equal the helper's state array, kept-off
entries with nothing attached included. Text unchanged, held by goldens
captured from the kept-off code.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Docs: D-059, getting started, the CLI reference, the README

**Depends on:** Tasks 1 to 8 merged. Tasks 9 and 10 each document their own part; if they land after this task, they add one sentence each to D-059's "What landed" list.

**Files:**
- Modify: `docs/DECISIONS.md` (append D-059), `docs/getting-started/install.md`, `docs/reference/cli.md` (one line per verb with a document), `README.md` (one line), `CLAUDE.md` (decisions table row; `docs/reference/json-interface.md` in the Document authority list)
- Test: `tests/test_docs_json_interface.py`

**Interfaces:**
- Consumes: `hammunition.interface.envelope.kinds()`, `refusal`, `_CAPABLE` (read in the test).
- Produces: nothing code depends on.

- [ ] **Step 1: Write the failing doc tests**

`tests/test_docs_json_interface.py`:

````python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The JSON interface is documented where people look.  D-059."""

from __future__ import annotations

import importlib
from pathlib import Path

from hammunition.interface import envelope

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_DOC = REPO_ROOT / "docs" / "reference" / "cli.md"


def test_d059_is_recorded() -> None:
    text = (REPO_ROOT / "docs" / "DECISIONS.md").read_text()
    assert "## D-059" in text
    assert "never driven through JSON" in text


def test_every_json_capable_verb_says_so_in_the_cli_reference() -> None:
    importlib.import_module("hammunition.cli.main")  # registers the decorators
    text = CLI_DOC.read_text()
    # Only the engine's own commands: test_json_interface.py registers a probe.
    capable = [f for f in envelope._CAPABLE if f.__module__ == "hammunition.cli.main"]
    assert capable, "no JSON-capable command found; the check below would pass empty"
    for func in capable:
        verb = func.__name__.removeprefix("cmd_").replace("_", " ")
        assert f"`hammunition {verb}" in text, f"{verb} is undocumented"
    assert text.count("--json") >= len(capable), (
        "each verb with a JSON form names --json in its section"
    )


def test_getting_started_says_bootstrap_puts_hammunition_on_the_path() -> None:
    text = (REPO_ROOT / "docs" / "getting-started" / "install.md").read_text()
    assert "~/.local/bin/hammunition" in text
    assert "source .venv/bin/activate" not in text
````

Run: `.venv/bin/pytest tests/test_docs_json_interface.py -q`
Expected: `test_d059_is_recorded` FAILS (`## D-059` absent); `test_getting_started_...` FAILS; `test_every_json_capable_verb_...` FAILS on the `--json` count.

- [ ] **Step 2: Write D-059**

Append to `docs/DECISIONS.md`, in the house form (heading, Status, Context, Decision, Consequences, as D-056 is written):

````markdown
## D-059 — The engine has a machine-readable interface: one JSON document per command on stdout, rendered from the same objects as the text; a real install is never driven through JSON

**Status:** decided by the maintainer 2026-09-28 (option A of the console
design: front ends are separate projects driving the engine through a stable
interface). Spec: `docs/superpowers/specs/2026-09-28-engine-json-interface-design.md`.

**Context.** The maintainer wants a menu-driven installer that remembers what
is installed and adds more (piece 2 of four, `hammunition-console`), and the
tray (`hammunition-tray`) already reads the helper's `state` array. Parsing the
text output would make every wording change a breaking change for a front end,
and a second code path producing "the same" data would drift from what the
operator reads. On the field laptop `hammunition` was not on the PATH, and a
short command in the docs failed with "command not found".

**Decision.**

1. A global `--json`, accepted before or after the verb. With it a command
   prints one JSON document on stdout and nothing else there; diagnostics go
   to stderr; the exit code is the text run's. A run that refuses still prints
   a document: its own kind when it has one (a refused plan is a `plan` with
   `outcome: "refused"`), otherwise an `error` document.
2. Every document is `{"schema": "hammunition/1", "kind": ..., "engine": ...}`
   plus the fields of one dataclass under `src/hammunition/interface/`. A field
   is added freely within a major version; removing or redefining one bumps it.
3. The text and the document render from the same dataclass instance. Every
   text refactor this required was held byte-for-byte by a golden captured
   before it, and a test asserts per command that every value the text shows
   is in the document.
4. `install` and `uninstall` accept `--json` only with `--dry-run`. A real
   install is never driven through JSON: a front end runs the ordinary command
   in the operator's terminal, where sudo, every consent gate (D-021) and every
   disclosure are the CLI's, then reads `status --json` again.
5. `station show --json` carries the station values and `plan` the paths it
   writes, for local programs; `docs/reference/json-interface.md` says they
   are not for pasting. `doctor --json` and `update --json` keep the
   count-only rule their text follows.
6. `docs/reference/json-interface.md` is generated from the dataclasses by
   `scripts/gen_json_reference.py`, with the JSON Schema pydantic derives from
   each; every golden document validates against it.
7. `bootstrap.sh` links `~/.local/bin/hammunition` to the checkout's
   `.venv/bin/hammunition` through `scripts/path-link.sh`: idempotent, never
   replacing a file it did not make or another checkout's link, printing the
   line to add when `~/.local/bin` is not on the PATH. `doctor` warns when
   `hammunition` is missing from the PATH or resolves to another checkout.

**Consequences.** A new command gets a document by adding a module to
`src/hammunition/interface/` and `@envelope.json_capable()` to its function;
the reference page and the `--json` flag follow without a list to edit. A
command with no document refuses `--json` and runs nothing. No network API
exists or is implied: the interface is a local process's stdout.
````

- [ ] **Step 3: Update getting started, the CLI reference, the README and CLAUDE.md**

In `docs/getting-started/install.md`, extend the paragraph after `./bootstrap.sh` with:

````markdown
It also puts `hammunition` on your PATH: `~/.local/bin/hammunition` becomes a
link to this checkout's `.venv/bin/hammunition`, so every command in these docs
works as written. If `~/.local/bin` is not on your PATH yet, bootstrap says so
and prints the one line to add to `~/.profile`. It never replaces a
`~/.local/bin/hammunition` it did not create; `hammunition doctor` tells you
which `hammunition` your PATH finds.
````

and change the three `.venv/bin/hammunition` lines under "Or by hand" to end with `ln -s "$PWD/.venv/bin/hammunition" ~/.local/bin/hammunition` followed by `hammunition doctor`.

In `docs/reference/cli.md`, at the end of each of these verb sections add one sentence naming its document kind and linking the page, e.g. for `status`: ``With `--json`, prints a `status` document ([json-interface.md](json-interface.md)).`` Do it for `status` (`status`), `update` (`update`), `list` (`catalog`), `show` (`profile`, or `unit` for a unit's name), `install` (`plan`, `--dry-run` only), `uninstall` (`plan`, `--dry-run` only), `doctor` (`doctor`), `hardware state` (`hardware`), `station show` (`station`, with "for local programs, not for pasting"). In `README.md`, add one line to the paragraph describing the CLI: ``Every read-only command also speaks JSON (`--json`) for front ends; see `docs/reference/json-interface.md`.`` In `CLAUDE.md`, add `docs/reference/json-interface.md` to the Document authority list and a row to the decisions table: `| Engine interface | One JSON document per command under --json, from the same dataclasses as the text; installs never driven through JSON | A console and the tray need a stable interface, not parsed text (**D-059**) |`.

- [ ] **Step 4: Run the doc tests and the gates**

Run: `.venv/bin/pytest tests/test_docs_json_interface.py tests/test_cli.py -q && .venv/bin/python scripts/check_doc_links.py && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy --strict && .venv/bin/pytest -q`
Expected: all passed; `no broken internal references`.

- [ ] **Step 5: Commit**

```bash
git add docs/DECISIONS.md docs/getting-started/install.md docs/reference/cli.md README.md CLAUDE.md \
  tests/test_docs_json_interface.py
git commit -m "$(cat <<'EOF'
D-059: the engine's JSON interface and hammunition on the PATH, documented

Decision record, getting-started (bootstrap now links hammunition onto
the PATH), one line per verb with a document in the CLI reference, and a
test that keeps each of those true.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

- **Spec coverage.** §2 PATH: Task 8 (link, idempotent, refusal, PATH hint, doctor check), Task 11 (docs say so). §3 flag and envelope: Task 1. Commands: `status` T2, `list`/`show` T3, `install`/`uninstall --dry-run` T4, `station show` and `hardware state` T5, `update` T6, `doctor` T7, `maps regions` T9. Installs never through JSON: T1 (`refusal`), T4 (test). §4 same objects plus the parity test: every task's `assert_text_values_in_json`. §5 golden per command, schema validation, one document on refusal, bootstrap tests: T1 to T10. Generated page with `--check` in `test_docs_generated.py`: T1. §6 privacy: T5 (reference says not for pasting), T6/T7 (no station value), T9 (no region name in `update`/`doctor`). §7 out of scope respected: no text change except the one error-path ordering in T2, stated there.
- **Placeholder scan.** No TBD/TODO. Task 9 and Task 10 name the branch commit their code was read from and say to re-read on `main`, because that code is not on `main` yet; their code blocks are complete against those commits.
- **Type consistency.** `build_install_view`, `render_plan_view(view, *, target)`, `PlanDocument` fields, `json_capable(dry_run_only=...)`, `target_view`, `DeviceView` keys and `StationDocument` fields are spelled the same in every task that uses them.
- **Review Focus.** Each of the five lines has its test in the owning task, named in the section above.

## Rulings on the planner's open questions (controller, 2026-09-28)

- `show NAME --json` accepting a package name while plain `show` refuses one:
  accepted, JSON-only, documented in `json-interface.md`. The spec forbids
  changing text output in piece 1.
- `status --json` lists recorded units, not requested profiles. The
  transaction log format does not change in piece 1; a front end derives
  profile membership from `list --json`. Recording profiles is a separate,
  log-versioned change if the console needs it.
- A `~/.local/bin/hammunition` link pointing at another checkout is left
  alone, and the command to switch it is printed (spec §2: never replace
  what it did not create).
- The `plan` document carries exactly what the text plan prints. Rendered
  config file contents, and the callsign in them, are not in it. Spec §6 is
  amended to match: less leaves the machine by accident.
- `status` with a missing catalog printing no Target lines before the error,
  and `--json --help` printing help to stderr with no document: both accepted.
- Tasks 9 and 10 are unblocked: #119 and #121 are on main (v0.10.0).
