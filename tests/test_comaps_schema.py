# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The git block's five build fields and the ``mwm-regions`` method.  D-069."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.backends import IMPLEMENTED_METHODS
from hammunition.manifest.schema import GitInstall, MwmRegionsInstall, PackageManifest

SHA = "a" * 64
COMMIT = "72632e4de65a98dfed827d8e447f0287168639d0"
PROTOBUF = "protobuf==3.20.3 --hash=sha256:" + "b" * 64
DOCS = {
    "what_it_does": "Does an example thing for the purposes of testing.",
    "why_you_want_it": "Because the test suite requires a valid manifest.",
    "upstream_url": "https://example.invalid/",
}


def _git(**extra: Any) -> dict[str, Any]:
    return {
        "method": "git",
        "repo": "https://codeberg.org/comaps/comaps.git",
        "ref": "v2026.08.31-14",
        "build_system": "cmake",
        **extra,
    }


def _manifest(install: dict[str, Any], **extra: Any) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "example",
            "version": "1.0",
            "summary": "An example package",
            "categories": ["navigation-maps"],
            "install": [{"install": install}],
            "update": {"probe": {"method": "none"}},
            "documentation": DOCS,
            **extra,
        }
    )


def _block(install: dict[str, Any]) -> GitInstall:
    block = _manifest(install).install[0].install
    assert isinstance(block, GitInstall)
    return block


# -- commit -----------------------------------------------------------------


def test_a_tag_may_name_the_commit_it_must_resolve_to() -> None:
    assert _block(_git(commit=COMMIT)).commit == COMMIT


def test_commit_is_refused_on_a_sha_ref() -> None:
    with pytest.raises(ValidationError, match="commit is for a tag"):
        _block(
            _git(
                ref=COMMIT,
                commit=COMMIT,
                pin_review={
                    "last_reviewed": "2026-09-29",
                    "reviewed_by": "tester",
                    "basis": "distribution_pin",
                    "distributions": ["Flathub"],
                    "rationale": "The commit three distributions build, checked 2026-09-29.",
                },
            )
        )


def test_commit_must_be_forty_hex() -> None:
    with pytest.raises(ValidationError, match="40 lowercase hex"):
        _block(_git(commit="72632e4"))


# -- submodules and the build Python ------------------------------------------


def test_submodules_default_off() -> None:
    assert _block(_git()).submodules is False
    assert _block(_git(submodules=True)).submodules is True


def test_build_python_lines_must_be_hash_pinned() -> None:
    assert _block(_git(build_python=[PROTOBUF])).build_python == [PROTOBUF]
    with pytest.raises(ValidationError, match="--hash=sha256"):
        _block(_git(build_python=["protobuf==3.20.3"]))


# -- prepare -----------------------------------------------------------------


def _prepare(**extra: Any) -> dict[str, Any]:
    return {
        "script": "configure.sh",
        "args": ["--skip-map-download"],
        "env": {"SKIP_PYTHON_VENV": "1"},
        "produces": ["data/symbols/*/light/symbols.png"],
        **extra,
    }


def test_prepare_is_accepted() -> None:
    block = _block(_git(prepare=_prepare()))
    assert block.prepare is not None
    assert block.prepare.script == "configure.sh"
    assert block.prepare.produces == ["data/symbols/*/light/symbols.png"]


@pytest.mark.parametrize("script", ["/bin/sh", "../configure.sh", "a/../../b.sh", ""])
def test_prepare_script_stays_inside_the_tree(script: str) -> None:
    with pytest.raises(ValidationError, match="relative path inside the tree"):
        _block(_git(prepare=_prepare(script=script)))


def test_prepare_must_name_what_it_produces() -> None:
    with pytest.raises(ValidationError, match="produces"):
        _block(_git(prepare=_prepare(produces=[])))
    with pytest.raises(ValidationError, match="relative path inside the tree"):
        _block(_git(prepare=_prepare(produces=["../elsewhere/*.png"])))


def test_prepare_env_may_not_set_what_the_engine_owns() -> None:
    with pytest.raises(ValidationError, match="the engine sets"):
        _block(_git(prepare=_prepare(env={"PATH": "/tmp"})))


# -- extra files -------------------------------------------------------------


WORLD = {
    "artifact": {
        "url": "https://cdn-fi-1.comaps.app/maps/2026.06.28/260830/World.mwm",
        "sha256": SHA,
        "size": 53387231,
    },
    "install_as": "share/comaps/data/World.mwm",
}
BRANDS = {"from_tree": "data/categories_brands.txt", "install_as": "share/comaps/data/x.txt"}


def test_extra_files_take_an_artifact_or_a_tree_file() -> None:
    block = _block(_git(extra_files=[WORLD, BRANDS]))
    assert [f.install_as for f in block.extra_files] == [
        "share/comaps/data/World.mwm",
        "share/comaps/data/x.txt",
    ]


def test_an_extra_file_is_exactly_one_of_the_two() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        _block(_git(extra_files=[{**WORLD, "from_tree": "data/World.mwm"}]))
    with pytest.raises(ValidationError, match="exactly one"):
        _block(_git(extra_files=[{"install_as": "share/comaps/data/World.mwm"}]))


@pytest.mark.parametrize(
    "install_as", ["/usr/share/x", "share/../bin/x", "bin/CoMaps", "lib/x.so", "share"]
)
def test_an_extra_file_lands_under_share(install_as: str) -> None:
    with pytest.raises(ValidationError, match="under share/"):
        _block(_git(extra_files=[{**BRANDS, "install_as": install_as}]))


def test_an_extra_file_is_not_installed_twice() -> None:
    with pytest.raises(ValidationError, match="twice"):
        _block(_git(extra_files=[BRANDS, BRANDS]))


# -- mwm-regions and its probe ----------------------------------------------


OSM = {"licence": "ODbL-1.0", "licence_url": "https://www.openstreetmap.org/copyright"}


def test_the_mwm_regions_method() -> None:
    block = _manifest({"method": "mwm-regions", "provider": "comaps", **OSM}).install[0].install
    assert isinstance(block, MwmRegionsInstall)
    assert block.provider == "comaps"
    assert "mwm-regions" in IMPLEMENTED_METHODS
    with pytest.raises(ValidationError):
        _manifest({"method": "mwm-regions", "provider": "organicmaps", **OSM})


def test_the_comaps_maps_probe() -> None:
    m = _manifest(
        {"method": "mwm-regions", "provider": "comaps", **OSM},
        update={"probe": {"method": "comaps_maps"}},
    )
    assert m.update.probe.method == "comaps_maps"
