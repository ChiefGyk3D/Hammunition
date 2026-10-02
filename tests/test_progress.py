# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The plan's progress reporter and its bounded-concurrency check runner (#197).

Timing is never asserted. The one measurement is in
:func:`test_fifty_slow_checks_run_four_at_a_time`: a fake server that sleeps
0.2 s per request, 50 tiles. Measured 2026-10-02 on the development host:
sequential 10.0 s, four workers 2.6 s (the ratio is the point, not the
numbers). CI asserts only order and completeness.
"""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import pytest

from hammunition.progress import CHECK_WORKERS, Outcome, Progress, run_checks


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def make(stream: io.StringIO, clock: Clock) -> Progress:
    return Progress(stream, clock=clock)


def test_silent_when_stderr_is_not_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAMMUNITION_PROGRESS", raising=False)
    out = io.StringIO()
    p = Progress(out)
    p.start("terrain tiles against the publisher", 3)
    p.tick()
    p.done()
    assert out.getvalue() == ""


def test_env_forces_it_on_for_a_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAMMUNITION_PROGRESS", "1")
    out = io.StringIO()
    p = Progress(out)
    p.start("terrain tiles against the publisher", 3)
    p.done()
    assert "checking 3 terrain tiles against the publisher (needs the network)" in out.getvalue()


def test_env_other_values_do_not_force(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAMMUNITION_PROGRESS", "0")
    out = io.StringIO()
    Progress(out).start("x", 3)
    assert out.getvalue() == ""


def test_start_line_counter_and_final_line_on_a_terminal() -> None:
    out, clock = Tty(), Clock()
    p = make(out, clock)
    p.start("terrain tiles against the Copernicus bucket", 412)
    assert out.getvalue() == (
        "checking 412 terrain tiles against the Copernicus bucket (needs the network)…\n"
    )
    clock.now += 1.0
    for _ in range(136):
        p.tick()
    clock.now += 0.6
    p.tick()
    assert out.getvalue().endswith("\r  137/412")
    clock.now += 29.6
    for _ in range(412 - 137):
        p.tick()
    p.done()
    text = out.getvalue()
    assert text.endswith("checked 412 terrain tiles against the Copernicus bucket in 31.2 s\n")


def test_counter_is_throttled_to_half_a_second() -> None:
    out, clock = Tty(), Clock()
    p = make(out, clock)
    p.start("tiles", 100)
    before = out.getvalue()
    for _ in range(50):  # the clock never moves
        p.tick()
    assert out.getvalue() == before
    clock.now += 0.4
    p.tick()
    assert out.getvalue() == before
    clock.now += 0.2
    p.tick()
    assert out.getvalue().endswith("  52/100")


def test_nothing_is_said_for_an_empty_list() -> None:
    out = Tty()
    p = make(out, Clock())
    p.start("tiles", 0)
    p.done()
    assert out.getvalue() == ""


def test_never_writes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    out = Tty()
    p = make(out, Clock())
    p.start("tiles", 2)
    p.tick()
    p.tick()
    p.done()
    assert capsys.readouterr().out == ""


def test_run_checks_keeps_input_order_and_completes() -> None:
    items = [f"t{i}" for i in range(23)]

    def slow_for_early(item: str) -> int:
        n = int(item[1:])
        time.sleep(0.01 if n < 4 else 0)  # early items finish last
        return n * 2

    outcomes = run_checks(items, slow_for_early, label="tiles")
    assert [o.get() for o in outcomes] == [i * 2 for i in range(23)]


def test_run_checks_reports_errors_per_item_and_runs_the_rest() -> None:
    def fn(item: int) -> int:
        if item % 3 == 0:
            raise OSError(f"no route to {item}")
        return item

    outcomes = run_checks(list(range(9)), fn, label="tiles")
    assert len(outcomes) == 9
    for item, outcome in enumerate(outcomes):
        if item % 3 == 0:
            with pytest.raises(OSError, match=f"no route to {item}"):
                outcome.get()
        else:
            assert outcome.get() == item


def test_run_checks_on_nothing() -> None:
    assert run_checks([], lambda x: x, label="tiles") == []


def test_outcome_get_returns_or_raises() -> None:
    assert Outcome(value=3).get() == 3
    with pytest.raises(ValueError, match="boom"):
        Outcome(error=ValueError("boom")).get()


def test_workers_are_four() -> None:
    assert CHECK_WORKERS == 4


def test_never_more_than_four_in_flight() -> None:
    lock = threading.Lock()
    live = 0
    peak = 0

    def fn(_item: int) -> None:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.02)
        with lock:
            live -= 1

    run_checks(list(range(20)), fn, label="tiles")
    assert 1 < peak <= CHECK_WORKERS


def test_progress_counts_every_item_through_run_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    out = Tty()
    clock = Clock()
    p = make(out, clock)
    run_checks(list(range(7)), lambda x: x, label="sheets against the publisher", progress=p)
    text = out.getvalue()
    assert text.startswith("checking 7 sheets against the publisher (needs the network)…\n")
    assert "checked 7 sheets against the publisher in 0.0 s" in text


def test_fifty_slow_checks_run_four_at_a_time() -> None:
    """A fake server that sleeps 0.2 s per request, 50 tiles: sequential 10.0 s,
    four workers 2.6 s on the development host (2026-10-02). Not asserted."""
    delay = 0.02  # a tenth of the measured fake, so the suite stays fast
    names = [f"tile-{i:02d}" for i in range(50)]
    asked: list[str] = []

    def head(name: str) -> tuple[int, int]:
        time.sleep(delay)
        asked.append(name)
        return 200, len(name)

    outcomes = run_checks(names, head, label="tiles")
    assert [o.get() for o in outcomes] == [(200, len(n)) for n in names]
    assert sorted(asked) == names


# -- the plan's checks use it ---------------------------------------------------


def test_the_terrain_plan_says_what_it_waits_on_and_keeps_stdout_clean(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from hammunition.copernicus import tile_url
    from hammunition.terrain_plan import poly_url, resolve_terrain
    from test_terrain_plan import LIST, MD5, OUTLINE, A, B, C, RegionProbe, TileProbe, _ok

    monkeypatch.setenv("HAMMUNITION_PROGRESS", "1")
    heads = _ok(A, B, C)
    heads[tile_url(B)] = (404, 0, None)  # one refusal, reported by name as before
    got = None
    with pytest.raises(Exception, match=f"{B}: .*answered HTTP 404"):
        got = resolve_terrain(
            [("atlantis/oceania", "atlantis-oceania")],
            installed=tmp_path,
            tile_list=LIST,
            pins={},
            region_probe=RegionProbe({poly_url("atlantis/oceania"): OUTLINE}),
            tile_probe=TileProbe(heads),
        )
    assert got is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "checking 3 terrain tiles against the Copernicus DEM bucket (needs the network)…" in (
        captured.err
    )
    assert "checked 3 terrain tiles against the Copernicus DEM bucket in " in captured.err
    assert MD5  # the fixture's digest is what the other tiles resolved against


def test_json_output_is_byte_identical_with_progress_forced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from test_json_install import _machine, _run

    _machine(monkeypatch, tmp_path)
    monkeypatch.delenv("HAMMUNITION_PROGRESS", raising=False)
    rc, quiet = _run(capsys, "install", "--dry-run", "--json", "fixture-apt")
    capsys.readouterr()
    monkeypatch.setenv("HAMMUNITION_PROGRESS", "1")
    rc2, loud = _run(capsys, "install", "--dry-run", "--json", "fixture-apt")
    assert rc == rc2 == 0
    assert quiet == loud
    assert quiet.startswith("{")
