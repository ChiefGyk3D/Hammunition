# SPDX-FileCopyrightText: 2026 The Hammunition contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Transaction log.  CLAUDE.md: structured logging to ~/.local/state/hammunition/."""

from .log import TransactionLog, log_path

__all__ = ["TransactionLog", "log_path"]
