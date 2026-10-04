# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import stat
from pathlib import Path

import pytest

from hammunition.console import config
from hammunition.console.config import Config


def env_for(tmp_path: Path) -> dict[str, str]:
    return {"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "xdg")}


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert config.load(config.config_path(env_for(tmp_path))) == Config()


def test_round_trip_and_modes(tmp_path: Path) -> None:
    path = config.config_path(env_for(tmp_path))
    assert config.save(Config(last_screen="logs", theme="light", walkthrough_dismissed=True), path)
    assert config.load(path) == Config("logs", "light", True)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert path.parent.name == "hammunition-console"


def test_xdg_config_home_wins_then_home(tmp_path: Path) -> None:
    assert config.config_dir({"HOME": "/h", "XDG_CONFIG_HOME": "/x"}) == Path(
        "/x/hammunition-console"
    )
    assert config.config_dir({"HOME": "/h"}) == Path("/h/.config/hammunition-console")


def test_the_file_holds_exactly_three_keys(tmp_path: Path) -> None:
    import tomllib

    path = config.config_path(env_for(tmp_path))
    config.save(Config(), path)
    assert set(tomllib.loads(path.read_text())) == {"last_screen", "theme", "walkthrough_dismissed"}


@pytest.mark.parametrize(
    "content",
    [
        b"\xff\xfe\x00garbage",
        b"last_screen = ",
        b"last_screen = 5\ntheme = true\nwalkthrough_dismissed = 'yes'\n",
        b"last_screen = 'no-such-screen'\ntheme = 'purple'\n",
        b"[[[[",
        b"",
    ],
)
def test_corrupt_or_hand_edited_config_gives_defaults_not_a_crash(
    tmp_path: Path, content: bytes
) -> None:
    path = config.config_path(env_for(tmp_path))
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    assert config.load(path) == Config()


def test_partially_valid_config_keeps_the_valid_keys(tmp_path: Path) -> None:
    path = config.config_path(env_for(tmp_path))
    path.parent.mkdir(parents=True)
    path.write_text("last_screen = 'update'\ntheme = 'purple'\n")
    assert config.load(path) == Config(last_screen="update")


def test_save_failure_is_reported_not_raised(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert config.save(Config(), blocker / "sub" / "config.toml") is False
