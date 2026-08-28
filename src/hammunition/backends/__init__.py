# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Install backends.

Only ``apt`` is implemented. The other six that 1.0 needs are measured, named
and absent — see DESIGN.md §6 and D-014. The planner refuses a manifest whose
method has no backend, by name, rather than skipping it; a capability matrix
that reports coverage the engine does not have is the shim CLAUDE.md forbids.
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

#: Install methods this engine build can actually perform.
IMPLEMENTED_METHODS: frozenset[str] = frozenset({"apt"})

#: `system_modifications` kinds this engine build can actually perform.
#: Everything else is a declared, named gap — never a silent skip.
IMPLEMENTED_MODIFICATIONS: frozenset[str] = frozenset({"group_membership"})

__all__ = [
    "IMPLEMENTED_METHODS",
    "IMPLEMENTED_MODIFICATIONS",
    "Action",
    "AptBackend",
    "AptPackageState",
    "BackendError",
    "Command",
    "CommandResult",
    "CommandRunner",
    "RecordingRunner",
    "SubprocessRunner",
    "parse_policy",
]
