# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A data archive's ``members`` and ``into``.  D-071.

The map kit takes three fonts, a style and tilemaker's profile out of one
43.7 MB tarball that also carries tilemaker's source and 64 MB of CJK fonts,
and it carries three archives in one unit. Two archives extracted into the
same directory replace each other (``extract`` rebuilds its destination), so
each needs its own subdirectory, and a member list keeps the rest of the
tarball out of the prefix. A listed member that matches nothing is refused:
an archive that no longer has the file is a changed archive, not a quiet
success (D-031).
"""

from __future__ import annotations

import hashlib
import io
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.backends import Action, BackendError, DataBackend
from hammunition.backends.source import extract
from hammunition.fetch import Fetcher
from hammunition.manifest.schema import DataInstall, PackageManifest


def _tarball(path: Path, files: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return path


def _zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    return path


TREE = {
    "tilemaker-3.0.0/resources/config-openmaptiles.json": b"{}",
    "tilemaker-3.0.0/resources/process-openmaptiles.lua": b"-- lua",
    "tilemaker-3.0.0/src/tilemaker.cpp": b"int main(){}",
    "tilemaker-3.0.0/server/static/fonts/KlokanTech Noto Sans Regular/0-255.pbf": b"R",
    "tilemaker-3.0.0/server/static/fonts/KlokanTech Noto Sans CJK Regular/0-255.pbf": b"C",
}


def test_members_extract_only_the_named_files_and_directories(tmp_path: Path) -> None:
    archive = _tarball(tmp_path / "t.tar.gz", TREE)
    dest = tmp_path / "out"
    outcome = extract(
        archive,
        dest,
        members=[
            "tilemaker-3.0.0/resources/config-openmaptiles.json",
            "tilemaker-3.0.0/server/static/fonts/KlokanTech Noto Sans Regular/",
        ],
    )
    assert (dest / "resources" / "config-openmaptiles.json").read_bytes() == b"{}"
    assert (dest / "server/static/fonts/KlokanTech Noto Sans Regular/0-255.pbf").read_bytes() == (
        b"R"
    )
    assert not (dest / "src").exists()
    assert not (dest / "resources" / "process-openmaptiles.lua").exists()
    assert not (dest / "server/static/fonts/KlokanTech Noto Sans CJK Regular").exists()
    assert "2 of 5" in outcome and "stripped tilemaker-3.0.0/" in outcome


def test_members_work_on_a_zip_too(tmp_path: Path) -> None:
    archive = _zip(
        tmp_path / "dist.zip",
        {"dist/maplibre-gl.mjs": b"export{}", "dist/maplibre-gl.mjs.map": b"{}"},
    )
    dest = tmp_path / "out"
    extract(archive, dest, members=["dist/maplibre-gl.mjs"])
    assert (dest / "maplibre-gl.mjs").read_bytes() == b"export{}"
    assert not (dest / "maplibre-gl.mjs.map").exists()


def test_a_member_that_matches_nothing_is_refused_and_nothing_lands(tmp_path: Path) -> None:
    archive = _tarball(tmp_path / "t.tar.gz", TREE)
    dest = tmp_path / "out"
    with pytest.raises(BackendError, match=r"resources/config-openmaptiles\.jsonx"):
        extract(archive, dest, members=["tilemaker-3.0.0/resources/config-openmaptiles.jsonx"])
    assert not dest.exists()


def test_a_directory_member_matches_only_below_it(tmp_path: Path) -> None:
    """``fonts/KlokanTech Noto Sans Regular/`` is not a prefix of the CJK
    directory's name, and a directory member without its slash is not one."""
    archive = _tarball(tmp_path / "t.tar.gz", TREE)
    with pytest.raises(BackendError, match="matched nothing"):
        extract(archive, tmp_path / "a", members=["tilemaker-3.0.0/server/static/fonts/Klokan"])


# -- the schema -----------------------------------------------------------------


def _manifest(artifacts: list[dict[str, Any]]) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "vector-map-kit",
            "version": "1",
            "summary": "A kit for a test",
            "categories": ["navigation-maps"],
            "install": [
                {
                    "install": {
                        "method": "data",
                        "artifacts": artifacts,
                        "licence": "various",
                        "licence_url": "https://example.org/",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "A kit for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://example.org/",
            },
        }
    )


def _archive(name: str, **extra: Any) -> dict[str, Any]:
    return {
        "url": f"https://x/{name}",
        "sha256": "a" * 64,
        "size": 10,
        "format": "tarball",
        **extra,
    }


def test_two_archives_each_need_their_own_directory() -> None:
    with pytest.raises(ValidationError, match="into"):
        _manifest([_archive("a.tar.gz"), _archive("b.tar.gz", into="b")])
    with pytest.raises(ValidationError, match="into"):
        _manifest([_archive("a.tar.gz", into="x"), _archive("b.tar.gz", into="x")])
    _manifest([_archive("a.tar.gz", into="a"), _archive("b.tar.gz", into="b")])


def test_an_archive_beside_files_needs_its_own_directory() -> None:
    file = {"url": "https://x/s.png", "sha256": "b" * 64, "size": 3, "install_as": "s.png"}
    with pytest.raises(ValidationError, match="into"):
        _manifest([_archive("a.tar.gz"), file])
    with pytest.raises(ValidationError, match="into"):
        _manifest([_archive("a.tar.gz", into="s.png"), file])
    _manifest([_archive("a.tar.gz", into="a"), file])


@pytest.mark.parametrize("into", ["", ".", "..", "a/b", "a b"])
def test_into_is_one_plain_name(into: str) -> None:
    with pytest.raises(ValidationError, match="into"):
        _manifest([_archive("a.tar.gz", into=into)])


@pytest.mark.parametrize("member", ["", "/etc/passwd", "a/../b", "a\\b"])
def test_a_member_is_a_relative_path_inside_the_archive(member: str) -> None:
    with pytest.raises(ValidationError, match="member"):
        _manifest([_archive("a.tar.gz", into="a", members=[member])])


def test_members_and_into_are_for_archives_only() -> None:
    for extra in ({"members": ["x"]}, {"into": "x"}):
        with pytest.raises(ValidationError, match="archive"):
            _manifest(
                [{"url": "https://x/s", "sha256": "b" * 64, "size": 3, "install_as": "s", **extra}]
            )


# -- the backend ------------------------------------------------------------------


def test_each_archive_lands_in_its_own_directory_and_files_beside_them(tmp_path: Path) -> None:
    import contextlib

    tar = _tarball(tmp_path / "t.tar.gz", TREE).read_bytes()
    zipped = _zip(tmp_path / "d.zip", {"dist/maplibre-gl.mjs": b"export{}"}).read_bytes()
    sprite = b"\x89PNG"
    bodies = {"https://x/t.tar.gz": tar, "https://x/d.zip": zipped, "https://x/s.png": sprite}

    class T:
        @contextlib.contextmanager
        def open(self, url: str) -> Any:
            yield io.BytesIO(bodies[url])

    def sha(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()

    m = _manifest(
        [
            {
                "url": "https://x/t.tar.gz",
                "sha256": sha(tar),
                "size": len(tar),
                "format": "tarball",
                "into": "tilemaker",
                "members": ["tilemaker-3.0.0/resources/"],
            },
            {
                "url": "https://x/d.zip",
                "sha256": sha(zipped),
                "size": len(zipped),
                "format": "zip",
                "into": "maplibre",
            },
            {"url": "https://x/s.png", "sha256": sha(sprite), "size": 4, "install_as": "s.png"},
        ]
    )
    block = m.install[0].install
    assert isinstance(block, DataInstall)
    backend = DataBackend(fetcher=Fetcher(tmp_path / "cache", transport=T()), prefix=tmp_path / "p")
    steps = [s for s in backend.steps(m, block) if isinstance(s, Action)]
    for step in steps:
        step.perform()
    data = tmp_path / "p" / "share" / "hammunition" / "data" / "vector-map-kit"
    assert (data / "tilemaker" / "resources" / "process-openmaptiles.lua").is_file()
    assert not (data / "tilemaker" / "src").exists()
    assert (data / "maplibre" / "maplibre-gl.mjs").read_bytes() == b"export{}"
    assert (data / "s.png").read_bytes() == sprite
    details = [s.detail for s in steps if s.kind == "install-data"]
    assert details == [str(data / "tilemaker"), str(data / "maplibre"), str(data / "s.png")]
    descriptions = " ".join(s.description for s in steps)
    assert "only the listed members" in descriptions
