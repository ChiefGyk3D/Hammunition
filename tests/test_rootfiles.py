# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A root-owned file is replaced whole, never spliced.  D-056, D-058.

Lifted from the kept-off rules file (#119), where a fixed temp name let two
helper runs interleave into one file that could then never be parsed.
"""

from __future__ import annotations

import fcntl
import os
import stat
import threading
import time
from pathlib import Path

import pytest

from hammunition.rootfiles import atomic_write, dir_lock


def test_atomic_write_puts_the_content_and_the_mode(tmp_path: Path) -> None:
    target = tmp_path / "ntp.conf"
    atomic_write(target, "driftfile /var/lib/ntpsec/ntp.drift\n", mode=0o640)
    assert target.read_text() == "driftfile /var/lib/ntpsec/ntp.drift\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_the_default_mode_is_0644(tmp_path: Path) -> None:
    target = tmp_path / "time.yaml"
    atomic_write(target, "mode: auto\n")
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_atomic_write_replaces_an_existing_file_whole(tmp_path: Path) -> None:
    target = tmp_path / "time.yaml"
    target.write_text("mode: auto\n" * 50)
    atomic_write(target, "mode: gps-only\n")
    assert target.read_text() == "mode: gps-only\n"


def test_the_temp_file_is_unique_hidden_and_beside_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    real_replace = os.replace

    def recording(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen.append(os.fspath(src))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", recording)
    atomic_write(tmp_path / "hammunition-gps.conf", "x\n")
    atomic_write(tmp_path / "hammunition-gps.conf", "y\n")
    first, second = (Path(s) for s in seen)
    assert first != second, "two writes shared one temp name"
    for tmp in (first, second):
        assert tmp.parent == tmp_path
        assert tmp.name.startswith(".hammunition-gps.") and tmp.name.endswith(".tmp")


def test_a_failed_replace_leaves_the_old_file_and_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "ntp.conf"
    target.write_text("old\n")

    def refusing(src: object, dst: object) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(os, "replace", refusing)
    with pytest.raises(OSError, match="read-only"):
        atomic_write(target, "new\n")
    assert target.read_text() == "old\n"
    assert [p.name for p in tmp_path.iterdir()] == ["ntp.conf"]


def test_dir_lock_makes_a_second_holder_wait(tmp_path: Path) -> None:
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    entered: list[bool] = []

    def worker() -> None:
        with dir_lock(tmp_path):
            entered.append(True)

    thread = threading.Thread(target=worker)
    try:
        thread.start()
        time.sleep(0.3)
        assert entered == [], "dir_lock did not wait for a lock already held"
    finally:
        os.close(fd)
    thread.join(timeout=5)
    assert entered == [True]
