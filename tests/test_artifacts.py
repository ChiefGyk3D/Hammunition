# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition artifacts``: every remote data artifact the engine would
fetch for an explicit selection, with no station.  D-070.

The Bunker's only source of what to mirror, so the tests hold the contract:
the same resolution as the plan (pins, freshness and its fallback, the
publisher's checksums), deferred entries rather than dropped ones, and
nothing read from the operator's station. Regions are Vermont and Delaware;
every probe is a fake, and the suite refuses any socket that is not
loopback.
"""

from __future__ import annotations

import hashlib
import importlib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from hammunition.artifacts import SelectionError, list_artifacts, select_units
from hammunition.copernicus import tile_name, tile_url
from hammunition.geofabrik import BASE, GeofabrikError
from hammunition.interface.artifacts import ArtifactEntry
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import DataInstall
from hammunition.station import Station, save_station
from json_support import REPO_ROOT, assert_golden, parse_one, validate

cli = importlib.import_module("hammunition.cli.main")

CATALOG = load_catalog(REPO_ROOT / "catalog" / "packages")
TODAY = date(2026, 9, 29)
VT = "north-america/us/vermont"
DE = "north-america/us/delaware"
VT_SHA = "a" * 64
DE_MD5 = hashlib.md5(b"delaware", usedforsecurity=False).hexdigest()
TILE_VT = tile_name((43, -73))
TILE_DE = tile_name((38, -76))
TILE_MD5 = "b" * 32
POLY = {
    VT: "vermont\n1\n-72.9 43.1\n-72.1 43.1\n-72.1 43.9\n-72.9 43.9\nEND\nEND\n",
    DE: "delaware\n1\n-75.9 38.1\n-75.1 38.1\n-75.1 38.9\n-75.9 38.9\nEND\nEND\n",
}


class Geofabrik:
    """A fake Geofabrik: Vermont pinned for 260101, Delaware not; `latest`
    redirects to a September file; `gone` is a region that 404s."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(f"HEAD {url}")
        if url.endswith("-latest.osm.pbf"):
            return 302, 0, url.replace("-latest", "-260928")
        if "/gone-" in url:
            return 404, 0, None
        return 200, 12_345, None

    def text(self, url: str) -> str:
        self.asked.append(f"GET {url}")
        if url.endswith(".md5"):
            return f"{DE_MD5}  {url.rsplit('/', 1)[-1][:-4]}\n"
        for region, poly in POLY.items():
            if url == f"{BASE}/{region}.poly":
                return poly
        raise GeofabrikError(f"{url} returned HTTP 404 (Not Found)")


class Bucket:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        return 200, 40_000_000, f'"{TILE_MD5}"'


def _root(tmp_path: Path) -> Path:
    """A catalog root: the real packages, and pin data written here."""
    root = tmp_path / "catalog"
    (root / "data").mkdir(parents=True)
    (root / "packages").symlink_to(REPO_ROOT / "catalog" / "packages")
    (root / "data" / "geofabrik-pins.yaml").write_text(
        yaml.safe_dump(
            {"pins": [{"region": VT, "snapshot": "260101", "size": 99, "sha256": VT_SHA}]}
        )
    )
    (root / "data" / "copernicus-glo30-tiles.txt").write_text(f"{TILE_VT}\n{TILE_DE}\n")
    (root / "data" / "copernicus-glo30-pins.yaml").write_text(
        yaml.safe_dump(
            {"pins": [{"tile": TILE_VT, "size": 41, "sha256": "c" * 64, "md5": "d" * 32}]}
        )
    )
    return root


def _list(
    tmp_path: Path, units: tuple[str, ...], regions: tuple[str, ...], freshness: str = "yearly"
) -> tuple[tuple[ArtifactEntry, ...], Geofabrik, Bucket]:
    geofabrik, bucket = Geofabrik(), Bucket()
    entries = list_artifacts(
        units,
        regions=regions,
        freshness=freshness,
        catalog=CATALOG,
        catalog_root=_root(tmp_path),
        today=TODAY,
        region_probe=geofabrik,
        tile_probe=bucket,
    )
    return entries, geofabrik, bucket


def _by(entries: tuple[ArtifactEntry, ...], unit: str) -> list[ArtifactEntry]:
    return [e for e in entries if e.unit == unit]


# -- selection ---------------------------------------------------------------


def test_the_default_units_are_every_unit_that_fetches_data() -> None:
    units = select_units(CATALOG, ())
    assert {"country-files", "country-boundaries", "osm-regions", "dem-copernicus"} <= set(units)
    assert "osm-navit" not in units and "navit" not in units  # derived, apt


@pytest.mark.parametrize("bad", ["no-such-unit", "osm-navit", "navit"])
def test_a_unit_that_does_not_exist_or_fetches_nothing_is_refused_by_name(bad: str) -> None:
    with pytest.raises(SelectionError, match=bad):
        select_units(CATALOG, ("osm-regions", bad))


# -- data units --------------------------------------------------------------


def test_a_data_unit_lists_each_artifact_with_its_pin(tmp_path: Path) -> None:
    entries, geofabrik, _ = _list(tmp_path, ("country-files", "country-boundaries"), ())
    block = CATALOG["country-files"].install[0].install
    artifact = block.artifacts[0]  # type: ignore[union-attr]
    (files,) = _by(entries, "country-files")
    assert files == ArtifactEntry(
        unit="country-files",
        name=artifact.url.rsplit("/", 1)[-1],
        url=artifact.url,
        check="sha256",
        digest=artifact.sha256,
        checksum_url=None,
        size=artifact.size,
        licence=" ".join(block.licence.split()),  # type: ignore[union-attr]
        deferred=None,
    )
    (borders,) = _by(entries, "country-boundaries")
    assert borders.name == "ne_10m_admin_0_countries.geojson"
    assert geofabrik.asked == [], "a data unit asks nobody"


# -- map regions ------------------------------------------------------------


def test_a_pinned_region_is_sha256_and_an_unpinned_one_is_the_publishers_md5(
    tmp_path: Path,
) -> None:
    entries, geofabrik, _ = _list(tmp_path, ("osm-regions",), (VT, DE))
    vermont, delaware = _by(entries, "osm-regions")
    assert (vermont.name, vermont.check, vermont.digest, vermont.checksum_url) == (
        VT,
        "sha256",
        VT_SHA,
        None,
    )
    assert vermont.url == f"{BASE}/{VT}-260101.osm.pbf" and vermont.size == 99
    assert (delaware.check, delaware.digest) == ("md5-publisher", DE_MD5)
    assert delaware.url == f"{BASE}/{DE}-260101.osm.pbf"
    assert delaware.checksum_url == f"{delaware.url}.md5" and delaware.size == 12_345
    assert delaware.licence == "ODbL-1.0" and delaware.deferred is None
    assert not any(VT in a for a in geofabrik.asked), "a pinned region needs no network"


def test_freshness_changes_the_url_and_the_check_as_the_plan_does(tmp_path: Path) -> None:
    monthly, _, _ = _list(tmp_path / "m", ("osm-regions",), (VT,), "monthly")
    assert monthly[0].url == f"{BASE}/{VT}-260901.osm.pbf"
    assert monthly[0].check == "md5-publisher"  # the pin is for 260101 only
    latest, _, _ = _list(tmp_path / "l", ("osm-regions",), (VT,), "latest")
    assert latest[0].url == f"{BASE}/{VT}-260928.osm.pbf"


def test_a_region_that_cannot_be_resolved_is_deferred_by_name(tmp_path: Path) -> None:
    entries, _, _ = _list(tmp_path, ("osm-regions",), ("north-america/us/gone",))
    (gone,) = entries
    assert gone.name == "north-america/us/gone" and gone.url is None
    assert gone.deferred is not None and "no yearly extract" in gone.deferred


def test_map_units_with_no_regions_are_deferred_saying_how(tmp_path: Path) -> None:
    entries, geofabrik, bucket = _list(tmp_path, ("osm-regions", "dem-copernicus"), ())
    assert [(e.unit, e.name) for e in entries] == [("osm-regions", None), ("dem-copernicus", None)]
    assert all(e.deferred is not None and "--map-regions" in e.deferred for e in entries)
    assert geofabrik.asked == [] and bucket.asked == []


# -- terrain ----------------------------------------------------------------


def test_tiles_come_from_each_regions_outline(tmp_path: Path) -> None:
    entries, _, bucket = _list(tmp_path, ("dem-copernicus",), (VT, DE))
    pinned, unpinned = sorted(_by(entries, "dem-copernicus"), key=lambda e: e.name != TILE_VT)
    assert (pinned.name, pinned.check, pinned.digest, pinned.size) == (
        TILE_VT,
        "sha256",
        "c" * 64,
        41,
    )
    assert (unpinned.name, unpinned.check, unpinned.digest) == (TILE_DE, "etag-md5", TILE_MD5)
    assert unpinned.url == tile_url(TILE_DE) and unpinned.checksum_url == tile_url(TILE_DE)
    assert bucket.asked == [tile_url(TILE_DE)], "a pinned tile needs no network"


def test_a_region_whose_outline_cannot_be_read_is_deferred(tmp_path: Path) -> None:
    entries, _, _ = _list(tmp_path, ("dem-copernicus",), (VT, "north-america/us/gone"))
    deferred = [e for e in entries if e.deferred is not None]
    assert [e.name for e in deferred] == ["north-america/us/gone"]
    assert deferred[0].deferred is not None and "outline" in deferred[0].deferred
    assert [e.name for e in entries if e.deferred is None] == [TILE_VT]


def test_tiles_are_not_filtered_by_what_this_machine_has_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The listing is the same on every machine: no install record, no
    installed tile, is ever read."""
    monkeypatch.setattr(Path, "is_file", _refuse_prefix(Path.is_file))
    entries, _, _ = _list(tmp_path, ("dem-copernicus",), (VT,))
    assert [e.name for e in entries] == [TILE_VT]


def _refuse_prefix(real: Any) -> Any:
    def guarded(self: Path) -> Any:
        assert "share/hammunition" not in str(self), f"read {self}"
        return real(self)

    return guarded


# -- the command --------------------------------------------------------------


def _cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *argv: str,
) -> tuple[int, str, str]:
    root = _root(tmp_path)
    monkeypatch.setattr(cli, "UrllibProbe", Geofabrik)
    monkeypatch.setattr(cli, "S3Probe", Bucket)
    monkeypatch.setattr(cli, "date", type("D", (), {"today": staticmethod(lambda: TODAY)}))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("USER", "op")
    rc = cli.main(["--catalog", str(root), "artifacts", *argv])
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_the_document_matches_its_golden_and_its_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, _ = _cli(
        monkeypatch,
        tmp_path,
        capsys,
        "--json",
        "--map-regions",
        f"{VT},{DE}",
        "--units",
        "osm-regions,dem-copernicus",
    )
    doc = parse_one(out)
    validate(doc)
    assert rc == 0 and doc["kind"] == "artifacts"
    assert doc["map_regions"] == [VT, DE] and doc["map_freshness"] == "yearly"
    assert_golden("artifacts", doc)


def test_the_command_never_reads_the_station(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_station(
        Station(map_regions=(DE,), map_freshness="monthly", mirror="http://bunker.lan:8080/"),
        path=tmp_path / "config" / "hammunition" / "station.yml",
    )
    rc, out, _ = _cli(monkeypatch, tmp_path, capsys, "--json", "--units", "osm-regions")
    doc = parse_one(out)
    assert rc == 0 and doc["map_regions"] == [] and doc["map_freshness"] == "yearly"
    assert doc["artifacts"][0]["deferred"] is not None


def test_the_text_form_lists_the_same_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, _ = _cli(
        monkeypatch, tmp_path, capsys, "--map-regions", VT, "--units", "osm-regions,country-files"
    )
    assert rc == 0
    assert f"{BASE}/{VT}-260101.osm.pbf" in out and "sha256" in out
    assert "country-files" in out


@pytest.mark.parametrize(
    "argv",
    [
        ("--units", "osm-navit"),
        ("--units", "no-such-unit"),
        ("--map-regions", "North America/US"),
        ("--map-regions", " , "),
    ],
)
def test_a_bad_selection_is_exit_2_naming_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: tuple[str, ...],
) -> None:
    rc, out, err = _cli(monkeypatch, tmp_path, capsys, *argv)
    assert rc == 2 and out == ""
    assert "error:" in err


def test_every_listed_name_is_the_mirror_path_the_install_asks_for(tmp_path: Path) -> None:
    """The contract between the two halves of D-070: what the listing names
    `<unit>/<name>` is exactly what the fetch asks the mirror for."""
    from hammunition.backends.data import data_name
    from hammunition.fetch import MirrorPath, mirror_url

    entries, _, _ = _list(
        tmp_path, ("country-files", "country-boundaries", "osm-regions", "dem-copernicus"), (VT,)
    )
    listed = [e for e in entries if e.deferred is None]
    assert len(listed) == 4
    for entry in listed:
        assert entry.name is not None
        url = mirror_url("http://bunker.lan:8080/", MirrorPath(entry.unit, entry.name))
        assert url == f"http://bunker.lan:8080/{entry.unit}/{entry.name}"
    for unit in ("country-files", "country-boundaries"):
        block = CATALOG[unit].install[0].install
        assert isinstance(block, DataInstall)
        assert [e.name for e in listed if e.unit == unit] == [data_name(a) for a in block.artifacts]
