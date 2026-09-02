# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Install backends.

``apt``, ``source``, ``git``, ``binary``, ``venv`` and ``node`` are
implemented — every method the 1.0 measurement requires (DESIGN.md §6,
D-014; ``node`` by D-037). ``pipx`` is a measured zero, declared in the
schema and refused here. The planner refuses a manifest whose method has no
backend, by name, rather than skipping it; a capability matrix that reports
coverage the engine does not have is the shim CLAUDE.md forbids.

``source`` is the expensive half of the parity target: 35 of AHRL's 95 units are
source builds from bundled tarballs, and 57 in total cannot be satisfied by apt.
"""

from .apt import AptBackend, AptPackageState, parse_policy
from .base import (
    Action,
    BackendError,
    Command,
    CommandResult,
    CommandRunner,
    RecordingRunner,
    SubprocessRunner,
)
from .binary import IMPLEMENTED_BINARY_FORMATS, BinaryBackend
from .git import GitBackend
from .node import NodeBackend
from .source import SourceBackend
from .venv import VenvBackend

#: Install methods this engine build can actually perform.
IMPLEMENTED_METHODS: frozenset[str] = frozenset({"apt", "binary", "git", "node", "source", "venv"})

#: `system_modifications` kinds this engine build can actually perform.
#: Everything else is a declared, named gap — never a silent skip.
IMPLEMENTED_MODIFICATIONS: frozenset[str] = frozenset({"group_membership"})

__all__ = [
    "IMPLEMENTED_BINARY_FORMATS",
    "IMPLEMENTED_METHODS",
    "IMPLEMENTED_MODIFICATIONS",
    "Action",
    "AptBackend",
    "AptPackageState",
    "BackendError",
    "BinaryBackend",
    "Command",
    "CommandResult",
    "CommandRunner",
    "GitBackend",
    "NodeBackend",
    "RecordingRunner",
    "SourceBackend",
    "SubprocessRunner",
    "VenvBackend",
    "parse_policy",
]
