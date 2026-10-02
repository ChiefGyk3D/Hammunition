# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A publisher outage at plan time retries, then defers by name (#200).

Synthetic regions and sheets, fake probes that answer from a script, no
network and no real sleep (``conftest`` stubs the policy's sleep).
"""

from __future__ import annotations

import json
import shutil
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.kiwix import resolve_station_books
from hammunition.copernicus import CopernicusError, TileFile
from hammunition.geofabrik import GeofabrikError
from hammunition.kiwix import KiwixError
from hammunition.retry import (
    OUTAGE_HINT,
    Outages,
    PublisherUnavailable,
    RetryingProbe,
    RetryPolicy,
)
from hammunition.terrain_plan import resolve_terrain
from hammunition.topo_plan import MemoProbe, poly_url, resolve_topo
from hammunition.ustopo import INDEX_REMEDY, UstopoError
from test_topo_cli import _catalog as _topo_catalog
from test_topo_plan import (
    ALPHA,
    BETA,
    INDEX,
    LEMURIA,
    OCEANIA,
    OUTLINE,
    QuadProbe,
    _ok,
)

A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
CATALOG = Path(__file__).resolve().parent.parent / "catalog"


class Recorder:
    def __init__(self) -> None:
        self.said: list[str] = []

    def policy(self) -> RetryPolicy:
        return RetryPolicy(sleep=lambda _s: None, notify=self.said.append)


def _timeout_error(url: str) -> GeofabrikError:
    err = GeofabrikError(f"{url} could not be fetched: timed out")
    err.__cause__ = urllib.error.URLError(TimeoutError("timed out"))
    return err


class FlakyOutlines:
    """Geofabrik: the oceania outline answers, the lemuria one never does."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:  # pragma: no cover
        raise AssertionError("outlines are not HEADed")

    def text(self, url: str) -> str:
        self.asked.append(url)
        if url == poly_url(LEMURIA[0]):
            raise _timeout_error(url)
        return OUTLINE


class Flaky:
    """A bucket whose answer for each URL is a script: (status, size, etag)."""

    def __init__(self, scripts: dict[str, list[tuple[int, int, str | None]]]) -> None:
        self.scripts = scripts
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        script = self.scripts[url]
        return script.pop(0) if len(script) > 1 else script[0]


# ---------------------------------------------------------------------------
# The resolvers
# ---------------------------------------------------------------------------


def test_a_sheet_that_answers_503_twice_then_200_resolves_with_two_retry_lines(
    tmp_path: Path,
) -> None:
    rec = Recorder()
    ok = (200, ALPHA.size, f'"{ALPHA.etag}"')
    bucket = Flaky({ALPHA.url: [(503, 0, None), (503, 0, None), ok]})
    outline = RetryingProbe(FlakyOutlines(), rec.policy())
    got, _ = resolve_topo(
        [OCEANIA],
        installed=tmp_path,
        index=INDEX,
        region_probe=outline,
        quad_probe=RetryingProbe(_Both(bucket, QuadProbe(_ok(BETA))), rec.policy()),
    )
    assert ALPHA in got.fetch and got.deferred == ()
    assert len(rec.said) == 2 and "attempt 2 of 3" in rec.said[0]


class _Both:
    """Alpha from a script, anything else from a plain probe."""

    def __init__(self, scripted: Flaky, rest: QuadProbe) -> None:
        self.scripted, self.rest = scripted, rest

    def head(self, url: str) -> tuple[int, int, str | None]:
        return (self.scripted if url in self.scripted.scripts else self.rest).head(url)


def _down_alpha() -> Any:
    return _Both(Flaky({ALPHA.url: [(503, 0, None)]}), QuadProbe(_ok(BETA)))


def test_a_sheet_that_answers_503_forever_is_deferred_and_the_rest_resolves(
    tmp_path: Path,
) -> None:
    rec = Recorder()
    outages = Outages()
    report = outages.reporter("usgs-ustopo", requested=False)
    assert report is not None
    got, _ = resolve_topo(
        [OCEANIA],
        installed=tmp_path,
        index=INDEX,
        region_probe=FlakyOutlines(),
        quad_probe=RetryingProbe(_down_alpha(), rec.policy()),
        on_outage=report,
    )
    assert got.fetch == (BETA,) and got.deferred == (ALPHA,)
    assert [o.item for o in outages.items] == [ALPHA.name]
    assert outages.items[0].answer == "HTTP 503"
    assert len(rec.said) == 2, "three attempts, two retries"


def test_the_same_outage_for_a_typed_unit_refuses_with_the_outage_wording(
    tmp_path: Path,
) -> None:
    rec = Recorder()
    with pytest.raises(UstopoError) as caught:
        resolve_topo(
            [OCEANIA],
            installed=tmp_path,
            index=INDEX,
            region_probe=FlakyOutlines(),
            quad_probe=RetryingProbe(_down_alpha(), rec.policy()),
        )
    text = str(caught.value)
    assert "not answering right now" in text and "HTTP 503" in text and OUTAGE_HINT in text
    assert INDEX_REMEDY not in text, "an outage is not a stale index"


def test_a_404_on_a_listed_sheet_keeps_the_stale_index_remedy_and_is_not_retried(
    tmp_path: Path,
) -> None:
    rec = Recorder()
    outages = Outages()
    bucket = Flaky({ALPHA.url: [(404, 0, None)]})
    with pytest.raises(UstopoError) as caught:
        resolve_topo(
            [OCEANIA],
            installed=tmp_path,
            index=INDEX,
            region_probe=FlakyOutlines(),
            quad_probe=RetryingProbe(_Both(bucket, QuadProbe(_ok(BETA))), rec.policy()),
            on_outage=outages.reporter("usgs-ustopo", requested=False),
        )
    text = str(caught.value)
    assert INDEX_REMEDY in text and "answered HTTP 404, not 200" in text
    assert "not answering" not in text
    assert bucket.asked == [ALPHA.url] and rec.said == [] and not outages


def test_one_outline_outage_defers_that_region_in_every_unit_and_asks_once() -> None:
    """The lemuria outline never answers. Terrain and US Topo both need it:
    each defers lemuria's items and resolves oceania; the dead request is made
    three times in all (the retries of the first unit), not three per unit."""
    rec = Recorder()
    inner = FlakyOutlines()
    memo = MemoProbe(RetryingProbe(inner, rec.policy()))
    outages = Outages()
    terrain_report = outages.reporter("dem-copernicus", requested=False)
    topo_report = outages.reporter("usgs-ustopo", requested=False)
    tile = TileFile(A, "https://example.invalid/t", 1, "0" * 32, None)

    class Tiles:
        def head(self, url: str) -> tuple[int, int, str | None]:
            return 200, 1, '"0123456789abcdef0123456789abcdef"'

    dem = resolve_terrain(
        [OCEANIA, LEMURIA],
        installed=Path("/nonexistent/dem"),
        tile_list=frozenset({A}),
        pins={},
        region_probe=memo,
        tile_probe=Tiles(),
        on_outage=terrain_report,
    )
    topo, _ = resolve_topo(
        [OCEANIA, LEMURIA],
        installed=Path("/nonexistent/topo"),
        index=INDEX,
        region_probe=memo,
        quad_probe=QuadProbe(_ok(ALPHA, BETA)),
        on_outage=topo_report,
    )
    assert tile is not None
    assert [e.region for e in dem.regions] == [OCEANIA[0]]
    assert [e.region for e in topo.regions] == [OCEANIA[0]]
    assert topo.fetch == (ALPHA, BETA), "oceania's sheets are unaffected"
    assert [(o.unit, o.item) for o in outages.items] == [
        ("dem-copernicus", f"{LEMURIA[0]} (its outline)"),
        ("usgs-ustopo", f"{LEMURIA[0]} (its outline)"),
    ]
    assert inner.asked.count(poly_url(LEMURIA[0])) == 3
    assert inner.asked.count(poly_url(OCEANIA[0])) == 1
    assert all(o.answer == "timed out" for o in outages.items)


def test_an_outline_outage_for_a_typed_unit_refuses_naming_the_region(tmp_path: Path) -> None:
    rec = Recorder()
    with pytest.raises(UstopoError, match="atlantis/lemuria: its outline could not be read"):
        resolve_topo(
            [LEMURIA],
            installed=tmp_path,
            index=INDEX,
            region_probe=RetryingProbe(FlakyOutlines(), rec.policy()),
            quad_probe=QuadProbe({}),
        )


def test_terrain_defers_a_tile_and_refuses_it_when_typed() -> None:
    rec = Recorder()

    class Down:
        def head(self, url: str) -> tuple[int, int, str | None]:
            return 503, 0, None

    kwargs: dict[str, Any] = {
        "installed": Path("/nonexistent/dem"),
        "tile_list": frozenset({A}),
        "pins": {},
        "region_probe": FlakyOutlines(),
        "tile_probe": RetryingProbe(Down(), rec.policy()),
    }
    outages = Outages()
    got = resolve_terrain([OCEANIA], on_outage=outages.reporter("dem", requested=False), **kwargs)
    assert got.fetch == () and [o.item for o in outages.items] == [A]
    with pytest.raises(CopernicusError, match="not answering right now"):
        resolve_terrain([OCEANIA], **kwargs)


def test_kiwix_books_defer_an_outage_and_refuse_it_when_typed(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    (root / "data").mkdir(parents=True)
    for name in ("kiwix-books.yaml", "kiwix-pins.yaml"):
        shutil.copy(CATALOG / "data" / name, root / "data" / name)
    ham = "ham.stackexchange.com_en_all"

    def head(url: str) -> int:
        raise PublisherUnavailable(url, "HTTP 503", 3)

    outages = Outages()
    got = resolve_station_books(
        (ham,),
        root,
        installed=tmp_path / "d",
        head=head,
        on_outage=outages.reporter("reference-books", requested=False),
    )
    assert got == [] and [o.item for o in outages.items] == [ham]
    with pytest.raises(KiwixError, match="not answering right now"):
        resolve_station_books((ham,), root, installed=tmp_path / "d", head=head)


# ---------------------------------------------------------------------------
# End to end through `install --dry-run`
# ---------------------------------------------------------------------------

PROFILE = """\
name: fixture-topo
summary: US Topo sheets, as a profile
packages: [usgs-ustopo]
documentation:
  what_it_installs: A fixture unit standing in for the navigation maps.
  why_together: The deferral needs a profile member it can defer.
  deliberately_excludes: Everything real.
  manual_configuration: Nothing, because it is a fixture.
"""


def _cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, answers: list[tuple[int, int, str | None]]
) -> tuple[Any, str, Any]:
    from test_topo_cli import _cli as topo_cli

    cli, probe = topo_cli(monkeypatch, tmp_path)
    catalog = _topo_catalog(tmp_path)
    (catalog / "profiles").mkdir(exist_ok=True)
    (catalog / "profiles" / "fixture-topo.yaml").write_text(PROFILE)
    script = list(answers)

    def head(url: str) -> tuple[int, int, str | None]:
        probe.asked.append(url)
        return script.pop(0) if len(script) > 1 else script[0]

    probe.head = head  # type: ignore[method-assign]
    return cli, str(catalog), probe


GOOD = (200, 9_000_000, '"0123456789abcdef0123456789abcdef-2"')
DOWN = (503, 0, None)


def test_dry_run_a_flaky_sheet_that_recovers_installs_it_and_says_so_on_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HAMMUNITION_PROGRESS", "1")
    cli, catalog, probe = _cli(monkeypatch, tmp_path, [DOWN, DOWN, GOOD])
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "fixture-topo"]) == 0
    captured = capsys.readouterr()
    assert "Fetch US Topo quad ZZ_Alpha_20240101" in captured.out
    assert "Will NOT happen" not in captured.out
    retries = [ln for ln in captured.err.splitlines() if "retrying" in ln]
    assert retries == [
        "prd-tnm.s3.amazonaws.com: HTTP 503; retrying (attempt 2 of 3) in 1 s",
        "prd-tnm.s3.amazonaws.com: HTTP 503; retrying (attempt 3 of 3) in 3 s",
    ]
    assert "attempt 2 of 3" in retries[0] and "attempt 3 of 3" in retries[1]
    assert len(probe.asked) == 3


def test_dry_run_a_profile_member_in_an_outage_is_deferred_not_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, catalog, probe = _cli(monkeypatch, tmp_path, [DOWN])
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "fixture-topo"]) == 0
    out = capsys.readouterr().out
    assert "Will NOT happen" in out
    assert "usgs-ustopo" in out and "ZZ_Alpha_20240101" in out
    flat = " ".join(out.split())
    assert "prd-tnm.s3.amazonaws.com answered HTTP 503" in flat
    assert "run the same command again" in flat
    assert "Fetch US Topo quad" not in out
    assert len(probe.asked) == 3
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "--json", "fixture-topo"]) == 0
    doc = json.loads(capsys.readouterr().out)
    deferrals = doc["install"]["deferrals"]
    assert [d["subject"] for d in deferrals] == ["usgs-ustopo"]
    assert deferrals[0]["kind"] == "package" and "HTTP 503" in deferrals[0]["why"]
    # The JSON run's stderr tee is flushed on collection: do it while capsys is open.
    import gc

    gc.collect()


def test_dry_run_the_same_unit_typed_by_name_refuses_in_full(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, catalog, _ = _cli(monkeypatch, tmp_path, [DOWN])
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "usgs-ustopo"]) == 2
    err = capsys.readouterr().err
    assert "not answering right now" in err and "HTTP 503" in err
    assert "gen_ustopo_index.py" not in err and "Nothing was changed." in err


def test_dry_run_a_404_is_still_a_stale_index_even_for_a_profile_member(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, catalog, probe = _cli(monkeypatch, tmp_path, [(404, 0, None)])
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "fixture-topo"]) == 2
    err = capsys.readouterr().err
    assert "gen_ustopo_index.py --fetch" in err and "not answering" not in err
    assert len(probe.asked) == 1


# ---------------------------------------------------------------------------
# What the backends do with a deferred item: nothing installed is lost for it
# ---------------------------------------------------------------------------


def test_an_older_edition_survives_while_its_newer_one_is_deferred(tmp_path: Path) -> None:
    """The old edition is installed, the new one's publisher is down: the old
    sheet is neither removed as unwanted nor replaced."""
    from hammunition.backends.regions import data_root
    from hammunition.backends.topo import TIF, RegionQuads, TopoQuadsBackend, TopoResolution
    from hammunition.fetch import Fetcher
    from hammunition.ustopo import Quad
    from test_topo_backend import _actions, _block, manifest

    md5 = "0123456789abcdef0123456789abcdef"
    new_alpha = Quad(0.0, 0.0, 0.125, 0.125, 10, md5, "ZZ/ZZ_Alpha_20260101")
    data = data_root(tmp_path) / "usgs-ustopo"
    data.mkdir(parents=True)
    (data / f"{ALPHA.name}{TIF}").write_bytes(b"old")
    region = RegionQuads(*OCEANIA, (new_alpha,))
    backend = TopoQuadsBackend(
        fetcher=Fetcher(cache_dir=tmp_path / "cache"),
        prefix=tmp_path,
        resolution=TopoResolution(regions=(region,), deferred=(new_alpha,)),
    )
    m = manifest()
    for step in _actions(backend.steps(m, _block(m))):
        step.perform()
    assert (data / f"{ALPHA.name}{TIF}").is_file()
    assert not any(s.kind == "fetch" for s in _actions(backend.steps(m, _block(m))))


def test_a_deferred_book_stops_the_unit_removing_what_is_installed(tmp_path: Path) -> None:
    from hammunition.backends.kiwix import KiwixBooksBackend
    from hammunition.backends.regions import data_root
    from test_kiwix_backend import _manifest

    out = data_root(tmp_path) / "kiwix-library"
    out.mkdir(parents=True)
    older = out / "ham.stackexchange.com_en_all_2026-02.zim"
    older.write_bytes(b"older")
    from hammunition.fetch import Fetcher

    def kinds(keep: bool) -> list[str]:
        backend = KiwixBooksBackend(
            fetcher=Fetcher(cache_dir=tmp_path / "cache"),
            prefix=tmp_path,
            files=(),
            keep_unlisted=keep,
        )
        m = _manifest()
        steps: list[Any] = backend.steps(m, m.install[0].install)  # type: ignore[arg-type]
        return [s.kind for s in steps]

    assert kinds(False) == ["remove-data"]
    assert kinds(True) == []


def test_a_deferred_terrain_tile_is_not_drawn_converted_or_built_over(tmp_path: Path) -> None:
    from hammunition.backends.dem import DemResolution, RegionTiles
    from test_gdal_dem import _converter as gdal_converter
    from test_gdal_dem import manifest as gdal_manifest
    from test_splat_sdf import _converter as splat_converter
    from test_splat_sdf import manifest as splat_manifest

    other = "Copernicus_DSM_COG_10_N01_00_E000_00_DEM"
    region = RegionTiles("atlantis/oceania", "atlantis-oceania", (A, other), 0)
    resolution = DemResolution(regions=(region,), deferred=(other,))
    assert resolution.tiles == (A, other) and resolution.available == (A,)
    gdal = gdal_converter(tmp_path, resolution=resolution)
    assert gdal.pending(gdal_manifest()) == [A]
    splat = splat_converter(tmp_path)
    object.__setattr__(splat, "resolution", resolution)
    assert splat.pending(splat_manifest()) == [A]


def test_a_deferred_map_stops_the_comaps_unit_removing_what_is_installed(tmp_path: Path) -> None:
    from hammunition.backends.comaps_maps import MWM, ComapsMapsBackend
    from hammunition.backends.regions import data_root
    from hammunition.fetch import Fetcher
    from test_comaps_maps import _block as comaps_block
    from test_comaps_maps import _unit as comaps_unit

    m = comaps_unit()
    out = data_root(tmp_path) / m.name / "250101"
    out.mkdir(parents=True)
    (out / f"US_Old{MWM}").write_bytes(b"old")

    def kinds(keep: bool) -> list[str]:
        backend = ComapsMapsBackend(
            fetcher=Fetcher(cache_dir=tmp_path / "cache"),
            prefix=tmp_path,
            files=(),
            keep_unlisted=keep,
        )
        steps: list[Any] = backend.steps(m, comaps_block(m))
        return [s.kind for s in steps]

    assert kinds(False) == ["remove-data"]
    assert kinds(True) == []
