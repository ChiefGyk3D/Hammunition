# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the engine's JSON documents. The only module that spawns `hammunition --json`.

The console ships with the engine (D-059, amended 2026-10-04), so there is one
version and no floor to check: a document's `engine` field is shown, never
compared. The engine is run as a subprocess through `launch.engine_argv()`, so
the documents stay the interface and nothing here imports engine internals.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hammunition.console import guard, verbs
from hammunition.console.launch import engine_argv

SUPPORTED_SCHEMA = "hammunition/1"
INSTALL_PAGE = "https://chiefgyk3d.github.io/Hammunition/getting-started/install/"


class EngineError(Exception):
    """Anything that stops a read."""


class EngineMissing(EngineError):
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


def parse_document(stdout: str, exit_code: int, stderr: str = "") -> Document:
    if not stdout.strip():
        raise BadDocument(
            f"the engine printed no document (exit {exit_code}): {stderr.strip()[:300]}"
        )
    try:
        body = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BadDocument(
            f"the engine printed something that is not JSON (exit {exit_code}): {exc.msg}"
        ) from exc
    if not isinstance(body, dict) or not all(
        isinstance(body.get(k), str) for k in ("schema", "kind", "engine")
    ):
        raise BadDocument("the engine's document lacks schema, kind or engine")
    schema = str(body["schema"])
    if schema != SUPPORTED_SCHEMA:
        raise UnknownSchema(
            f"the engine printed a document of schema {schema!r}; this console knows only "
            f"{SUPPORTED_SCHEMA!r}. The console and the engine are one program: update Hammunition."
        )
    return Document(str(body["kind"]), str(body["engine"]), schema, exit_code, body)


def accept(doc: Document) -> Document:
    if doc.kind == "error":
        raise EngineRefused(
            int(doc.body.get("exit_code", doc.exit_code)), str(doc.body.get("message", ""))
        )
    return doc


Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class Engine:
    def __init__(
        self,
        argv0: Sequence[str] | None = None,
        environ: Mapping[str, str] | None = None,
        run: Runner = subprocess.run,
    ) -> None:
        self.argv0 = list(engine_argv() if argv0 is None else argv0)
        self._environ = environ
        self._run = run

    def command(self, *words: str) -> list[str]:
        return [*self.argv0, *words]

    def read(self, *words: str, timeout: float | None = 180.0) -> Document:
        """One document. `timeout=None` waits as long as the engine takes: the caller passes it
        for `install`/`uninstall --dry-run`, which measured 9 m 49 s for a maps profile."""
        verbs.require_json_verb(words)
        guard.assert_clean_read(words)
        argv = [*self.argv0, *words, "--json"]
        env = guard.scrubbed_environ(os.environ if self._environ is None else self._environ)
        try:
            done = self._run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except FileNotFoundError as exc:
            raise EngineMissing(
                f"`hammunition` could not be run ({self.argv0[0]!r} was not found), and the console "
                f"cannot work without it. "
                f"Reinstall Hammunition: {INSTALL_PAGE} (run ./bootstrap.sh)."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise EngineError(f"`{' '.join(words)}` timed out after {int(timeout or 0)} s") from exc
        return accept(parse_document(done.stdout, done.returncode, done.stderr))


def command_words(argv: Sequence[str]) -> str:
    """For messages: the verb words of an argv, never its values."""
    return " ".join(w for w in argv if not w.startswith("-"))[:80]
