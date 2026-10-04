# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared helpers for the Atheris targets in this directory.

Not a target itself (python-fuzz.yml runs only ``fuzz_*.py``). A target draws
its text from here so the fuzzer starts from a *valid* document and edits it,
which reaches the code behind the first syntax check far sooner than random
bytes do; half the inputs stay fully random so the syntax check itself is
exercised too.
"""

from __future__ import annotations

from pathlib import Path

import atheris

REPO = Path(__file__).resolve().parent.parent


def seed_text(*parts: str) -> str:
    """A tracked file under the repository, or "" when this checkout lacks it."""
    try:
        return REPO.joinpath(*parts).read_text(encoding="utf-8")
    except OSError:
        return ""


def text_from(fdp: atheris.FuzzedDataProvider, seed: str, limit: int = 4096) -> str:
    """Raw fuzzed text, or *seed* with up to four fuzzer-chosen edits."""
    if not seed or fdp.ConsumeBool():
        return fdp.ConsumeUnicodeNoSurrogates(limit)
    text = seed
    for _ in range(fdp.ConsumeIntInRange(0, 4)):
        if not text:
            break
        start = fdp.ConsumeIntInRange(0, len(text))
        end = min(len(text), start + fdp.ConsumeIntInRange(0, 64))
        kind = fdp.ConsumeIntInRange(0, 2)
        if kind == 0:
            text = text[:start] + fdp.ConsumeUnicodeNoSurrogates(32) + text[end:]
        elif kind == 1:
            text = text[:start] + text[end:]
        else:
            text = text[:end] + text[start:end] + text[end:]
    return text
