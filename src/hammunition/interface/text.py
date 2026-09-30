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
