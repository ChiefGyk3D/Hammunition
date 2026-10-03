# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``tar1090`` unit and the verb's wiring of it.  D-071 (2026-10-02).

The unit is a pinned archive's ``html/`` as data; the page is
``hammunition reference serve``'s. These tests hold the two together: the
directory the manifest extracts into is the one the server reads, the pin is
a full commit, and the verb takes ``--readsb-json`` and says what it serves.
Stand-in files only.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Sequence
from pathlib import Path

import pytest

from hammunition import aircraft_page
from hammunition.aircraft_page import HTML, SRC, UNIT, find_aircraft
from hammunition.manifest.load import load_catalog, load_profiles
from hammunition.manifest.schema import DataInstall
from hammunition.reference import Shelf, landing_page, run

cli = importlib.import_module("hammunition.cli.main")
REPO = Path(__file__).resolve().parent.parent
COMMIT = "e784ee5ae82948f41efe3ef5c235ade0943ab8ff"


def _block() -> DataInstall:
    block = load_catalog(REPO / "catalog" / "packages")[UNIT].install[0].install
    assert isinstance(block, DataInstall)
    return block


def test_the_pin_is_one_full_commit_in_the_url_the_members_and_the_licence_link() -> None:
    block = _block()
    [artifact] = block.artifacts
    assert artifact.url == f"https://github.com/wiedehopf/tar1090/archive/{COMMIT}.tar.gz"
    assert re.fullmatch(r"[0-9a-f]{64}", artifact.sha256)
    assert artifact.format == "tarball" and artifact.size == 2812358
    assert COMMIT in block.licence_url
    assert artifact.members is not None
    assert all(m.startswith(f"tar1090-{COMMIT}/") for m in artifact.members)


def test_the_manifest_extracts_where_the_server_reads() -> None:
    """``into`` is the unit's ``src``; the page is the archive's ``html/``."""
    [artifact] = _block().artifacts
    assert artifact.into == SRC
    assert artifact.members is not None
    assert f"tar1090-{COMMIT}/{HTML}/" in artifact.members
    assert f"tar1090-{COMMIT}/LICENSE" in artifact.members
    assert not any("tar1090-db" in m for m in artifact.members)


def test_it_needs_readsb_and_is_in_the_listening_profile_by_name() -> None:
    manifest = load_catalog(REPO / "catalog" / "packages")[UNIT]
    assert manifest.depends == ["readsb"]
    profile = load_profiles(REPO / "catalog" / "profiles")["listening"]
    assert UNIT in profile.packages and "readsb" in profile.packages
    assert "GPL-2.0-or-later" in _block().licence


def test_the_documentation_says_what_is_not_carried_and_what_is_unmeasured() -> None:
    docs = load_catalog(REPO / "catalog" / "packages")[UNIT].documentation
    assert docs is not None
    text = f"{docs.known_problems} {docs.what_it_does}"
    assert "No aircraft database" in text
    assert "not yet seen with a live receiver" in text
    assert "Content-Security-Policy" in text


def test_the_server_reads_readsbs_debian_directory_by_default() -> None:
    assert aircraft_page.JSON_DIRS[0] == Path("/run/readsb")
    assert aircraft_page.default_json_dir((Path("/nonexistent-a"), Path("/nonexistent-b"))) == Path(
        "/nonexistent-a"
    )


def test_serve_refuses_a_relative_readsb_directory(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["reference", "serve", "--readsb-json", "run/readsb"]) != 0
    assert "absolute directory" in capsys.readouterr().err


class _Child:
    def poll(self) -> int | None:
        return None

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None: ...


def test_run_says_where_the_aircraft_page_is_and_what_it_reads(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / UNIT / SRC / HTML).mkdir(parents=True)
    (data / UNIT / SRC / HTML / "index.html").write_text(f"x {aircraft_page.ANCHOR} y")
    shelf = find_aircraft(data, None, json_dir=tmp_path / "readsb")
    assert shelf is not None
    lines: list[str] = []
    ticks = iter([0])

    def tick() -> None:
        if next(ticks, None) is None:
            raise KeyboardInterrupt

    def spawn(argv: Sequence[str]) -> _Child:
        raise AssertionError("no books: kiwix-serve is not started")

    code = run(
        0,
        shelf=Shelf(books=(), forms=(), dict_client=False, goldendict=False),
        library=tmp_path / "lib.xml",
        spawn=spawn,
        manage=lambda *_: None,
        tick=tick,
        log=lines.append,
        aircraft=shelf,
    )
    assert code == 0
    [line] = [x for x in lines if "aircraft:" in x]
    assert "/aircraft/" in line and str(tmp_path / "readsb") in line and "No basemap" in line


def test_the_landing_page_has_the_aircraft_section_installed_or_not(tmp_path: Path) -> None:
    bare = Shelf(books=(), forms=(), dict_client=False, goldendict=False)
    assert "hammunition install tar1090" in landing_page(bare, kiwix_port=1)
    data = tmp_path / "data"
    (data / UNIT / SRC / HTML).mkdir(parents=True)
    (data / UNIT / SRC / HTML / "index.html").write_text(aircraft_page.ANCHOR)
    shelf = find_aircraft(data, None, json_dir=tmp_path)
    assert 'href="/aircraft/"' in landing_page(bare, kiwix_port=1, aircraft=shelf)
