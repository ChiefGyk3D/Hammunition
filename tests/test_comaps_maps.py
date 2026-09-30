# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""CoMaps' maps for the station's regions: fetch, verify, install, remove.  D-069.

Public example regions only (Vermont, Delaware). The CDN is never asked: the
transport and the ``HEAD`` are injected, and the pins are the carried file's.
"""

from __future__ import annotations

import base64
import hashlib
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import IO

import pytest

from hammunition.backends import Action
from hammunition.backends.comaps_maps import (
    ComapsMapsBackend,
    map_current,
    maps_disk_needs,
    resolve_station_maps,
)
from hammunition.comaps import VERIFIED_BY, ComapsError, MapFile, MapPin, load_pins
from hammunition.fetch import Fetcher, VerificationError
from hammunition.manifest.schema import MwmRegionsInstall, PackageManifest

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "catalog"
VERMONT = "north-america/us/vermont"
DELAWARE = "north-america/us/delaware"
OSM = {"licence": "ODbL-1.0", "licence_url": "https://www.openstreetmap.org/copyright"}


def _sha1(body: bytes) -> str:
    return base64.b64encode(hashlib.sha1(body).digest()).decode()


class _Transport:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requested: list[str] = []

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:
        self.requested.append(url)
        yield BytesIO(self.body)


def _unit() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "comaps-maps",
            "version": "station",
            "summary": "CoMaps maps for your regions",
            "categories": ["navigation-maps"],
            "install": [{"install": {"method": "mwm-regions", "provider": "comaps", **OSM}}],
            "update": {"probe": {"method": "comaps_maps"}},
            "documentation": {
                "what_it_does": "Keeps CoMaps' map files for the station's regions.",
                "why_you_want_it": "CoMaps reads its own map format and nothing else.",
                "upstream_url": "https://www.comaps.app/",
            },
        }
    )


def _block(m: PackageManifest) -> MwmRegionsInstall:
    block = m.install[0].install
    assert isinstance(block, MwmRegionsInstall)
    return block


def _file(body: bytes, name: str = "US_Vermont") -> MapFile:
    return MapFile(
        MapPin(name, len(body), _sha1(body)),
        f"https://cdn-fi-1.comaps.app/maps/2026.06.28/260830/{name}.mwm",
        260830,
    )


# -- the fetch ----------------------------------------------------------------


BODY = b"a small map file standing in for a state\n"


def test_a_map_is_verified_by_its_sha1_and_exact_size(tmp_path: Path) -> None:
    fetcher = Fetcher(tmp_path / "cache", transport=_Transport(BODY))
    f = _file(BODY)
    result = fetcher.fetch_sha1(f.url, hashlib.sha1(BODY).hexdigest(), expected_size=len(BODY))
    assert result.path.read_bytes() == BODY
    assert result.sha256 == hashlib.sha256(BODY).hexdigest()


def test_a_mirror_s_html_page_for_a_missing_map_is_refused_by_size(tmp_path: Path) -> None:
    """CoMaps' mirrors answer a missing file with 200 and a web page."""
    page = b"<html><body>Not here</body></html>"
    fetcher = Fetcher(tmp_path / "cache", transport=_Transport(page))
    with pytest.raises(VerificationError, match="size"):
        fetcher.fetch_sha1(_file(BODY).url, hashlib.sha1(BODY).hexdigest(), expected_size=len(BODY))
    assert not list((tmp_path / "cache").glob("sha1-*"))


def test_a_map_with_the_wrong_sha1_is_refused(tmp_path: Path) -> None:
    other = b"X" * len(BODY)
    fetcher = Fetcher(tmp_path / "cache", transport=_Transport(other))
    with pytest.raises(VerificationError, match="SHA-1"):
        fetcher.fetch_sha1(_file(BODY).url, hashlib.sha1(BODY).hexdigest(), expected_size=len(BODY))


# -- the backend -----------------------------------------------------------


def _backend(tmp_path: Path, files: list[MapFile], body: bytes = BODY) -> ComapsMapsBackend:
    return ComapsMapsBackend(
        fetcher=Fetcher(tmp_path / "cache", transport=_Transport(body)),
        prefix=tmp_path / "prefix",
        files=files,
    )


def test_each_map_is_disclosed_with_its_size_licence_and_check(tmp_path: Path) -> None:
    m = _unit()
    steps = _backend(tmp_path, [_file(BODY)]).steps(m, _block(m))
    [fetch] = [s for s in steps if isinstance(s, Action) and s.kind == "fetch"]
    assert "US_Vermont" in fetch.description
    assert "ODbL-1.0" in fetch.description
    assert VERIFIED_BY in fetch.description
    assert f"{len(BODY)} bytes" in fetch.detail


def test_a_map_installs_under_its_version_and_the_log_gets_its_sha256(tmp_path: Path) -> None:
    m = _unit()
    backend = _backend(tmp_path, [_file(BODY)])
    steps = backend.steps(m, _block(m))
    outcomes = [s.perform() for s in steps if isinstance(s, Action)]
    dest = tmp_path / "prefix/share/hammunition/data/comaps-maps/260830/US_Vermont.mwm"
    assert dest.read_bytes() == BODY
    assert any(hashlib.sha256(BODY).hexdigest() in o for o in outcomes)
    [install] = [s for s in steps if isinstance(s, Action) and s.kind == "install-data"]
    assert install.detail == str(dest)
    # The cached download is gone once installed.
    assert not list((tmp_path / "cache").glob("sha1-*"))


def test_a_map_at_its_pin_is_not_fetched_again(tmp_path: Path) -> None:
    m = _unit()
    f = _file(BODY)
    dest = tmp_path / "prefix/share/hammunition/data/comaps-maps/260830/US_Vermont.mwm"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(BODY)
    assert map_current(dest, f)
    assert _backend(tmp_path, [f]).steps(m, _block(m)) == []


def test_a_map_no_region_needs_is_removed(tmp_path: Path) -> None:
    m = _unit()
    data = tmp_path / "prefix/share/hammunition/data/comaps-maps"
    (data / "260830").mkdir(parents=True)
    (data / "260830" / "US_Vermont.mwm").write_bytes(BODY)
    (data / "260830" / "US_Delaware.mwm").write_bytes(b"old")
    (data / "260501").mkdir()
    (data / "260501" / "US_Vermont.mwm").write_bytes(b"an older version")
    steps = _backend(tmp_path, [_file(BODY)]).steps(m, _block(m))
    removals = [s for s in steps if isinstance(s, Action) and s.kind == "remove-data"]
    assert sorted(Path(s.detail).relative_to(data).as_posix() for s in removals) == [
        "260501/US_Vermont.mwm",
        "260830/US_Delaware.mwm",
    ]
    for step in removals:
        step.perform()
    assert (data / "260830" / "US_Vermont.mwm").exists()
    assert not (data / "260830" / "US_Delaware.mwm").exists()


def test_the_disk_need_counts_each_download_twice(tmp_path: Path) -> None:
    needs = maps_disk_needs([_file(BODY)], cache=tmp_path / "c", prefix=tmp_path / "p")
    assert needs == {tmp_path / "c": len(BODY), tmp_path / "p": len(BODY)}
    assert maps_disk_needs([], cache=tmp_path / "c", prefix=tmp_path / "p") == {}


# -- resolution before the plan prints ---------------------------------------


def _catalog(tmp_path: Path) -> Path:
    root = tmp_path / "catalog"
    (root / "data").mkdir(parents=True)
    shutil.copy(CATALOG / "data" / "comaps-pins.yaml", root / "data" / "comaps-pins.yaml")
    return root


def test_the_station_s_regions_resolve_after_one_head_each(tmp_path: Path) -> None:
    pins = load_pins(CATALOG)
    asked: list[str] = []

    def head(url: str) -> tuple[int, int]:
        asked.append(url)
        name = url.rsplit("/", 1)[1].removesuffix(".mwm")
        return 200, pins.maps[name].size

    files, notes = resolve_station_maps(
        (VERMONT, DELAWARE, "europe/germany/bayern"),
        _catalog(tmp_path),
        installed=tmp_path / "d",
        head=head,
    )
    assert [f.id for f in files] == ["US_Vermont", "US_Delaware"]
    assert len(asked) == 2
    [note] = notes
    assert "europe/germany/bayern" in note and "no CoMaps map" in note


def test_an_installed_map_asks_nothing(tmp_path: Path) -> None:
    pins = load_pins(CATALOG)
    installed = tmp_path / "d"
    (installed / "260830").mkdir(parents=True)
    with (installed / "260830" / "US_Delaware.mwm").open("wb") as fh:
        fh.truncate(pins.maps["US_Delaware"].size)

    def head(url: str) -> tuple[int, int]:
        raise AssertionError(f"asked {url}")

    files, _ = resolve_station_maps((DELAWARE,), _catalog(tmp_path), installed=installed, head=head)
    assert [f.id for f in files] == ["US_Delaware"]


@pytest.mark.parametrize("answer", [(404, 0), (200, 1234)])
def test_a_map_the_cdn_no_longer_publishes_refuses_the_plan(
    tmp_path: Path, answer: tuple[int, int]
) -> None:
    with pytest.raises(ComapsError) as caught:
        resolve_station_maps(
            (DELAWARE,), _catalog(tmp_path), installed=tmp_path / "d", head=lambda _u: answer
        )
    text = str(caught.value)
    assert "US_Delaware" in text and "pin expired" in text
    assert "scripts/gen_comaps_pins.py" in text


def test_offline_a_map_not_installed_refuses_by_name(tmp_path: Path) -> None:
    def head(url: str) -> tuple[int, int]:
        raise ComapsError(f"{url} could not be reached: no route")

    with pytest.raises(ComapsError, match="could not be reached"):
        resolve_station_maps((VERMONT,), _catalog(tmp_path), installed=tmp_path / "d", head=head)


# -- through `install --dry-run` ------------------------------------------------


COMAPS_MAPS = """\
name: comaps-maps
version: "station"
summary: CoMaps maps for your regions
categories: [navigation-maps]
install:
  - install:
      method: mwm-regions
      provider: comaps
      licence: ODbL-1.0
      licence_url: https://www.openstreetmap.org/copyright
update:
  probe:
    method: comaps_maps
documentation:
  what_it_does: Keeps CoMaps' map files for the regions in station config.
  why_you_want_it: CoMaps reads its own map format and nothing else.
  upstream_url: https://www.comaps.app/
"""


def _dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    size: int | None = None,
    regions: tuple[str, ...] = (VERMONT,),
    installed: bool = False,
) -> tuple[int, str, str]:
    import importlib

    from hammunition.comaps import CdnProbe
    from hammunition.station import Station, save_station
    from json_support import FIXTURE_CATALOG
    from test_json_install import _machine

    cli = importlib.import_module("hammunition.cli.main")
    _machine(monkeypatch, tmp_path)
    catalog = tmp_path / "catalog"
    shutil.copytree(FIXTURE_CATALOG, catalog)
    shutil.copytree(CATALOG / "data", catalog / "data", dirs_exist_ok=True)
    (catalog / "packages" / "comaps-maps.yaml").write_text(COMAPS_MAPS)
    save_station(
        Station(map_regions=regions),
        path=tmp_path / "xdg_config_home" / "hammunition" / "station.yml",
    )
    pins = load_pins(catalog)

    def head(self: CdnProbe, url: str) -> tuple[int, int]:
        name = url.rsplit("/", 1)[1].removesuffix(".mwm")
        return 200, pins.maps[name].size if size is None else size

    monkeypatch.setattr(CdnProbe, "head", head)
    prefix = tmp_path / "prefix"
    real = cli.SourceBackend
    monkeypatch.setattr(cli, "SourceBackend", lambda *a, **k: real(*a, **{**k, "prefix": prefix}))
    if installed:
        where = prefix / "share/hammunition/data/comaps-maps/260830"
        where.mkdir(parents=True)
        with (where / "US_Vermont.mwm").open("wb") as fh:
            fh.truncate(pins.maps["US_Vermont"].size)
    rc = cli.main(["--catalog", str(catalog), "install", "--dry-run", "comaps-maps"])
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_the_dry_run_prints_each_map_with_size_licence_and_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, err = _dry_run(monkeypatch, tmp_path, capsys)
    assert rc == 0, err
    line = next(ln for ln in out.splitlines() if "Fetch CoMaps map US_Vermont" in ln)
    assert "60.9 MB" in line and "ODbL-1.0" in line and "SHA-1" in line


def test_the_dry_run_refuses_an_expired_pin_before_anything_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib

    cli = importlib.import_module("hammunition.cli.main")
    rc, out, err = _dry_run(monkeypatch, tmp_path, capsys, size=731)
    assert rc == cli.EXIT_UNPLANNABLE
    assert "pin expired" in err and "Nothing was changed" in err
    assert "Fetch CoMaps map" not in out


def test_the_dry_run_names_a_region_with_no_comaps_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, err = _dry_run(
        monkeypatch, tmp_path, capsys, regions=(VERMONT, "europe/germany/bayern")
    )
    assert rc == 0, err
    assert "europe/germany/bayern" in out and "no CoMaps map" in out


def test_with_no_regions_set_the_unit_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib

    cli = importlib.import_module("hammunition.cli.main")
    rc, _out, err = _dry_run(monkeypatch, tmp_path, capsys, regions=())
    assert rc == cli.EXIT_UNPLANNABLE
    assert "no map regions set" in err


def test_a_map_installed_at_its_pin_reads_already_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, err = _dry_run(monkeypatch, tmp_path, capsys, size=1, installed=True)
    assert rc == 0, err
    assert "Fetch CoMaps map" not in out
    line = next(ln for ln in out.splitlines() if "comaps-maps" in ln)
    assert "already installed" in line


def test_uninstall_removes_the_maps_with_their_directory(tmp_path: Path) -> None:
    from hammunition.distro import Target
    from hammunition.state.uninstall import RemovalPaths, plan_removal

    paths = RemovalPaths(
        prefix=tmp_path / "prefix",
        venv_root=tmp_path / "venvs",
        bin_dir=tmp_path / "bin",
        applications_dir=tmp_path / "applications",
    )
    m = _unit()
    backend = ComapsMapsBackend(
        fetcher=Fetcher(tmp_path / "cache", transport=_Transport(BODY)),
        prefix=paths.prefix,
        files=[_file(BODY)],
    )
    for step in backend.steps(m, _block(m)):
        if isinstance(step, Action):
            step.perform()
    plan = plan_removal(
        ["comaps-maps"],
        catalog={"comaps-maps": m},
        profiles={},
        target=Target(distro="debian", version="13", arch="x86_64"),
        attributed=frozenset(),
        states={},
        paths=paths,
    )
    directory = paths.prefix / "share/hammunition/data/comaps-maps"
    assert (directory / "260830" / "US_Vermont.mwm").is_file()
    assert [(a.kind, a.path, a.basis) for a in plan.artifacts["comaps-maps"]] == [
        ("tree", directory, "namespaced")
    ]
