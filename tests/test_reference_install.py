# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The chosen books, resolved before the plan prints.  D-065.

Resolution asks nothing of the network for a book already installed at its
pin. Every book about to be fetched is asked for once, by ``HEAD``, so a pin
Kiwix has dropped refuses the plan -- naming the regeneration -- before apt
or anything else runs, rather than after.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hammunition.backends.kiwix import resolve_station_books
from hammunition.kiwix import KiwixError

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "catalog"
HAM = "ham.stackexchange.com_en_all"


def _catalog(tmp_path: Path) -> Path:
    root = tmp_path / "catalog"
    (root / "data").mkdir(parents=True)
    for name in ("kiwix-books.yaml", "kiwix-pins.yaml"):
        shutil.copy(CATALOG / "data" / name, root / "data" / name)
    return root


def test_a_chosen_book_resolves_after_one_head(tmp_path: Path) -> None:
    asked: list[str] = []

    def head(url: str) -> int:
        asked.append(url)
        return 200

    [book] = resolve_station_books((HAM,), _catalog(tmp_path), installed=tmp_path / "d", head=head)
    assert book.book.licence == "CC BY-SA"
    assert asked == [book.pin.url]


def test_an_installed_book_needs_no_network(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    [book] = resolve_station_books((HAM,), catalog, installed=tmp_path / "d", head=lambda _u: 200)
    installed = tmp_path / "d"
    installed.mkdir()
    with (installed / book.pin.file).open("wb") as fh:
        fh.truncate(book.pin.size)

    def head(url: str) -> int:
        raise AssertionError(f"asked {url}")

    assert resolve_station_books((HAM,), catalog, installed=installed, head=head) == [book]


def test_a_pin_kiwix_has_dropped_refuses_naming_the_generator(tmp_path: Path) -> None:
    with pytest.raises(KiwixError) as excinfo:
        resolve_station_books(
            (HAM,), _catalog(tmp_path), installed=tmp_path / "d", head=lambda _u: 404
        )
    text = str(excinfo.value)
    assert HAM in text and "404" in text and "scripts/gen_kiwix_pins.py" in text
    assert "two" in text  # why the pin went: Kiwix keeps two dated files


def test_offline_a_book_not_installed_refuses_by_name(tmp_path: Path) -> None:
    def head(url: str) -> int:
        raise KiwixError(f"{url} could not be reached: no route")

    with pytest.raises(KiwixError, match="could not be reached"):
        resolve_station_books((HAM,), _catalog(tmp_path), installed=tmp_path / "d", head=head)


def test_an_unknown_book_refuses_naming_the_list(tmp_path: Path) -> None:
    with pytest.raises(KiwixError, match="hammunition reference books"):
        resolve_station_books(
            ("nope_en_all",), _catalog(tmp_path), installed=tmp_path / "d", head=lambda _u: 200
        )


# ---------------------------------------------------------------------------
# Through `install --dry-run`: the disclosure, and the refusal of a dead pin
# ---------------------------------------------------------------------------

KIWIX_LIBRARY = """\
name: kiwix-library
version: "station"
summary: the chosen Kiwix books
categories: [references]
install:
  - install:
      method: kiwix-books
      provider: kiwix
update:
  probe:
    method: kiwix
documentation:
  what_it_does: Keeps the Kiwix books chosen in station config.
  why_you_want_it: An encyclopaedia and a ham Q&A with no network at all.
  upstream_url: https://kiwix.org/
"""


def _dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    status: int,
    books: tuple[str, ...] = (HAM,),
    installed: bool = False,
) -> tuple[int, str, str]:
    import importlib

    from hammunition.kiwix import KiwixProbe
    from hammunition.station import Station, save_station
    from json_support import FIXTURE_CATALOG
    from test_json_install import _machine

    cli = importlib.import_module("hammunition.cli.main")
    _machine(monkeypatch, tmp_path)
    catalog = tmp_path / "catalog"
    shutil.copytree(FIXTURE_CATALOG, catalog)
    shutil.copytree(CATALOG / "data", catalog / "data", dirs_exist_ok=True)
    (catalog / "packages" / "kiwix-library.yaml").write_text(KIWIX_LIBRARY)
    save_station(
        Station(reference_books=books),
        path=tmp_path / "xdg_config_home" / "hammunition" / "station.yml",
    )
    asked: list[str] = []

    def head(self: KiwixProbe, url: str) -> int:
        asked.append(url)
        return status

    monkeypatch.setattr(KiwixProbe, "head", head)
    # The prefix is the test's, so an installed book can be put there.
    prefix = tmp_path / "prefix"
    real = cli.SourceBackend
    monkeypatch.setattr(cli, "SourceBackend", lambda *a, **k: real(*a, **{**k, "prefix": prefix}))
    if installed:
        from hammunition.kiwix import load_pin_file

        pin = load_pin_file(catalog)[HAM]
        where = prefix / "share" / "hammunition" / "data" / "kiwix-library"
        where.mkdir(parents=True)
        with (where / pin.file).open("wb") as fh:
            fh.truncate(pin.size)
    rc = cli.main(["--catalog", str(catalog), "install", "--dry-run", "kiwix-library"])
    captured = capsys.readouterr()
    assert len(asked) == (0 if installed else len(books))
    return rc, captured.out, captured.err


def test_the_dry_run_prints_each_books_size_and_licence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, err = _dry_run(monkeypatch, tmp_path, capsys, status=200)
    assert rc == 0, err
    assert f"Fetch reference book {HAM} (2026-08, 75.9 MB, CC BY-SA)" in out
    assert "Delete the cached download" in out


def test_the_dry_run_refuses_a_dead_pin_before_anything_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib

    cli = importlib.import_module("hammunition.cli.main")
    rc, out, err = _dry_run(monkeypatch, tmp_path, capsys, status=404)
    assert rc == cli.EXIT_UNPLANNABLE
    assert "scripts/gen_kiwix_pins.py" in err and "Nothing was changed" in err
    assert "Fetch reference book" not in out


def test_a_book_installed_at_its_pin_reads_already_installed_and_asks_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, err = _dry_run(monkeypatch, tmp_path, capsys, status=500, installed=True)
    assert rc == 0, err
    assert "Fetch reference book" not in out
    line = next(ln for ln in out.splitlines() if "kiwix-library" in ln)
    assert "already installed" in line
