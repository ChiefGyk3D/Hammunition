# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The infrastructure layers as GeoJSON overlays on the browser map.  D-075.

Each layer the operator wrote with ``maps infra`` is one GeoJSON in their
overlay directory; ``reference serve`` finds them when it starts, serves
each by its exact name and lists them, and the page draws each as a toggled
circle layer with its licence as the source's attribution. A new pin or a
new fetch never rebuilds the tiles. Synthetic points only.
"""

from __future__ import annotations

import http.client
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from threading import Thread

import pytest

from hammunition import infra, map_style
from hammunition.infra import InfraLayer, Point
from hammunition.map_page import OVERLAYS, STYLE_LICENCE, find_map, map_page
from hammunition.reference import make_server
from test_map_serve import _data, _get


def _overlays(tmp_path: Path) -> Path:
    where = tmp_path / "overlays" / "infra"
    for layer_id, name, licence in (
        ("osm-medical", "Medical (OpenStreetMap, ODbL, 2026-09-30)", infra.OSM_LICENCE),
        ("nwr", "NOAA Weather Radio (unverified, fetched 2026-10-01)", "NOAA/NWS, public domain"),
    ):
        infra.write_layer(
            where,
            InfraLayer(
                layer_id, name, licence, "test", date(2026, 10, 1), (Point("P", "k", 38.7, -75.5),)
            ),
        )
    return where


@pytest.fixture
def served(tmp_path: Path) -> Iterator[int]:
    shelf = find_map(_data(tmp_path), overlays=_overlays(tmp_path))
    server = make_server(0, "<html>landing</html>", [], map_shelf=shelf, position_port=10111)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def test_every_layer_is_listed_with_its_name_and_licence(served: int) -> None:
    status, headers, body = _get(served, OVERLAYS)
    assert status == 200 and headers["Content-Type"] == "application/json"
    assert json.loads(body) == [
        {
            "id": "osm-medical",
            "name": "Medical (OpenStreetMap, ODbL, 2026-09-30)",
            "licence": infra.OSM_LICENCE,
            "url": "/map/overlays/infra-osm-medical.geojson",
        },
        {
            "id": "nwr",
            "name": "NOAA Weather Radio (unverified, fetched 2026-10-01)",
            "licence": "NOAA/NWS, public domain",
            "url": "/map/overlays/infra-nwr.geojson",
        },
    ]


def test_each_layer_is_served_as_geojson(served: int) -> None:
    status, headers, body = _get(served, "/map/overlays/infra-nwr.geojson")
    assert status == 200 and headers["Content-Type"] == "application/geo+json"
    assert json.loads(body)["features"][0]["properties"]["name"] == "P"


def test_the_style_licence_is_served_as_text(served: int) -> None:
    status, headers, body = _get(served, STYLE_LICENCE)
    assert status == 200 and headers["Content-Type"].startswith("text/plain")
    assert b"Copyright Open Infrastructure Map contributors" in body


@pytest.mark.parametrize(
    "path",
    [
        "/map/overlays/infra-osm-medical.gpx",
        "/map/overlays/../infra/infra-nwr.geojson",
        "/map/overlays/x.geojson",
    ],
)
def test_nothing_else_of_the_directory_is_served(served: int, path: str) -> None:
    assert _get(served, path)[0] == 404


def test_a_link_a_foreign_file_or_an_unreadable_one_is_not_listed(tmp_path: Path) -> None:
    where = _overlays(tmp_path)
    elsewhere = tmp_path / "secret.geojson"
    elsewhere.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    (where / "infra-fcc-towers.geojson").symlink_to(elsewhere)
    (where / "infra-eia-plants.geojson").write_text("not json")
    (where / "notes.geojson").write_text("{}")
    shelf = find_map(_data(tmp_path), overlays=where)
    assert [o.layer_id for o in shelf.overlays] == ["osm-medical", "nwr"]


def test_no_overlay_directory_lists_nothing(tmp_path: Path) -> None:
    shelf = find_map(_data(tmp_path), overlays=tmp_path / "absent")
    assert shelf.overlays == ()
    assert find_map(_data(tmp_path / "b")).overlays == ()


def test_the_page_loads_the_list_draws_the_infra_tiles_and_credits_the_style() -> None:
    page = map_page(position_port=10110)
    assert OVERLAYS in page
    assert json.dumps(map_style.CREDIT)[1:-1] in page
    assert STYLE_LICENCE in page
    assert '"source-layer": "infra"' in page
    assert "addSource" in page and "geojson" in page
    assert "http" not in page.replace("http://127.0.0.1:", "").replace(
        "https://openmaptiles.org/", ""
    ).replace("https://www.openstreetmap.org/copyright", "")


def test_reference_serve_reads_the_operators_overlay_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    cli = importlib.import_module("hammunition.cli.main")
    from hammunition import reference

    seen: dict[str, object] = {}

    def run(port: int, **kw: object) -> int:
        seen.update(kw)
        return 0

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(cli, "DEFAULT_PREFIX", tmp_path / "prefix")
    monkeypatch.setattr(reference, "run", run)
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    _overlays(tmp_path / "xdg" / "hammunition")
    assert cli.main(["reference", "serve"]) == 0
    shelf = seen["map_shelf"]
    assert [o.layer_id for o in shelf.overlays] == ["osm-medical", "nwr"]  # type: ignore[attr-defined]


def test_the_server_refuses_another_host_for_the_overlays(served: int) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", served, timeout=5)
    try:
        conn.request("GET", OVERLAYS, headers={"Host": "evil.example:80"})
        assert conn.getresponse().status == 403
    finally:
        conn.close()
