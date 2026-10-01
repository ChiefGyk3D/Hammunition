# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Open Repeater pin is generated into its manifest; nothing here
reaches the network.  D-074.

The fetch is injected. Every check is run against a copy of the real
manifest, so the file the generator edits is the one it will edit for real.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from hammunition.manifest.load import load_catalog, load_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "gen_open-repeater-pin.py"
MANIFEST = REPO_ROOT / "catalog" / "packages" / "open-repeater.yaml"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "repeaters" / "open-repeater.json"


def _generator() -> Any:
    spec = importlib.util.spec_from_file_location("gen_open_repeater_pin", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_open_repeater_pin"] = module
    spec.loader.exec_module(module)
    return module


gen = _generator()


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    copy = tmp_path / "open-repeater.yaml"
    shutil.copyfile(MANIFEST, copy)
    return copy


def _fetch(body: bytes) -> Any:
    asked: list[str] = []

    def fetch(url: str) -> bytes:
        asked.append(url)
        return body

    fetch.asked = asked  # type: ignore[attr-defined]
    return fetch


def _artifact(path: Path) -> Any:
    block = load_manifest(path).install[0].install
    return block, block.artifacts[0]  # type: ignore[union-attr]


def test_regenerating_writes_the_digest_size_and_day_into_the_manifest(
    manifest: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = FIXTURE.read_bytes()
    fetch = _fetch(body)
    before = manifest.read_text()
    code = gen.main([], fetch=fetch, today=date(2026, 10, 1), manifest_path=manifest)
    assert code == 0
    assert fetch.asked == [gen.URL]
    _block, artifact = _artifact(manifest)
    assert artifact.sha256 == hashlib.sha256(body).hexdigest()
    assert artifact.size == len(body)
    assert load_manifest(manifest).version == "2026-10-01"
    # Only the three pinned lines changed.
    changed = [
        (a, b)
        for a, b in zip(before.splitlines(), manifest.read_text().splitlines(), strict=True)
        if a != b
    ]
    assert len(changed) <= 3
    assert "wrote" in capsys.readouterr().out


@pytest.mark.parametrize(
    "body",
    [
        b"<html>maintenance</html>",
        json.dumps({"source": "Open Repeater", "license": "CC BY-NC", "repeaters": []}).encode(),
        json.dumps({"source": "Someone", "license": "CC0", "repeaters": []}).encode(),
    ],
)
def test_regenerating_refuses_what_is_not_the_cc0_list(manifest: Path, body: bytes) -> None:
    before = manifest.read_text()
    with pytest.raises(SystemExit, match="Nothing was written"):
        gen.main([], fetch=_fetch(body), today=date(2026, 10, 1), manifest_path=manifest)
    assert manifest.read_text() == before


def test_the_offline_check_passes_on_the_committed_manifest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def no_network(url: str) -> bytes:
        raise AssertionError("--offline asked the network")

    before = MANIFEST.stat().st_mtime_ns
    assert gen.main(["--check", "--offline"], fetch=no_network) == 0
    assert "well formed" in capsys.readouterr().out
    assert MANIFEST.stat().st_mtime_ns == before


@pytest.mark.parametrize(
    ("old", "new", "says"),
    [
        ("format=json&", "format=csv&", "URL"),
        ("install_as: open-repeater.json", "install_as: other.json", "open-repeater.json"),
        ("licence: CC0 1.0", "licence: CC BY 4.0", "CC0 1.0"),
    ],
)
def test_the_offline_check_goes_red_on_a_broken_manifest(
    manifest: Path, old: str, new: str, says: str, capsys: pytest.CaptureFixture[str]
) -> None:
    text = manifest.read_text()
    assert old in text
    manifest.write_text(text.replace(old, new))
    assert gen.main(["--check", "--offline"], manifest_path=manifest) == 1
    assert says in capsys.readouterr().out


def test_the_online_check_compares_and_names_the_generator(
    manifest: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = FIXTURE.read_bytes()
    gen.main([], fetch=_fetch(body), today=date(2026, 10, 1), manifest_path=manifest)
    capsys.readouterr()
    pinned = manifest.read_text()
    assert gen.main(["--check"], fetch=_fetch(body), manifest_path=manifest) == 0
    assert "up to date" in capsys.readouterr().out
    assert gen.main(["--check"], fetch=_fetch(body + b" "), manifest_path=manifest) == 1
    out = capsys.readouterr().out
    assert "changed since" in out and "gen_open-repeater-pin.py" in out
    assert manifest.read_text() == pinned  # a check writes nothing


def test_the_unit_is_listed_by_artifacts_under_the_name_a_mirror_is_asked_for() -> None:
    from hammunition.artifacts import select_units

    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    assert "open-repeater" in select_units(catalog, ())
    block, artifact = _artifact(MANIFEST)
    assert artifact.install_as == "open-repeater.json"
    assert artifact.url == gen.URL
    assert block.licence == "CC0 1.0"
