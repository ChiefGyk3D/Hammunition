# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The engine's machine-readable interface.  D-059.

One module per document kind. Each defines a frozen dataclass with a ``KIND``
class variable, and :func:`hammunition.interface.envelope.kinds` finds them by
walking this package, so adding a kind edits no shared registry. The text a
command prints and the JSON it emits under ``--json`` are rendered from the
same dataclass instance, which is what keeps the two from drifting.
"""
