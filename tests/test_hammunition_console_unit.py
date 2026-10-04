# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The hammunition-console unit pins a tag's source archive, like hammunition-tray (D-024)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "catalog" / "packages" / "hammunition-console.yaml"


def load() -> dict:  # type: ignore[type-arg]
    return yaml.safe_load(MANIFEST.read_text())  # type: ignore[no-any-return]


def test_the_digest_is_a_real_release_digest_not_the_draft_zeros() -> None:
    block = load()["install"][0]["install"]
    assert block["artifact"]["sha256"] != "0" * 64, (
        "fill the pin at release: Phase B of the console plan's Task 20 says which command produces it"
    )


def test_the_pin_is_the_version_the_manifest_declares() -> None:
    data = load()
    url = data["install"][0]["install"]["artifact"]["url"]
    assert url == (
        "https://github.com/ChiefGyk3D/hammunition-console/releases/download/"
        f"v{data['version']}/hammunition-console-{data['version']}.tar.gz"
    )


def test_it_depends_on_the_archives_urwid_and_nothing_is_fetched_by_pip() -> None:
    data = load()
    assert "python3-urwid" in data["depends"] and "python3" in data["depends"]
    methods = {b["install"]["method"] for b in data["install"]}
    assert methods == {"binary"}, "no venv, no pip, no pipx (D-014)"


def test_it_is_in_no_profile() -> None:
    for path in (ROOT / "catalog" / "profiles").glob("*.yaml"):
        assert "hammunition-console" not in path.read_text(), f"{path.name} must not include it yet"


def test_it_has_a_terminal_launcher_for_the_menu() -> None:
    launcher = load()["launchers"][0]
    assert launcher["terminal"] is True and launcher["name"] == "hammunition-console"
    assert launcher["exec"].endswith("/hammunition-console/bin/hammunition-console")
