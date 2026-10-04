# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``resolve_secret`` (D-081): the environment, then Doppler, then a named error.

Doppler is a fake executable in a scratch directory put first on PATH; the
real ``doppler`` is never run and nothing touches the network.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from hammunition import runlog, secrets
from hammunition.station import Station, StationError

TOKEN = "rbuapp_0123456789abcdef"  # synthetic


def _doppler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, out: str, err: str = "", code: int = 0
) -> Path:
    """A fake `doppler` that records its argv and answers as told."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    record = tmp_path / "argv.txt"
    script = bin_dir / "doppler"
    script.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" > {record}\n'
        f"printf %s '{out}'\n"
        f"printf '%s\\n' '{err}' >&2\n"
        f"exit {code}\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bin_dir))
    return record


STATION = Station(secrets_doppler_project="hammunition", secrets_doppler_config="dev")


def test_the_environment_wins_and_doppler_is_never_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _doppler(tmp_path, monkeypatch, out="from-doppler")
    got = secrets.resolve_secret("SOME_API_KEY", env={"SOME_API_KEY": TOKEN}, station=STATION)
    assert got == TOKEN
    assert not record.exists()


def test_an_empty_environment_value_falls_through_to_doppler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _doppler(tmp_path, monkeypatch, out=TOKEN + "\n")
    got = secrets.resolve_secret("SOME_API_KEY", env={"SOME_API_KEY": ""}, station=STATION)
    assert got == TOKEN  # stripped
    assert record.read_text().split() == [
        "secrets",
        "get",
        "SOME_API_KEY",
        "--plain",
        "--project",
        "hammunition",
        "--config",
        "dev",
    ]


def test_doppler_off_path_is_a_named_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(secrets.SecretUnavailable) as exc:
        secrets.resolve_secret("SOME_API_KEY", env={}, station=STATION)
    assert "doppler" in str(exc.value) and "PATH" in str(exc.value)


def test_a_failing_doppler_quotes_only_the_first_stderr_line_never_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _doppler(tmp_path, monkeypatch, out=TOKEN, err="Doppler Error: not logged in", code=1)
    with pytest.raises(secrets.SecretUnavailable) as exc:
        secrets.resolve_secret("SOME_API_KEY", env={}, station=STATION)
    assert "not logged in" in str(exc.value)
    assert TOKEN not in str(exc.value)


def test_nothing_set_names_both_ways(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = _doppler(tmp_path, monkeypatch, out=TOKEN)
    for station in (None, Station(), Station(secrets_doppler_project="only-one")):
        with pytest.raises(secrets.SecretUnavailable) as exc:
            secrets.resolve_secret("SOME_API_KEY", env={}, station=station)
        text = str(exc.value)
        assert "export SOME_API_KEY=" in text
        assert "--doppler-project" in text and "--doppler-config" in text
    assert not record.exists()


def test_an_empty_doppler_answer_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _doppler(tmp_path, monkeypatch, out="\n")
    with pytest.raises(secrets.SecretUnavailable, match="empty"):
        secrets.resolve_secret("SOME_API_KEY", env={}, station=STATION)


def test_a_secret_name_is_an_identifier_never_an_option() -> None:
    with pytest.raises(ValueError):
        secrets.resolve_secret("--config", env={}, station=None)


@pytest.mark.parametrize("bad", ["-x", "a b", "", "a;b", "../x"])
def test_doppler_names_are_slugs_never_options(bad: str) -> None:
    with pytest.raises(StationError):
        Station(secrets_doppler_project=bad)
    with pytest.raises(StationError):
        Station(secrets_doppler_config=bad)


def test_a_resolved_secret_is_scrubbed_from_the_active_run_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = runlog._open(tmp_path / "20261002T000000Z-maps-1.log", None)
    monkeypatch.setattr(runlog, "_active", run)
    try:
        secrets.resolve_secret("SOME_API_KEY", env={"SOME_API_KEY": TOKEN}, station=None)
        run.write("out", f"the token is {TOKEN}")
        run.write("out", f"X-RB-App-Token: {TOKEN}")
        run.write("out", "Authorization: Bearer someotherthing")
    finally:
        monkeypatch.setattr(runlog, "_active", None)
    text = run.path.read_text()
    assert TOKEN not in text and "someotherthing" not in text
    assert text.count("<redacted>") == 3


# -- the station values ---------------------------------------------------------


def test_station_set_saves_and_clears_the_two_doppler_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib

    from hammunition.station import load_station

    cli = importlib.import_module("hammunition.cli.main")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert cli.main(["station", "set", "--doppler-project", "hammunition"]) != 0
    assert "both a project and a config" in capsys.readouterr().err
    assert (
        cli.main(["station", "set", "--doppler-project", "hammunition", "--doppler-config", "dev"])
        == 0
    )
    capsys.readouterr()
    saved = load_station()
    assert (saved.secrets_doppler_project, saved.secrets_doppler_config) == ("hammunition", "dev")
    assert cli.main(["station", "set", "--clear-doppler"]) == 0
    capsys.readouterr()
    cleared = load_station()
    assert cleared.secrets_doppler_project is None and cleared.secrets_doppler_config is None
    assert cli.main(["station", "set", "--doppler-project=-x", "--doppler-config", "dev"]) != 0
