# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Affirmative consent gates.  D-021."""

from .gate import (
    ConsentDeclined,
    ConsentRecord,
    ConsentUnavailable,
    Decision,
    render_disclosure,
    resolve_consent,
)

__all__ = [
    "ConsentDeclined",
    "ConsentRecord",
    "ConsentUnavailable",
    "Decision",
    "render_disclosure",
    "resolve_consent",
]
