# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition maps phone``: stage the phone files, print the routes.  D-067.

Public example regions only; the "installed" files are a few bytes each.
Nothing here transfers, serves or binds anything.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import subprocess
from pathlib import Path

import pytest

from hammunition import phone
from json_support import parse_one, validate

cli = importlib.import_module("hammunition.cli.main")

VT, DE = "north-america-us-vermont", "north-america-us-delaware"


def _data(prefix: Path) -> Path:
    return prefix / "share" / "hammunition" / "data"


def _install(prefix: Path, unit: str, name: str, body: bytes) -> Path:
    path = _data(prefix) / unit / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def _everything(prefix: Path) -> None:
    for slug in (VT, DE):
        _install(prefix, "mapsforge-map", f"{slug}.map", f"map {slug}".encode())
        _install(prefix, "mapsforge-poi", f"{slug}.poi", f"poi {slug}".encode())
    _install(prefix, "osm-garmin", f"{VT}.img", b"garmin")
    # Sidecars are not phone files.
    _install(prefix, "mapsforge-map", f"{VT}.map.source", b"260101\n")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(cli, "DEFAULT_PREFIX", tmp_path / "prefix")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    return tmp_path


def test_every_phone_file_is_copied_with_a_sha256sums_that_checks(home: Path) -> None:
    _everything(home / "prefix")
    folder = phone.phone_dir()
    result = phone.stage(phone.installed(_data(home / "prefix")), folder)
    assert folder == home / "xdg" / "hammunition" / "phone"
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        [f"{VT}.map", f"{DE}.map", f"{VT}.poi", f"{DE}.poi", f"{VT}.img", "SHA256SUMS"]
    )
    assert all(f.copied for f in result.files)
    assert (folder / f"{VT}.img").read_bytes() == b"garmin"
    check = subprocess.run(
        ["sha256sum", "--check", "--strict", "SHA256SUMS"],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert (folder.stat().st_mode & 0o777) == 0o700


def test_a_second_run_copies_nothing_and_writes_the_same_sums(home: Path) -> None:
    _everything(home / "prefix")
    found = phone.installed(_data(home / "prefix"))
    folder = phone.phone_dir()
    phone.stage(found, folder)
    before = (folder / "SHA256SUMS").read_bytes()
    inode = (folder / f"{VT}.map").stat().st_ino
    again = phone.stage(found, folder)
    assert not any(f.copied for f in again.files)
    assert (folder / "SHA256SUMS").read_bytes() == before
    assert (folder / f"{VT}.map").stat().st_ino == inode, "a current copy is not rewritten"


def test_a_changed_map_is_copied_again(home: Path) -> None:
    _everything(home / "prefix")
    folder = phone.phone_dir()
    phone.stage(phone.installed(_data(home / "prefix")), folder)
    _install(home / "prefix", "mapsforge-map", f"{VT}.map", b"a newer map")
    result = phone.stage(phone.installed(_data(home / "prefix")), folder)
    assert [f.name for f in result.files if f.copied] == [f"{VT}.map"]
    assert (folder / f"{VT}.map").read_bytes() == b"a newer map"
    digest = hashlib.sha256(b"a newer map").hexdigest()
    assert f"{digest}  {VT}.map\n" in (folder / "SHA256SUMS").read_text()


def test_a_region_gone_removes_only_our_file_and_leaves_the_rest(home: Path) -> None:
    _everything(home / "prefix")
    folder = phone.phone_dir()
    phone.stage(phone.installed(_data(home / "prefix")), folder)
    (folder / "notes.txt").write_text("mine")
    (folder / "sub").mkdir()
    (folder / "sub" / "old.map").write_text("mine too")
    os.symlink("/nonexistent", folder / "link.map")
    for unit, ext in (("mapsforge-map", ".map"), ("mapsforge-poi", ".poi")):
        (_data(home / "prefix") / unit / f"{DE}{ext}").unlink()
    result = phone.stage(phone.installed(_data(home / "prefix")), folder)
    assert sorted(result.removed) == [f"{DE}.map", f"{DE}.poi"]
    assert (folder / "notes.txt").exists() and (folder / "sub" / "old.map").exists()
    assert (folder / "link.map").is_symlink(), "a symbolic link is not ours to remove"
    assert DE not in (folder / "SHA256SUMS").read_text()


def test_a_symlinked_folder_is_refused_and_nothing_is_copied(home: Path) -> None:
    _everything(home / "prefix")
    elsewhere = home / "elsewhere"
    elsewhere.mkdir()
    folder = phone.phone_dir()
    folder.parent.mkdir(parents=True)
    folder.symlink_to(elsewhere)
    with pytest.raises(phone.PhoneError, match="symbolic link"):
        phone.stage(phone.installed(_data(home / "prefix")), folder)
    assert list(elsewhere.iterdir()) == []


def test_too_little_room_is_refused_before_anything_is_copied(home: Path) -> None:
    _everything(home / "prefix")
    folder = phone.phone_dir()
    with pytest.raises(phone.PhoneError, match="nothing was copied"):
        phone.stage(phone.installed(_data(home / "prefix")), folder, free_at=lambda _: 3)
    assert list(folder.iterdir()) == []


def test_a_symlink_among_the_installed_files_is_not_a_phone_file(home: Path) -> None:
    _everything(home / "prefix")
    secret = home / "secret.map"
    secret.write_text("not a map")
    os.symlink(secret, _data(home / "prefix") / "mapsforge-map" / "planted.map")
    names = [f.name for f in phone.installed(_data(home / "prefix"))]
    assert "planted.map" not in names


def test_the_command_prints_the_files_and_the_routes_and_transfers_nothing(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _everything(home / "prefix")
    assert cli.main(["maps", "phone"]) == 0
    out = capsys.readouterr().out
    folder = phone.phone_dir()
    assert f"Phone files in {folder}:" in out
    assert "Nothing was transferred." in out
    assert f"--bind 10.42.0.1 --directory {folder}" in out
    assert f"--bind 127.0.0.1 --directory {folder}" in out
    for line in out.splitlines():
        if "http.server" in line and "python3" in line:
            assert "--bind" in line, f"a server line without --bind: {line}"
    assert "kio-extras" in out and "android-udev-rules" in out and "kdeconnect" in out
    assert "USB debugging" in out and "KDE Connect app" in out
    assert "none has been checked on a phone" in out


def test_the_command_refuses_root(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    _everything(home / "prefix")
    assert cli.main(["maps", "phone"]) == 1
    assert not phone.phone_dir().exists()


def test_nothing_installed_says_what_to_install_and_touches_nothing(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["maps", "phone"]) == 0
    out = capsys.readouterr().out
    assert "hammunition install phone-maps" in out and "Nothing was copied" in out
    assert not phone.phone_dir().exists()


def test_the_json_document_carries_the_files_and_the_routes(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _install(home / "prefix", "mapsforge-map", f"{VT}.map", b"map")
    assert cli.main(["maps", "phone", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["kind"] == "phone"
    assert [f["name"] for f in doc["files"]] == [f"{VT}.map"]
    assert doc["files"][0]["sha256"] == hashlib.sha256(b"map").hexdigest()
    assert doc["missing"] == ["mapsforge-poi", "osm-garmin"]
    assert doc["routes"][0]["name"] == "Laptop hotspot and a web browser"
    assert len(doc["routes"]) == 4
