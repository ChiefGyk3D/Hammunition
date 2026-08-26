# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every file carries the licence its tree requires. D-023.

The split is the whole point: GPL-3.0-or-later on the engine because the
argument for this project is a governance argument, CC0-1.0 on the catalog
because the catalog is required to stay usable by an engine that isn't ours.
A split enforced only by convention is a split that drifts — a manifest
copy-pasted from a Python module inherits the wrong identifier, and nobody
notices until someone downstream has to ask.

So it is checked. Two ways a file can be wrong: no identifier at all, or the
identifier belonging to the other tree.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

GPL = "GPL-3.0-or-later"
CC0 = "CC0-1.0"

SPDX = re.compile(r"^#\s*SPDX-License-Identifier:\s*(\S+)\s*$", re.M)
COPYRIGHT = re.compile(r"^#\s*SPDX-FileCopyrightText:\s*(.+?)\s*$", re.M)

# (glob, required identifier). The catalog is CC0; everything else is GPL.
TREES: tuple[tuple[str, str], ...] = (
    ("src/**/*.py", GPL),
    ("tests/**/*.py", GPL),
    ("scripts/*.py", GPL),
    ("scripts/*.sh", GPL),
    ("catalog/**/*.yaml", CC0),
)


def files(pattern: str) -> list[Path]:
    return sorted(p for p in REPO_ROOT.glob(pattern) if p.is_file())


def identifier(path: Path) -> str | None:
    match = SPDX.search(path.read_text())
    return match.group(1) if match else None


ALL_FILES = [(path, spdx) for pattern, spdx in TREES for path in files(pattern)]


def test_there_is_something_to_check() -> None:
    """Guards the silent pass: a glob that matches nothing checks nothing."""
    assert len(ALL_FILES) > 40
    for pattern, _ in TREES:
        assert files(pattern), f"{pattern} matched no files"


@pytest.mark.parametrize(
    ("path", "expected"),
    [pytest.param(p, s, id=str(p.relative_to(REPO_ROOT))) for p, s in ALL_FILES],
)
def test_every_file_declares_the_licence_of_its_tree(path: Path, expected: str) -> None:
    found = identifier(path)
    assert found is not None, (
        f"{path.relative_to(REPO_ROOT)} has no SPDX-License-Identifier. "
        f"D-023 requires one on every source and manifest file."
    )
    assert found == expected, (
        f"{path.relative_to(REPO_ROOT)} declares {found}, but its tree is "
        f"{expected}. The catalog is CC0 and the engine is GPL; a file with the "
        f"other tree's identifier is a copy-paste, not a decision."
    )


@pytest.mark.parametrize(
    "path", [pytest.param(p, id=str(p.relative_to(REPO_ROOT))) for p, _ in ALL_FILES]
)
def test_every_file_names_a_copyright_holder(path: Path) -> None:
    assert COPYRIGHT.search(path.read_text()), (
        f"{path.relative_to(REPO_ROOT)} has no SPDX-FileCopyrightText"
    )


def test_no_catalog_file_is_copylefted() -> None:
    """The invariant, stated directly rather than as a consequence of a table.

    CLAUDE.md: the catalog must remain usable by an engine that isn't ours. A
    GPL manifest is one an alternative engine cannot freely consume.
    """
    offenders = [
        p.relative_to(REPO_ROOT) for p in files("catalog/**/*.yaml") if identifier(p) != CC0
    ]
    assert not offenders, f"catalog files not under CC0-1.0: {offenders}"


def test_licence_texts_are_present_and_verbatim() -> None:
    """Copied from Debian base-files, not transcribed. Checksums from D-023."""
    import hashlib

    expected = {
        "LICENSE": "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903",
        "LICENSES/GPL-3.0-or-later.txt": (
            "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903"
        ),
        "catalog/LICENSE": "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499",
        "LICENSES/CC0-1.0.txt": (
            "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499"
        ),
    }
    for name, digest in expected.items():
        path = REPO_ROOT / name
        assert path.is_file(), f"{name} is missing"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == digest, (
            f"{name} does not match the canonical text. A licence with an "
            f"unknown diff in it is not the licence it claims to be."
        )


def test_reuse_toml_exists() -> None:
    """Covers the formats a comment cannot reach — data, generated docs, config."""
    assert (REPO_ROOT / "REUSE.toml").is_file()


HOLDER = "Copyright (C) 2026 Renegade Penguin LLC"


def test_one_copyright_holder_everywhere() -> None:
    """Q-012. A second holder string is a copy-paste, not a decision."""
    holders = {m.group(1) for p, _ in ALL_FILES for m in [COPYRIGHT.search(p.read_text())] if m}
    assert holders == {HOLDER}, f"expected one holder, found: {sorted(holders)}"


def test_no_cla_claim_is_stated_where_people_look() -> None:
    """A company name in every header invites the assumption this rebuts.

    Not decoration: without it a contributor reasonably infers assignment, and
    the inference costs us exactly the drive-by contributions we most want.
    """
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text()
    assert "no CLA" in contributing or "There is no CLA" in contributing
    assert "retain copyright" in contributing or "keep your copyright" in contributing.lower()


def test_the_licence_texts_carry_no_project_copyright() -> None:
    """A copyright line inserted into a licence corrupts the licence.

    The checksum test above already catches this, but it fails with "does not
    match the canonical text", which does not tell the next person WHY someone
    would have edited it. This one names the mistake.
    """
    for name in ("LICENSE", "catalog/LICENSE"):
        assert HOLDER not in (REPO_ROOT / name).read_text(), (
            f"{name} is a verbatim licence text. The copyright notice belongs in "
            f"the SPDX headers and REUSE.toml, not inside the licence -- and CC0 "
            f"is a waiver, so a notice printed on it contradicts the instrument."
        )
