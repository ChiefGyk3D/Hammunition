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

from hammunition.execute import stage_config, write_config  # noqa: E402
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
    "ax25-tools": "/etc/ax25/axports",
    "gpredict": "~/.config/Gpredict/sample.qth",
}

#: Where a `~/` path lands in these tests: a stand-in operator home.
HOME = Path("/home/op")


def _where(path: str) -> str:
    return str(HOME / path[2:]) if path.startswith("~/") else path


@pytest.fixture(scope="module")
def catalog() -> dict[str, PackageManifest]:
    return load_catalog(CATALOG)


def _render(manifest: PackageManifest, station: Station = STATION) -> dict[str, str]:
    writable, deferred = _plan_config(manifest, station, HOME)
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
    assert list(rendered) == [_where(path)]
    assert "{station." not in rendered[_where(path)], "an unsubstituted reference survived"


@pytest.mark.parametrize("unit", sorted(BLOCKS))
def test_an_empty_station_writes_nothing(catalog: dict[str, PackageManifest], unit: str) -> None:
    """D-035: the unit installs and the file is reported, never invented."""
    writable, deferred = _plan_config(catalog[unit], Station(), HOME)
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
    assert path in notes
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


# ---------------------------------------------------------------------------
# ax25-tools -- the axports line, appended once and never as a duplicate
# ---------------------------------------------------------------------------

#: The shape of libax25's shipped /etc/ax25/axports: a header and two example
#: ports, both commented out (measured from 0.0.12-rc5+git20230513).
SHIPPED_AXPORTS = (
    "# /etc/ax25/axports\n#\n# The format of this file is:\n#\n"
    "# name callsign speed paclen window description\n#\n\n"
    "#1\tOH2BNS-1\t1200\t255\t2\t144.675 MHz (1200  bps)\n"
    "#2\tOH2BNS-9\t38400\t255\t7\tTNOS/Linux  (38400 bps)\n"
)


def _axports(catalog: dict[str, PackageManifest]) -> tuple[str, tuple[str, ...]]:
    writable, _ = _plan_config(catalog["ax25-tools"], STATION)
    (_unit, config, body) = writable[0]
    assert config.append
    return body, tuple(config.skip_if_present)


def _ports(text: str) -> list[list[str]]:
    """axports as libax25 reads it: `#` in column one is a comment, the rest
    is whitespace-separated fields (axconfig.c, strtok on space and tab)."""
    return [ln.split() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def test_axports_appends_the_wl2k_port(catalog: dict[str, PackageManifest]) -> None:
    body, _ = _axports(catalog)
    assert _ports(body) == [["wl2k", "N0TST", "1200", "255", "7", "Winlink"]]


def test_axports_append_is_idempotent(catalog: dict[str, PackageManifest], tmp_path: Path) -> None:
    body, skip = _axports(catalog)
    target = tmp_path / "axports"
    target.write_text(SHIPPED_AXPORTS)
    write_config(target, body, 0o644, append=True, backup=True, skip_if_present=skip)
    outcome = write_config(target, body, 0o644, append=True, backup=True, skip_if_present=skip)
    assert "left" in outcome and "wl2k" in outcome
    assert _ports(target.read_text()) == [["wl2k", "N0TST", "1200", "255", "7", "Winlink"]]
    assert (tmp_path / "axports.hammunition-backup").read_text() == SHIPPED_AXPORTS


@pytest.mark.parametrize(
    "existing",
    [
        "radio N0TST 9600 255 2 my own port\n",  # the callsign already has a port
        "radio\tn0tst-0\t9600\t255\t2\tsame call, -0 and lower case\n",
        "WL2K N0TST-5 1200 255 7 a wl2k port of the operator's own\n",
    ],
)
def test_axports_never_adds_a_duplicate_libax25_would_refuse(
    catalog: dict[str, PackageManifest], tmp_path: Path, existing: str
) -> None:
    """axconfig.c: "duplicate port name" (strcasecmp) and "duplicate callsign"
    are refused -- the operator's own port is left alone instead."""
    body, skip = _axports(catalog)
    target = tmp_path / "axports"
    target.write_text(SHIPPED_AXPORTS + existing)
    write_config(target, body, 0o644, append=True, backup=True, skip_if_present=skip)
    assert target.read_text() == SHIPPED_AXPORTS + existing


def test_axports_ignores_a_commented_port_on_the_same_call(
    catalog: dict[str, PackageManifest], tmp_path: Path
) -> None:
    body, skip = _axports(catalog)
    target = tmp_path / "axports"
    target.write_text(SHIPPED_AXPORTS + "#old N0TST 1200 255 2 retired\n")
    write_config(target, body, 0o644, append=True, backup=False, skip_if_present=skip)
    assert _ports(target.read_text())[-1][0] == "wl2k"


def test_axports_staged_for_root_puts_back_what_was_there(
    catalog: dict[str, PackageManifest], tmp_path: Path
) -> None:
    """The root path stages the final file for `install -m`: when the append is
    skipped the staged file is the target, byte for byte."""
    body, skip = _axports(catalog)
    target = tmp_path / "axports"
    target.write_text(SHIPPED_AXPORTS + "wl2k N0TST 1200 255 7 Winlink\n")
    staging = tmp_path / "staged"
    outcome = stage_config(staging, target, body, append=True, skip_if_present=skip)
    assert "nothing is appended" in outcome
    assert staging.read_text() == target.read_text()

    fresh = tmp_path / "fresh"
    fresh.write_text(SHIPPED_AXPORTS)
    stage_config(staging, fresh, body, append=True, skip_if_present=skip)
    assert _ports(staging.read_text()) == [["wl2k", "N0TST", "1200", "255", "7", "Winlink"]]


def test_a_callsign_is_matched_literally_not_as_a_pattern() -> None:
    """A value substituted into skip_if_present is escaped: it can only ever
    match itself."""
    manifest = PackageManifest.model_validate(
        {
            "name": "fixture",
            "version": "1.0",
            "summary": "An append with a skip pattern",
            "categories": ["packet"],
            "install": [{"install": {"method": "apt", "packages": ["fixture"]}}],
            "config_files": [
                {
                    "path": "/etc/fixture",
                    "append": True,
                    "template": "port {station.callsign}\n",
                    "skip_if_present": ["^port {station.callsign}$"],
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for an append that must not duplicate a line.",
                "why_you_want_it": "To prove a value is not a pattern.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )
    writable, _ = _plan_config(manifest, Station(callsign="W1AW/4"))
    (pattern,) = writable[0][1].skip_if_present
    assert re.search(pattern, "port W1AW/4")
    assert not re.search(pattern, "port W1AWX4")


def test_skip_if_present_is_refused_on_a_whole_file_write() -> None:
    from hammunition.manifest.schema import ConfigFile, ManifestError

    with pytest.raises((ManifestError, ValueError), match="append"):
        ConfigFile(path="/etc/x", template="x", skip_if_present=["x"])


# ---------------------------------------------------------------------------
# gpredict -- the default ground station, from the grid square
# ---------------------------------------------------------------------------


def _keyfile(body: str) -> dict[str, dict[str, str]]:
    """A GKeyFile read the way gpredict's qth_data_read sees it: `[group]`
    headers, `key=value`, `#` comments."""
    groups: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in body.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if line.startswith("["):
            current = groups.setdefault(line.strip("[]"), {})
            continue
        assert current is not None, f"{line!r} is outside any group"
        key, _, value = line.partition("=")
        current[key] = value
    return groups


def test_gpredict_writes_the_default_ground_station(catalog: dict[str, PackageManifest]) -> None:
    body = _render(catalog["gpredict"])[str(HOME / ".config/Gpredict/sample.qth")]
    qth = _keyfile(body)["QTH"]
    assert qth["LOCATION"] == "FN31pr"
    assert (qth["LAT"], qth["LON"]) == ("41.7292", "-72.7083"), "the centre of FN31pr"
    assert "ALT" not in qth, "station config has no altitude; nothing is invented"
    assert set(qth) <= {"LOCATION", "DESCRIPTION", "WX", "LAT", "LON", "ALT", "QTH_TYPE"}


def test_gpredict_is_deferred_without_a_grid_square(catalog: dict[str, PackageManifest]) -> None:
    writable, deferred = _plan_config(catalog["gpredict"], Station(callsign="N0TST"), HOME)
    assert not writable
    assert "grid_square" in deferred[0].why
    assert "--grid-square" in deferred[0].remedy
