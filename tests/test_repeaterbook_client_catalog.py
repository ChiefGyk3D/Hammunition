# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``repeaterbook-client`` unit (D-081): a hash-pinned venv of a third-party
client, installed by name, in no profile, exposing nothing, its closure
recorded beside the mesh closures."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "catalog" / "packages" / "repeaterbook-client.yaml"
CLOSURE = ROOT / "docs" / "reference" / "repeaterbook-client-closure.txt"


def _block() -> dict[str, object]:
    data = yaml.safe_load(MANIFEST.read_text())
    (entry,) = data["install"]
    return dict(entry["install"])


def _pins() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for line in _block()["requirements"]:  # type: ignore[attr-defined]
        name = line.split("==")[0]
        out[name] = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", line))
    return out


def test_it_is_a_hash_pinned_venv_with_every_line_pinned_and_hashed() -> None:
    block = _block()
    assert block["method"] == "venv" and block["python"] == ">=3.11" and block["licence"] == "MIT"
    pins = _pins()
    assert "repeaterbook" in pins
    assert all(hashes for hashes in pins.values()), "a requirement without a hash"
    assert not block.get("expose"), "the package's console scripts are not for the operator"


def test_the_manifest_is_the_recorded_closure_line_for_line() -> None:
    recorded: dict[str, set[str]] = {}
    text = CLOSURE.read_text().replace("\\\n", " ")
    for line in text.splitlines():
        if re.match(r"^[A-Za-z0-9_.-]+==", line):
            recorded[line.split("==")[0]] = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", line))
    assert recorded == _pins()
    versions = {
        m.group(1): m.group(2)
        for m in re.finditer(r"^([A-Za-z0-9_.-]+)==(\S+)", CLOSURE.read_text(), re.MULTILINE)
    }
    assert versions["repeaterbook"] == yaml.safe_load(MANIFEST.read_text())["version"]


def test_it_is_in_no_profile() -> None:
    for profile in (ROOT / "catalog" / "profiles").glob("*.yaml"):
        assert "repeaterbook-client" not in profile.read_text(), profile.name


def test_the_page_says_it_is_a_third_party_client_registered_as_app_114() -> None:
    docs = yaml.safe_load(MANIFEST.read_text())["documentation"]
    text = " ".join(str(v) for v in docs.values())
    assert "App #114" in text and "third-party" in text and "api_apps.php" in text
    assert "not yet run against the live API" in text
    assert "your own personal use" in text
