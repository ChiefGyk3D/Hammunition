# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``register`` install method: the ACMA register fetched, checked by its
own structure, installed, and disclosed as unverified.  D-074, amended
2026-10-01.

Every byte is served from memory by a fake transport; the register is
synthetic (:mod:`acma_support`). No network.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import IO

import pytest

from acma_support import register_bytes
from hammunition import acma
from hammunition.backends import Action, BackendError, DataBackend
from hammunition.fetch import Fetcher
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import ManifestError, PackageManifest, RegisterInstall
from json_support import REPO_ROOT

CATALOG = load_catalog(REPO_ROOT / "catalog" / "packages")
MIRROR = "http://bunker.lan:8080/"
AT_MIRROR = "http://bunker.lan:8080/acma-register/spectra_rrl.zip"


class Routes:
    def __init__(self, routes: dict[str, bytes]) -> None:
        self.routes = routes
        self.requested: list[str] = []

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:
        self.requested.append(url)
        if url not in self.routes:
            raise BackendError(f"{url} returned HTTP 404 (Not Found)")
        yield BytesIO(self.routes[url])


def _unit() -> tuple[PackageManifest, RegisterInstall]:
    manifest = CATALOG["acma-register"]
    block = manifest.install[0].install
    assert isinstance(block, RegisterInstall)
    return manifest, block


def _backend(tmp_path: Path, routes: Routes, mirror: str | None = None) -> DataBackend:
    fetcher = Fetcher(tmp_path / "cache", transport=routes, mirror=mirror)
    return DataBackend(fetcher=fetcher, prefix=tmp_path / "prefix")


def _steps(backend: DataBackend) -> tuple[Action, Action]:
    manifest, block = _unit()
    fetch, install = backend.register_steps(manifest, block)
    assert isinstance(fetch, Action) and isinstance(install, Action)
    return fetch, install


def _dest(tmp_path: Path) -> Path:
    return (
        tmp_path / "prefix" / "share" / "hammunition" / "data" / "acma-register" / "spectra_rrl.zip"
    )


def test_the_catalog_unit_is_a_register_block_in_no_profile() -> None:
    _, block = _unit()
    assert (block.method, block.provider) == ("register", "acma-rrl")
    assert block.licence.startswith("ACMA Register of Radiocommunications Licences")
    assert block.licence.endswith("attribution required")
    profiles = (REPO_ROOT / "catalog" / "profiles").glob("*.yaml")
    assert not [p.name for p in profiles if "acma-register" in p.read_text()]


def test_the_steps_say_unverified_and_the_measured_size(tmp_path: Path) -> None:
    fetch, install = _steps(_backend(tmp_path, Routes({})))
    assert "UNVERIFIED: no checksum is published" in fetch.description
    assert "about 67.5 MB" in fetch.description
    assert "attribution required" in fetch.description
    assert fetch.sources == (acma.URL,)
    assert acma.VERIFIED_BY in fetch.detail
    assert install.kind == "install-data" and install.detail == str(_dest(tmp_path))


def test_a_whole_register_is_installed_and_its_cached_copy_deleted(tmp_path: Path) -> None:
    body = register_bytes(tmp_path)
    fetch, install = _steps(_backend(tmp_path, Routes({acma.URL: body})))
    said = fetch.perform()
    assert said.startswith(f"downloaded {len(body)} bytes, unverified")
    assert "CRC-32" in said
    install.perform()
    assert _dest(tmp_path).read_bytes() == body
    assert not list((tmp_path / "cache").glob("checked-*"))


def test_a_web_page_in_its_place_is_refused_and_nothing_installed(tmp_path: Path) -> None:
    fetch, _ = _steps(_backend(tmp_path, Routes({acma.URL: b"<html>Service unavailable</html>"})))
    with pytest.raises(BackendError, match="not a zip archive"):
        fetch.perform()
    assert not list((tmp_path / "cache").glob("checked-*"))
    assert not _dest(tmp_path).exists()


def test_a_truncated_download_is_refused(tmp_path: Path) -> None:
    body = register_bytes(tmp_path)[:-300]
    fetch, _ = _steps(_backend(tmp_path, Routes({acma.URL: body})))
    with pytest.raises(BackendError):
        fetch.perform()


def test_the_mirror_is_asked_first_and_checked_the_same_way(tmp_path: Path) -> None:
    body = register_bytes(tmp_path)
    routes = Routes({AT_MIRROR: body, acma.URL: b"never asked"})
    fetch, install = _steps(_backend(tmp_path, routes, MIRROR))
    assert fetch.sources == (AT_MIRROR, acma.URL)
    assert "LAN mirror first" in fetch.description
    assert "from the LAN mirror" in fetch.perform()
    assert routes.requested == [AT_MIRROR]
    install.perform()
    assert _dest(tmp_path).read_bytes() == body


def test_a_damaged_mirror_copy_is_passed_over_for_the_publisher(tmp_path: Path) -> None:
    body = register_bytes(tmp_path)
    routes = Routes({AT_MIRROR: body[:-300], acma.URL: body})
    fetch, _ = _steps(_backend(tmp_path, routes, MIRROR))
    said = fetch.perform()
    assert "from the publisher" in said and "the mirror was passed over" in said
    assert fetch.facts["source"] == "publisher"


def test_the_schema_holds_the_licence_url_to_https() -> None:
    with pytest.raises((ManifestError, ValueError), match="licence_url must be https"):
        RegisterInstall(licence="x y", licence_url="http://example.invalid/")


def _dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *flags: str,
) -> tuple[int, str]:
    from test_json_install import _machine, cli

    _machine(monkeypatch, tmp_path)
    rc = cli.main(
        ["--catalog", str(REPO_ROOT / "catalog"), "install", "--dry-run", *flags, "acma-register"]
    )
    return rc, capsys.readouterr().out


def test_the_plan_prints_about_the_size_the_licence_and_unverified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out = _dry_run(monkeypatch, tmp_path, capsys)
    assert rc == 0, out
    flat = " ".join(out.split())
    assert (
        "acma-register about 67.5 MB total, licence: ACMA Register of Radiocommunications " in flat
    )
    assert "attribution required" in flat
    assert "warning: unverified: the ACMA publishes no checksum" in flat
    assert "UNVERIFIED: no checksum is published" in flat


def test_the_plan_document_carries_the_check_and_validates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from json_support import parse_one, validate

    rc, out = _dry_run(monkeypatch, tmp_path, capsys, "--json")
    doc = parse_one(out)
    validate(doc)
    assert rc == 0
    (data,) = doc["install"]["data"]
    assert data["unit"] == "acma-register" and data["approximate"] is True
    assert data["verified_by"] == acma.VERIFIED_BY
    assert data["total_size"] == acma.MEASURED_SIZE
