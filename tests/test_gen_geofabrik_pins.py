# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Geofabrik pin list is generated, and its check re-probes sizes only.

`scripts/gen_geofabrik_pins.py` downloads each pinned region's yearly and
monthly snapshot, hashes it, discards the bytes and writes
`catalog/data/geofabrik-pins.yaml`. A real pass is about 10 GB, so every
test here injects the download and the HEAD probe; the suite blocks
non-loopback sockets and nothing in this file may reach Geofabrik.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "gen_geofabrik_pins.py"
COMMITTED = REPO_ROOT / "catalog" / "data" / "geofabrik-pins.yaml"

VT = "north-america/us/vermont"
NH = "north-america/us/new-hampshire"
TODAY = date(2026, 9, 27)


def _gen() -> Any:
    spec = importlib.util.spec_from_file_location("gen_geofabrik_pins", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _url(region: str, snapshot: str) -> str:
    return f"https://download.geofabrik.de/{region}-{snapshot}.osm.pbf"


class FakeServer:
    """Serves bytes by URL in chunks; records every URL asked for."""

    def __init__(self, files: dict[str, bytes], heads: dict[str, tuple[int, int | None]]) -> None:
        self.files, self.heads = files, heads
        self.streamed: list[str] = []
        self.headed: list[str] = []

    def stream(self, url: str) -> Iterator[bytes]:
        self.streamed.append(url)
        if url not in self.files:
            raise OSError(f"{url} returned HTTP 404")
        data = self.files[url]
        for i in range(0, len(data), 7):
            yield data[i : i + 7]

    def head(self, url: str) -> tuple[int, int | None]:
        self.headed.append(url)
        return self.heads.get(url, (404, None))


def _files(regions: Iterable[str]) -> dict[str, bytes]:
    out = {}
    for r in regions:
        for snap in ("260101", "260901"):
            out[_url(r, snap)] = f"{r}@{snap}".encode() * 3
    return out


# -- the region list --------------------------------------------------------


def test_the_region_list_is_the_fifty_states_and_dc() -> None:
    gen = _gen()
    regions = list(gen.REGIONS)
    assert len(regions) == 51
    assert len(set(regions)) == 51
    assert all(r.startswith("north-america/us/") for r in regions)
    assert "north-america/us/district-of-columbia" in regions
    assert VT in regions and NH in regions
    assert "north-america/us/california" in regions


def test_every_region_matches_the_path_pattern() -> None:
    gen = _gen()
    bad = [r for r in gen.REGIONS if not gen.REGION_PATTERN.fullmatch(r)]
    assert not bad


# -- which snapshots ---------------------------------------------------------


def test_snapshots_are_this_years_first_of_january_and_this_months_first() -> None:
    assert _gen().snapshots(TODAY) == ["260101", "260901"]


def test_in_january_the_two_snapshots_are_one_file() -> None:
    assert _gen().snapshots(date(2027, 1, 14)) == ["270101"]


# -- generation ---------------------------------------------------------------


def test_generate_streams_hashes_and_records_each_snapshot() -> None:
    gen = _gen()
    files = _files([VT])
    server = FakeServer(files, {})
    rows = gen.generate([VT], today=TODAY, stream=server.stream)
    assert rows == [
        {
            "region": VT,
            "snapshot": snap,
            "size": len(files[_url(VT, snap)]),
            "sha256": hashlib.sha256(files[_url(VT, snap)]).hexdigest(),
            "measured": "2026-09-27",
        }
        for snap in ("260101", "260901")
    ]
    assert server.streamed == [_url(VT, "260101"), _url(VT, "260901")]


def test_a_file_that_will_not_download_is_an_error_naming_the_url() -> None:
    gen = _gen()
    server = FakeServer({_url(VT, "260101"): b"x"}, {})
    with pytest.raises(SystemExit) as raised:
        gen.generate([VT], today=TODAY, stream=server.stream)
    assert _url(VT, "260901") in str(raised.value)


def test_an_empty_download_is_refused() -> None:
    """A zero-byte body hashes fine and pins nothing real (D-031)."""
    gen = _gen()
    server = FakeServer({_url(VT, "260101"): b"", _url(VT, "260901"): b"x"}, {})
    with pytest.raises(SystemExit) as raised:
        gen.generate([VT], today=TODAY, stream=server.stream)
    assert _url(VT, "260101") in str(raised.value)


def test_render_carries_the_header_and_round_trips(tmp_path: Path) -> None:
    gen = _gen()
    rows = gen.generate([VT], today=TODAY, stream=FakeServer(_files([VT]), {}).stream)
    text = gen.render(rows)
    assert "SPDX-License-Identifier: CC0-1.0" in text
    assert "GENERATED by scripts/gen_geofabrik_pins.py" in text
    data = yaml.safe_load(text)
    assert data["pins"] == rows
    # A snapshot is a string: '060101' must not become an integer.
    assert all(isinstance(r["snapshot"], str) for r in data["pins"])


def test_render_of_no_pins_is_an_empty_list() -> None:
    assert yaml.safe_load(_gen().render([]))["pins"] == []


def test_main_writes_every_region_by_default(tmp_path: Path) -> None:
    gen = _gen()
    out = tmp_path / "pins.yaml"
    server = FakeServer(_files(gen.REGIONS), {})
    assert gen.main([], stream=server.stream, today=TODAY, out=out) == 0
    pins = yaml.safe_load(out.read_text())["pins"]
    assert len(pins) == 51 * 2
    assert len(server.streamed) == 51 * 2


def test_region_flag_replaces_only_those_regions_and_keeps_the_rest(tmp_path: Path) -> None:
    gen = _gen()
    out = tmp_path / "pins.yaml"
    old = [
        {
            "region": NH,
            "snapshot": "260101",
            "size": 5,
            "sha256": "b" * 64,
            "measured": "2026-01-02",
        },
        {
            "region": VT,
            "snapshot": "250101",
            "size": 5,
            "sha256": "c" * 64,
            "measured": "2025-01-02",
        },
    ]
    out.write_text(gen.render(old))
    server = FakeServer(_files([VT]), {})
    assert gen.main(["--region", VT], stream=server.stream, today=TODAY, out=out) == 0
    pins = yaml.safe_load(out.read_text())["pins"]
    assert {(p["region"], p["snapshot"]) for p in pins} == {
        (NH, "260101"),
        (VT, "260101"),
        (VT, "260901"),
    }
    assert server.streamed == [_url(VT, "260101"), _url(VT, "260901")]


def test_region_flag_refuses_a_region_not_in_the_list(tmp_path: Path) -> None:
    gen = _gen()
    with pytest.raises(SystemExit) as raised:
        gen.main(
            ["--region", "europe/monaco"],
            stream=FakeServer({}, {}).stream,
            today=TODAY,
            out=tmp_path / "p.yaml",
        )
    assert "europe/monaco" in str(raised.value)
    assert "REGIONS" in str(raised.value)


# -- --check -----------------------------------------------------------------


def _pinned(tmp_path: Path) -> tuple[Any, Path, list[dict[str, Any]]]:
    gen = _gen()
    rows = gen.generate([VT, NH], today=TODAY, stream=FakeServer(_files([VT, NH]), {}).stream)
    out = tmp_path / "pins.yaml"
    out.write_text(gen.render(rows))
    return gen, out, rows


def test_check_passes_when_every_pinned_url_answers_200_at_its_size(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gen, out, rows = _pinned(tmp_path)
    heads = {_url(r["region"], r["snapshot"]): (200, r["size"]) for r in rows}
    server = FakeServer({}, heads)
    before = out.read_text()
    assert gen.main(["--check"], head=server.head, out=out) == 0
    assert "up to date" in capsys.readouterr().out
    assert out.read_text() == before
    assert server.streamed == []  # HEAD only, never a download
    assert sorted(server.headed) == sorted(heads)


def test_check_names_a_pin_whose_url_no_longer_answers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gen, out, rows = _pinned(tmp_path)
    heads = {_url(r["region"], r["snapshot"]): (200, r["size"]) for r in rows}
    gone = _url(VT, "260901")
    heads[gone] = (404, None)
    assert gen.main(["--check"], head=FakeServer({}, heads).head, out=out) == 1
    text = capsys.readouterr().out
    assert gone in text and "404" in text
    assert "gen_geofabrik_pins.py" in text  # the command to regenerate


def test_check_names_a_pin_whose_size_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gen, out, rows = _pinned(tmp_path)
    heads = {_url(r["region"], r["snapshot"]): (200, r["size"]) for r in rows}
    moved = _url(NH, "260101")
    heads[moved] = (200, 999)
    assert gen.main(["--check"], head=FakeServer({}, heads).head, out=out) == 1
    text = capsys.readouterr().out
    assert moved in text and "999" in text


def test_check_treats_a_redirect_as_a_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dated file never redirects; one that does is not the file we pinned."""
    gen, out, rows = _pinned(tmp_path)
    heads = {_url(r["region"], r["snapshot"]): (200, r["size"]) for r in rows}
    heads[_url(VT, "260101")] = (302, None)
    assert gen.main(["--check"], head=FakeServer({}, heads).head, out=out) == 1
    assert "302" in capsys.readouterr().out


def test_check_refuses_a_malformed_row(tmp_path: Path) -> None:
    gen = _gen()
    out = tmp_path / "pins.yaml"
    bad = [{"region": VT, "snapshot": "260101", "size": 5, "sha256": "short", "measured": "x"}]
    out.write_text(gen.render(bad))
    with pytest.raises(SystemExit) as raised:
        gen.main(["--check"], head=FakeServer({}, {}).head, out=out)
    assert "sha256" in str(raised.value)


def test_check_of_an_empty_pin_list_needs_no_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gen = _gen()
    out = tmp_path / "pins.yaml"
    out.write_text(gen.render([]))
    server = FakeServer({}, {})
    assert gen.main(["--check"], head=server.head, out=out) == 0
    assert server.headed == []
    assert "up to date" in capsys.readouterr().out


def test_check_refuses_a_file_without_the_generated_header(tmp_path: Path) -> None:
    gen = _gen()
    out = tmp_path / "pins.yaml"
    out.write_text("pins: []\n")
    with pytest.raises(SystemExit) as raised:
        gen.main(["--check"], head=FakeServer({}, {}).head, out=out)
    assert "generated" in str(raised.value).lower()


# -- the committed file ---------------------------------------------------------


def test_the_committed_file_is_well_formed_and_generated() -> None:
    gen = _gen()
    text = COMMITTED.read_text()
    assert "GENERATED by scripts/gen_geofabrik_pins.py" in text
    rows = gen.parse(text)
    assert isinstance(rows, list)
    for row in rows:
        assert row["region"] in gen.REGIONS


def test_the_committed_file_loads_in_the_shape_load_pins_reads() -> None:
    """`hammunition.geofabrik.load_pins` (another task) reads
    ``data.get("pins", [])`` and each row's region, snapshot, size and sha256."""
    data = yaml.safe_load(COMMITTED.read_text()) or {}
    for row in data.get("pins", []):
        str(row["region"]), str(row["snapshot"]), int(row["size"]), str(row["sha256"])
