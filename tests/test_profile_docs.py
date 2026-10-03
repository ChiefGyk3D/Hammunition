# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every profile this repository ships carries the newcomer-facing prose.

The schema leaves these fields optional so a community profile is not refused
for lacking them, but the generated profile page and the profiles index read
them, and a profile without them would render a page with a hole in it. A
maintainer who wants the index's "which profile do I want" table to stay
complete needs this to fail naming the profile and the field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.manifest.load import load_catalog, load_profiles

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_TEXT = ("who_for", "hardware_assumed", "footprint_short", "excludes_short")
REQUIRED_LISTS = ("goals", "first_ten_minutes")


@pytest.fixture(scope="module")
def profiles() -> dict:
    catalog = load_catalog(ROOT / "catalog" / "packages")
    return load_profiles(ROOT / "catalog" / "profiles", catalog)


def test_every_profile_has_the_newcomer_fields(profiles: dict) -> None:
    missing: list[str] = []
    for name, profile in sorted(profiles.items()):
        doc = profile.documentation
        for field in REQUIRED_TEXT:
            if not (getattr(doc, field) or "").strip():
                missing.append(f"{name}: {field}")
        for field in REQUIRED_LISTS:
            if not getattr(doc, field):
                missing.append(f"{name}: {field}")
    assert not missing, (
        "profiles missing the fields the generated pages read "
        "(catalog/profiles/<name>.yaml, under documentation:): " + "; ".join(missing)
    )


def test_first_ten_minutes_steps_are_real_steps(profiles: dict) -> None:
    for name, profile in sorted(profiles.items()):
        steps = profile.documentation.first_ten_minutes
        assert len(steps) >= 4, (
            f"{name}: a first-ten-minutes list of {len(steps)} is not a walkthrough"
        )
        for step in steps:
            assert step.strip().endswith((".", "`", ")")), (
                f"{name}: step does not end as a sentence: {step[:60]!r}"
            )
