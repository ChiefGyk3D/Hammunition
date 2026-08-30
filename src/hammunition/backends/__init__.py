# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Install backends.

``apt``, ``source`` and ``git`` are implemented. The other three that 1.0
needs — binary, venv, pipx — are measured, named and absent (DESIGN.md §6,
D-014). The
planner refuses a manifest whose method has no backend, by name, rather than
skipping it; a capability matrix that reports coverage the engine does not have
is the shim CLAUDE.md forbids.

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
from .source import SourceBackend
from .venv import VenvBackend

#: Install methods this engine build can actually perform.
IMPLEMENTED_METHODS: frozenset[str] = frozenset({"apt", "binary", "git", "source", "venv"})

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
    "RecordingRunner",
    "SourceBackend",
    "SubprocessRunner",
    "VenvBackend",
    "parse_policy",
]
