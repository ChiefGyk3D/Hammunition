# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Transaction log and what it makes possible.

CLAUDE.md: structured logging to ~/.local/state/hammunition/. D-004: the log,
not a rollback promise, is what ``uninstall`` stands on.
"""

from .log import TransactionLog, log_path
from .uninstall import RemovalError, RemovalPlan, installed_by_hammunition, plan_removal

__all__ = [
    "RemovalError",
    "RemovalPlan",
    "TransactionLog",
    "installed_by_hammunition",
    "log_path",
    "plan_removal",
]
