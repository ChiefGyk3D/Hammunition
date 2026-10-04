# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps repeaters fetch-repeaterbook`` (D-081), end to end.

The format is RepeaterBook's *documented* one and the fixture is written by
hand from it (see ``fixtures/repeaters/repeaterbook-api.README.md``): nothing
here has met the live API. The "publisher" is a loopback server in this
process that records every request; the real ``doppler`` is never run.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import stat
import sys
from pathlib import Path

import pytest

from hammunition import repeaterbook as rb
from hammunition import repeaters
from hammunition.repeaters import RepeaterInputError
from hammunition.station import Station as Saved
from hammunition.station import save_station

cli = importlib.import_module("hammunition.cli.main")

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "repeaters" / "repeaterbook-api-de.json"
TOKEN = "rbuapp_synthetic0123456789"
PRIVATE = ("N0CALL", "N0TST", "39.8", "-89.6", "146.94", "Springfield")


# -- parsing -----------------------------------------------------------------------


def test_the_documented_rows_parse_and_the_unusable_ones_are_counted() -> None:
    parsed = rb.parse_export(FIXTURE.read_bytes(), "https://x/api/export.php")
    assert parsed.format == repeaters.REPEATERBOOK_API and parsed.read == 6
    first, second = parsed.rows
    assert (first.callsign, first.output_hz, first.offset_hz) == ("N0CALL", 146_940_000, -600_000)
    assert first.tone == "131.8" and first.mode == "FM" and first.use == "OPEN"
    assert first.place == "Springfield, Test Hill" and first.updated == "2026-09-01"
    assert (first.lat, first.lon) == (39.8, -89.6)
    assert second.mode == "FM, DMR" and second.status == "Unknown"  # kept: not known off-air
    reasons = {s.reason: s.count for s in parsed.skipped}
    assert reasons == {
        rb.OFF_AIR: 1,
        "no usable position": 1,
        "no callsign": 1,
        "no usable output frequency": 1,
    }


def test_a_changed_field_name_fails_with_a_named_error() -> None:
    """Falsification: the importer must go red, saying which field, when
    RepeaterBook renames a key it relies on (here `Frequency`)."""
    text = FIXTURE.read_text().replace('"Frequency"', '"Freq"')
    with pytest.raises(RepeaterInputError, match="no Frequency field") as exc:
        rb.parse_export(text.encode(), "https://x")
    assert "nothing was read" in str(exc.value)


def test_a_bare_list_is_accepted_and_other_shapes_are_named() -> None:
    rows = json.loads(FIXTURE.read_text())["results"]
    assert rb.parse_export(json.dumps(rows).encode(), "u").read == 6
    with pytest.raises(RepeaterInputError, match="not JSON"):
        rb.parse_export(b"<html>login</html>", "u")
    with pytest.raises(RepeaterInputError, match="auth_invalid: bad key"):
        rb.parse_export(
            b'{"status": "error", "error_code": "auth_invalid", "message": "bad key"}', "u"
        )
    with pytest.raises(RepeaterInputError, match="no list of repeaters"):
        rb.parse_export(b'{"count": 0}', "u")


@pytest.mark.parametrize(
    ("country", "state", "expected"),
    [
        ("United States", "DE", "10"),
        ("United States", "delaware", "10"),
        ("United States", "New Hampshire", "33"),
        ("United States", "vt", "50"),
        ("Canada", "7", "07"),
        ("Canada", "ca01", "CA01"),
        ("Mexico", "MX14", "MX14"),
    ],
)
def test_states_map_to_the_id_the_export_takes(country: str, state: str, expected: str) -> None:
    assert rb.resolve_state(country, state) == expected


def test_an_unknown_state_is_refused_by_name() -> None:
    with pytest.raises(RepeaterInputError, match="'ZZ'"):
        rb.resolve_state("United States", "ZZ")
    with pytest.raises(RepeaterInputError, match="own state_id"):
        rb.resolve_state("Canada", "Ontario")


class Home:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.data = root / "data"
        self.config = root / "config"
        self.layer = self.data / "hammunition" / "overlays" / "repeaters"
        self.station = self.config / "hammunition" / "station.yml"
        self.record = root / "runner-record.jsonl"
        self.reply = root / "runner-reply.json"
        self.runner = root / "fake_runner.py"
        self.python = self.data / "hammunition" / "venvs" / rb.UNIT / "bin" / "python"

    def runs(self) -> list[dict[str, object]]:
        if not self.record.exists():
            return []
        return [json.loads(x) for x in self.record.read_text().splitlines()]

    def answer(self, document: dict[str, object]) -> None:
        self.reply.write_text(json.dumps(document))


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Home:
    """A scratch home with the unit "installed" (a symlink to this
    interpreter) and a fake runner that records how it was run and prints
    the recorded export, never the library, never RepeaterBook."""
    here = Home(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(here.data))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(here.config))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USER", "op")
    monkeypatch.setenv(rb.TOKEN_ENV, TOKEN)
    monkeypatch.setattr(cli, "DEFAULT_PREFIX", tmp_path / "prefix")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    here.python.parent.mkdir(parents=True)
    here.python.symlink_to(sys.executable)
    here.runner.write_text(
        "import json, os, sys\n"
        f"open({str(here.record)!r}, 'a').write(json.dumps({{'argv': sys.argv[1:], "
        "'token': os.environ.get('REPEATERBOOK'), 'env': sorted(os.environ)}) + '\\n')\n"
        f"sys.stdout.write(open({str(here.reply)!r}).read() + '\\n')\n"
    )
    monkeypatch.setattr(rb, "RUNNER", here.runner)
    here.answer({"ok": True, **json.loads(FIXTURE.read_text())})
    return here


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waits: list[float] = []
    monkeypatch.setattr(rb, "pause", lambda seconds=rb.INTERVAL_SECONDS: waits.append(seconds))
    return waits


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_the_token_reaches_the_runner_by_environment_only_and_one_unverified_layer_is_written(
    home: Home, capsys: pytest.CaptureFixture[str], _run_logs_in_tmp: Path
) -> None:
    code, out, err = _run(["maps", "repeaters", "fetch-repeaterbook", "--state", "DE"], capsys)
    assert code == 0, out + err
    (run,) = home.runs()
    assert run["argv"] == ["--country", "United States", "--state-id", "10"]
    assert run["token"] == TOKEN and TOKEN not in json.dumps(run["argv"])
    assert "REPEATERBOOK_API_KEY" not in run["env"]  # type: ignore[operator]
    # terms before anything is written
    assert out.index("Data courtesy of RepeaterBook.com") < out.index("Written:")
    flat = out.replace("\n", " ")
    assert "your own personal use on this machine" in flat and "never offered to a Bunker" in flat
    assert "Repeaters (RepeaterBook, personal use, " in out and ", unverified)" in out
    assert "Written: 2 repeaters" in out and "off the air (Operational Status): 1" in out
    for name in repeaters.layer_files("repeaterbook"):
        assert (home.layer / name).is_file()
    assert "not verified against the live API" in flat
    for leaked in PRIVATE:
        assert leaked not in out
    everything = out + err
    for log in _run_logs_in_tmp.glob("*.log"):
        everything += log.read_text()
    for item in home.layer.iterdir():
        if item.suffix != ".poi":
            everything += item.read_text(errors="replace")
    assert TOKEN not in everything
    assert any(_run_logs_in_tmp.glob("*.log")), "the run was logged"


def test_a_second_state_in_a_later_run_merges_into_the_same_layer(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["maps", "repeaters", "fetch-repeaterbook", "--state", "DE"]) == 0
    capsys.readouterr()
    other = json.loads(FIXTURE.read_text())
    other["results"] = [dict(other["results"][0], Callsign="N0NEW", Frequency="145.23000")]
    home.answer({"ok": True, **other})
    code, out, _ = _run(["maps", "repeaters", "fetch-repeaterbook", "--state", "Vermont"], capsys)
    assert code == 0, out
    assert home.runs()[-1]["argv"][-1] == "50"  # type: ignore[index]
    layer = repeaters.read_layer_rows(home.layer / repeaters.layer_files("repeaterbook")[3])
    assert sorted(r.callsign for r in layer.rows) == ["N0CALL", "N0NEW", "N0TST"]
    assert repeaters.present_layers(home.layer) == ("repeaterbook",)


def test_two_states_in_one_run_pause_between_requests(
    home: Home, capsys: pytest.CaptureFixture[str], _no_pause: list[float]
) -> None:
    code, out, _ = _run(
        ["maps", "repeaters", "fetch-repeaterbook", "--state", "DE", "--state", "VT"], capsys
    )
    assert code == 0, out
    assert [r["argv"][-1] for r in home.runs()] == ["10", "50"]  # type: ignore[index]
    assert _no_pause == [rb.INTERVAL_SECONDS]


@pytest.mark.parametrize(
    ("kind", "status"), [("unauthorized", 401), ("forbidden", 403), ("rate_limited", 429)]
)
def test_a_refusal_stops_the_whole_run_without_a_retry_and_writes_nothing(
    kind: str, status: int, home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    home.answer(
        {
            "ok": False,
            "kind": kind,
            "status": status,
            "error_code": None,
            "message": f"HTTP {status} with {TOKEN} in it",
            "retry_after": 30.0 if status == 429 else None,
        }
    )
    code, out, err = _run(
        ["maps", "repeaters", "fetch-repeaterbook", "--state", "DE", "--state", "VT"], capsys
    )
    assert code == cli.EXIT_FAILED
    assert len(home.runs()) == 1, "never retried, and the second state is not asked"
    assert "does not retry" in err and "Nothing was written" in err
    if status == 429:
        assert "too many requests (429)" in err and "30 s" in err
    else:
        assert "App #114" in err
    assert TOKEN not in out + err
    assert not home.layer.exists()


def test_a_runner_that_prints_nothing_is_a_named_error_with_the_token_redacted(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    home.runner.write_text(f"import sys\nsys.stderr.write('boom {TOKEN}\\n')\nsys.exit(3)\n")
    code, _, err = _run(["maps", "repeaters", "fetch-repeaterbook", "--state", "DE"], capsys)
    assert code == cli.EXIT_FAILED and "printed no document (exit 3)" in err
    assert TOKEN not in err and "<redacted>" in err
    assert not home.layer.exists()


def test_no_token_names_both_ways_and_runs_nothing(
    home: Home, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(rb.TOKEN_ENV)
    code, _, err = _run(["maps", "repeaters", "fetch-repeaterbook", "--state", "DE"], capsys)
    assert code == cli.EXIT_FAILED and home.runs() == []
    assert "export REPEATERBOOK=" in err and "--doppler-project" in err
    assert "App #114" in err and "api_apps.php" in err


def test_the_unit_not_installed_is_refused_by_name_before_the_token_is_read(
    home: Home, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home.python.unlink()
    code, _, err = _run(["maps", "repeaters", "fetch-repeaterbook", "--state", "DE"], capsys)
    assert code == cli.EXIT_FAILED and home.runs() == []
    assert "hammunition install repeaterbook-client" in err and "App #114" in err


def test_an_unknown_state_is_refused_before_any_run(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _run(["maps", "repeaters", "fetch-repeaterbook", "--state", "ZZ"], capsys)
    assert code == cli.EXIT_FAILED and "'ZZ'" in err and home.runs() == []


def test_a_changed_format_writes_nothing_and_names_the_field(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    home.answer({"ok": True, **json.loads(FIXTURE.read_text().replace('"Callsign"', '"Call"'))})
    code, _, err = _run(["maps", "repeaters", "fetch-repeaterbook", "--state", "DE"], capsys)
    assert code == cli.EXIT_FAILED and "no Callsign field" in err
    assert not home.layer.exists()


def _fake_doppler(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    script = bin_dir / "doppler"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' '{TOKEN}'\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def test_doppler_supplies_the_token_when_the_environment_does_not(
    home: Home,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    monkeypatch.delenv(rb.TOKEN_ENV)
    _fake_doppler(home.root, monkeypatch)
    save_station(
        Saved(secrets_doppler_project="hammunition", secrets_doppler_config="dev"), home.station
    )
    code, out, err = _run(["maps", "repeaters", "fetch-repeaterbook", "--state", "DE"], capsys)
    assert code == 0, out + err
    assert home.runs()[0]["token"] == TOKEN
    logs = "".join(p.read_text() for p in _run_logs_in_tmp.glob("*.log"))
    assert TOKEN not in out + err + logs


# -- policy: never mirrored, never listed, personal, credited ---------------------------


def test_the_layer_is_never_mirrored_even_when_the_station_names_a_mirror(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    import http.server
    import threading

    seen: list[str] = []

    class Spy(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Spy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        save_station(Saved(mirror=f"http://127.0.0.1:{server.server_address[1]}/"), home.station)
        code, out, err = _run(["maps", "repeaters", "fetch-repeaterbook", "--state", "DE"], capsys)
    finally:
        server.shutdown()
        server.server_close()
    assert code == 0, out + err
    assert seen == [], "RepeaterBook data is never read from a mirror"
    assert len(home.runs()) == 1


def test_artifacts_never_lists_it() -> None:
    from hammunition import repeater_sources as rs

    assert all("repeaterbook" not in s.name for s in rs.snapshots())
    assert "repeaterbook" not in rs.SNAPSHOT_UNIT


def test_every_rendering_credits_repeaterbook_with_a_link_and_is_private(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    import sqlite3

    assert cli.main(["maps", "repeaters", "fetch-repeaterbook", "--state", "DE"]) == 0
    capsys.readouterr()
    gpx, poi, navit, rows = (home.layer / n for n in repeaters.layer_files("repeaterbook"))
    for path in (gpx, poi, navit, rows):
        assert path.stat().st_mode & 0o777 == 0o600, path.name
    assert "repeaterbook" in navit.name  # Navit's textfile has no place for a title or a link
    text = gpx.read_text()
    assert "<metadata><name>Repeaters (RepeaterBook, personal use, " in text
    assert text.count("<src>RepeaterBook (https://www.repeaterbook.com)") == 2
    assert "not be shared, re-served, mirrored" in text and "App #114" in text
    db = sqlite3.connect(poi)
    try:
        (comment,) = db.execute("SELECT value FROM metadata WHERE name = 'comment'").fetchone()
        points = [r[0] for r in db.execute("SELECT data FROM poi_data")]
    finally:
        db.close()
    link = re.compile(r"\(https://www\.repeaterbook\.com\)")
    assert "RepeaterBook" in comment and link.search(comment)
    assert all(link.search(p) for p in points)
