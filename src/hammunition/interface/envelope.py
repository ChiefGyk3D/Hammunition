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
import io
import json
import pkgutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from importlib import import_module, metadata
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
    """``status``, ``hardware state``, ``maps repeaters import``: the verb as
    the operator typed it."""
    verb = str(getattr(args, "command", None) or "")
    sub = getattr(args, f"{verb}_command", None) if verb else None
    if not sub:
        return verb
    third = getattr(args, f"{verb}_{sub}_command".replace("-", "_"), None)
    return f"{verb} {sub} {third}" if third else f"{verb} {sub}"


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
        module = import_module(f"{package.__name__}.{info.name}")
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
