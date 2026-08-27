# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Distribution detection.  DESIGN.md §8 — /etc/os-release, no heuristics.

The tests that matter here are the refusals. Detection that works on the five
declared targets is easy; what earns its place is that a system which does not
say what it is gets an error rather than a guess, because the next thing the
engine does with that answer is install packages onto the machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.distro import DetectionError, Target, parse_os_release  # noqa: E402

DEBIAN_13 = """\
PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
NAME="Debian GNU/Linux"
VERSION_ID="13"
VERSION="13 (trixie)"
VERSION_CODENAME=trixie
ID=debian
"""

MINT = """\
NAME="Linux Mint"
VERSION="22.3 (Zara)"
ID=linuxmint
ID_LIKE=ubuntu
VERSION_ID="22.3"
"""

DEBIAN_SID = """\
PRETTY_NAME="Debian GNU/Linux trixie/sid"
NAME="Debian GNU/Linux"
ID=debian
VERSION_CODENAME=trixie
"""

FEDORA = """\
NAME="Fedora Linux"
VERSION="41 (Workstation Edition)"
ID=fedora
VERSION_ID=41
"""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_quoted_values_lose_their_quotes_and_keep_their_spaces() -> None:
    fields = parse_os_release(DEBIAN_13)
    assert fields["PRETTY_NAME"] == "Debian GNU/Linux 13 (trixie)"
    assert fields["ID"] == "debian"


def test_a_value_containing_an_equals_sign_survives() -> None:
    """`partition` on the first `=` only. A naive split would truncate this."""
    fields = parse_os_release('HOME_URL="https://example.invalid/?a=b&c=d"')
    assert fields["HOME_URL"] == "https://example.invalid/?a=b&c=d"


def test_comments_and_blank_lines_are_skipped() -> None:
    assert parse_os_release("# a comment\n\nID=debian\n") == {"ID": "debian"}


def test_single_quotes_are_handled_too() -> None:
    assert parse_os_release("ID='debian'")["ID"] == "debian"


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_system_with_no_id_is_an_error_not_a_guess() -> None:
    """The whole point of DESIGN.md §8. No falling back to /etc/debian_version."""
    with pytest.raises(DetectionError, match="declares no ID"):
        Target.from_fields(parse_os_release("NAME=Mystery\n"), machine="x86_64")


def test_a_system_with_no_os_release_file_at_all_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(DetectionError, match="no os-release file"):
        Target.detect(paths=(tmp_path / "absent", tmp_path / "also-absent"))


# ---------------------------------------------------------------------------
# Version, which is allowed to be absent
# ---------------------------------------------------------------------------


def test_version_id_is_preferred() -> None:
    target = Target.from_fields(parse_os_release(DEBIAN_13), machine="x86_64")
    assert target.version == "13"


def test_version_falls_back_to_the_codename() -> None:
    """Debian testing and sid ship no VERSION_ID. That is not a failure."""
    target = Target.from_fields(parse_os_release(DEBIAN_SID), machine="x86_64")
    assert target.version == "trixie"


def test_an_empty_version_still_matches_selectors_that_name_none() -> None:
    """Most manifests do not constrain the version, and must keep resolving."""
    from hammunition.manifest.schema import Selector

    target = Target(distro="debian", version="", arch="x86_64")
    assert Selector().matches(target.distro, target.version, target.arch)
    assert not Selector(distro_version=["13"]).matches(target.distro, target.version, target.arch)


# ---------------------------------------------------------------------------
# Family membership, which gates installation rather than detection
# ---------------------------------------------------------------------------


def test_debian_is_family() -> None:
    assert Target.from_fields(parse_os_release(DEBIAN_13), machine="x86_64").is_debian_family


def test_mint_is_family_through_ubuntu_not_debian() -> None:
    """Mint's ID_LIKE names ubuntu and never debian; a single-hop check misses it."""
    target = Target.from_fields(parse_os_release(MINT), machine="x86_64")
    assert "debian" not in target.id_like
    assert target.is_debian_family


def test_fedora_is_not_family() -> None:
    assert not Target.from_fields(parse_os_release(FEDORA), machine="x86_64").is_debian_family


def test_an_unknown_id_with_a_debian_id_like_is_family() -> None:
    """A Debian derivative we have never heard of still installs correctly."""
    target = Target.from_fields(
        parse_os_release("ID=somethingnew\nID_LIKE=debian\n"), machine="x86_64"
    )
    assert target.is_debian_family


# ---------------------------------------------------------------------------
# What gets recorded
# ---------------------------------------------------------------------------


def test_the_log_entry_records_what_was_read_verbatim() -> None:
    target = Target.from_fields(parse_os_release(MINT), machine="aarch64")
    entry = target.to_log_entry()
    assert entry["distro"] == "linuxmint"
    assert entry["distro_version"] == "22.3"
    assert entry["arch"] == "aarch64"
    assert entry["id_like"] == ["ubuntu"]


def test_describe_names_the_fields_it_read() -> None:
    line = Target.from_fields(parse_os_release(DEBIAN_13), machine="x86_64").describe()
    assert "ID=debian" in line and "arch=x86_64" in line
