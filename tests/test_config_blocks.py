# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The `config_files` blocks of Q-022 #1 (gap analysis A1), unit by unit.

Each block's keys and path were measured from the package's own shipped
example, man page or source, and the manifest's comment cites where. These
tests pin what was measured -- the exact keyword lines a program reads -- so
that an edit to a template that breaks the program's parse fails here rather
than on an operator's radio. They use placeholders only (N0TST, FN31pr): a
real callsign or grid square never appears in the repository.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402
from hammunition.plan import _plan_config  # noqa: E402
from hammunition.station import Station  # noqa: E402

CATALOG = REPO_ROOT / "catalog" / "packages"
STATION = Station(callsign="N0TST", grid_square="FN31pr", node_alias="TSTND")

#: unit -> the path its block writes. The Q-022 #1 set, less the two whose
#: measurement said no (linpac, fbb: see their manifests).
BLOCKS: dict[str, str] = {
    "direwolf": "/etc/direwolf.conf",
}


@pytest.fixture(scope="module")
def catalog() -> dict[str, PackageManifest]:
    return load_catalog(CATALOG)


def _render(manifest: PackageManifest, station: Station = STATION) -> dict[str, str]:
    writable, deferred = _plan_config(manifest, station)
    assert not deferred, [d.why for d in deferred]
    return {config.path: body for _unit, config, body in writable}


def _lines(body: str) -> list[str]:
    """The lines a program reads: not blank, not a # comment."""
    return [ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


@pytest.mark.parametrize(("unit", "path"), sorted(BLOCKS.items()))
def test_the_block_renders_whole_with_placeholders(
    catalog: dict[str, PackageManifest], unit: str, path: str
) -> None:
    rendered = _render(catalog[unit])
    assert list(rendered) == [path]
    assert "{station." not in rendered[path], "an unsubstituted reference survived"


@pytest.mark.parametrize("unit", sorted(BLOCKS))
def test_an_empty_station_writes_nothing(catalog: dict[str, PackageManifest], unit: str) -> None:
    """D-035: the unit installs and the file is reported, never invented."""
    writable, deferred = _plan_config(catalog[unit], Station())
    assert not writable
    assert deferred and all("station set" in d.remedy for d in deferred)


@pytest.mark.parametrize("unit", sorted(BLOCKS))
def test_no_block_templates_a_secret(catalog: dict[str, PackageManifest], unit: str) -> None:
    """No password, passcode or key is ever templated (CLAUDE.md security)."""
    for config in catalog[unit].config_files:
        for line in _lines(config.template):
            assert not re.search(r"pass(word|code)|secret|token|pwd", line, re.I), (
                f"{unit}: {config.path} sets {line!r}"
            )


@pytest.mark.parametrize("unit", sorted(BLOCKS))
def test_the_manifest_says_how_to_inspect_and_reverse(
    catalog: dict[str, PackageManifest], unit: str
) -> None:
    """CLAUDE.md: every system modification says what changes, how to inspect
    it and how to reverse it -- and uninstall does not reverse config files."""
    notes = " ".join((catalog[unit].documentation.known_problems or "").split())
    path = BLOCKS[unit]
    assert path in notes or path.replace("~/", "") in notes
    assert "does not remove it" in notes
    assert "hammunition-backup" in notes


# ---------------------------------------------------------------------------
# direwolf -- D-008 by name
# ---------------------------------------------------------------------------


def test_direwolf_sets_mycall_and_the_client_ports(catalog: dict[str, PackageManifest]) -> None:
    body = _render(catalog["direwolf"])["/etc/direwolf.conf"]
    assert _lines(body) == ["CHANNEL 0", "MYCALL N0TST", "AGWPORT 8000", "KISSPORT 8001"]


def test_direwolf_leaves_the_sound_card_and_ptt_to_the_operator(
    catalog: dict[str, PackageManifest],
) -> None:
    keywords = {ln.split()[0] for ln in _lines(_render(catalog["direwolf"])["/etc/direwolf.conf"])}
    assert not keywords & {"ADEVICE", "PTT", "PBEACON", "DIGIPEAT", "IGSERVER", "IGLOGIN"}


def test_direwolf_defers_a_callsign_ax25_cannot_carry(
    catalog: dict[str, PackageManifest],
) -> None:
    writable, deferred = _plan_config(catalog["direwolf"], Station(callsign="W1AW/4"))
    assert not writable
    assert "AX.25" in deferred[0].why
