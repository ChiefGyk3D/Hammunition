# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The navigation guide says what the plan says about GeoClue, word for word.  D-069."""

from __future__ import annotations

from pathlib import Path

from hammunition.geoclue import DISCLOSURES


def test_the_guide_carries_every_disclosure_verbatim() -> None:
    guide = Path(__file__).parent.parent / "docs" / "guides" / "offline-navigation.md"
    text = " ".join(guide.read_text(encoding="utf-8").split())
    for sentence in DISCLOSURES:
        assert " ".join(sentence.split()) in text, sentence
