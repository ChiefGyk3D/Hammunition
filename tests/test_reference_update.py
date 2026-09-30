# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`update` for the Kiwix books: offline against the pins, and upstream.  D-066.

Offline the question is the machine against the catalog: is each chosen
book's pinned file installed. Upstream it is the catalog against Kiwix: is
the pinned file still the newest, and is it still published at all --
Kiwix keeps two dated files per book, so a pin goes on Kiwix's calendar.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from hammunition.kiwix import Book, BookFile, BookPin, KiwixError, KiwixGone
from hammunition.update import BEHIND_PIN, NOT_INSTALLED, UP_TO_DATE, books_state
from hammunition.upstream import CURRENT, EXPIRED, NEWER_UPSTREAM, UNANSWERED, probe_kiwix, render

MED = Book(
    id="wikipedia_en_medicine_nopic",
    name="wikipedia_en_medicine",
    flavour="nopic",
    category="wikipedia",
    title="WikiMed",
    licence="CC BY-SA 4.0 (text; media individually licensed)",
    licence_url="https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
)
FILE = "wikipedia_en_medicine_nopic_2026-04.zim"
URL = f"https://download.kiwix.org/zim/wikipedia/{FILE}"
BOOK = BookFile(MED, BookPin(MED.id, FILE, URL, 10, "a" * 64, "2026-04", "2026-09-29"))
OPDS_URL = "https://opds.library.kiwix.org/catalog/v2/entries?name=wikipedia_en_medicine"


def opds(file: str) -> str:
    return (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        "<name>wikipedia_en_medicine</name><flavour>nopic</flavour>"
        '<link rel="http://opds-spec.org/acquisition/open-access" type="application/x-zim" '
        f'href="https://lb.download.kiwix.org/zim/wikipedia/{file}.meta4" /></entry></feed>'
    )


def _text(answers: dict[str, str], gone: frozenset[str] = frozenset()) -> Callable[[str], str]:
    def text(url: str) -> str:
        if url in gone:
            raise KiwixGone(url)
        if url not in answers:
            raise KiwixError(f"{url} could not be fetched: timed out")
        return answers[url]

    return text


# -- offline -------------------------------------------------------------------


def test_every_chosen_book_at_its_pin_is_up_to_date(tmp_path: Path) -> None:
    (tmp_path / FILE).write_bytes(b"x" * 10)
    state, detail = books_state([BOOK], tmp_path)
    assert state == UP_TO_DATE and "1 book" in detail


def test_a_chosen_book_at_an_older_date_is_behind_the_pin(tmp_path: Path) -> None:
    (tmp_path / "wikipedia_en_medicine_nopic_2025-10.zim").write_bytes(b"old")
    state, detail = books_state([BOOK], tmp_path)
    assert state == BEHIND_PIN and "install kiwix-library" in detail


def test_a_chosen_book_not_on_disk_is_not_installed(tmp_path: Path) -> None:
    state, _ = books_state([BOOK], tmp_path)
    assert state == NOT_INSTALLED


def test_no_books_chosen_is_not_installed_and_says_why(tmp_path: Path) -> None:
    state, detail = books_state([], tmp_path)
    assert state == NOT_INSTALLED and "no reference books chosen" in detail


# -- upstream ------------------------------------------------------------------


def test_the_pinned_file_still_newest_is_current() -> None:
    [row] = probe_kiwix("kiwix-library", [BOOK], text=_text({OPDS_URL: opds(FILE[:-4] + ".zim")}))
    assert row.state == CURRENT
    assert row.unit == "kiwix-library/wikipedia_en_medicine_nopic"


def test_a_newer_file_warns_that_the_pin_goes_at_the_next_publication() -> None:
    newer = "wikipedia_en_medicine_nopic_2026-10.zim"
    [row] = probe_kiwix(
        "kiwix-library",
        [BOOK],
        text=_text({OPDS_URL: opds(newer), f"{URL}.meta4": "<metalink/>"}),
    )
    assert row.state == NEWER_UPSTREAM
    assert row.upstream == "2026-10" and row.catalog == "2026-04"
    assert "next" in row.detail and "scripts/gen_kiwix_pins.py" in row.detail


def test_a_pin_kiwix_no_longer_publishes_is_expired() -> None:
    newer = "wikipedia_en_medicine_nopic_2026-10.zim"
    [row] = probe_kiwix(
        "kiwix-library",
        [BOOK],
        text=_text({OPDS_URL: opds(newer)}, gone=frozenset({f"{URL}.meta4"})),
    )
    assert row.state == EXPIRED
    assert "scripts/gen_kiwix_pins.py" in row.detail
    assert "pin expired" in render([row])


def test_a_timeout_is_unanswered_and_the_rest_stands() -> None:
    [row] = probe_kiwix("kiwix-library", [BOOK], text=_text({}))
    assert row.state == UNANSWERED and "timed out" in row.detail


def test_only_kiwix_hosts_are_asked() -> None:
    asked: list[str] = []

    def text(url: str) -> str:
        asked.append(url)
        return opds(FILE)

    probe_kiwix("kiwix-library", [BOOK], text=text)
    assert asked and all(u.startswith("https://opds.library.kiwix.org/") for u in asked)


# -- through `hammunition update` ------------------------------------------------


def test_update_reports_the_books_offline_and_asks_kiwix_only_with_upstream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib
    import shutil

    from hammunition.kiwix import KiwixProbe, load_pin_file
    from hammunition.station import Station, save_station
    from json_support import FIXTURE_CATALOG
    from test_json_update import _machine
    from test_reference_install import CATALOG, HAM, KIWIX_LIBRARY

    cli = importlib.import_module("hammunition.cli.main")
    _machine(monkeypatch, tmp_path)
    catalog = tmp_path / "catalog"
    shutil.copytree(FIXTURE_CATALOG, catalog)
    shutil.copytree(CATALOG / "data", catalog / "data", dirs_exist_ok=True)
    (catalog / "packages" / "kiwix-library.yaml").write_text(KIWIX_LIBRARY)
    save_station(
        Station(reference_books=(HAM,)), path=tmp_path / "config" / "hammunition" / "station.yml"
    )
    prefix = tmp_path / "prefix"
    real = cli.SourceBackend
    monkeypatch.setattr(cli, "SourceBackend", lambda *a, **k: real(*a, **{**k, "prefix": prefix}))
    pin = load_pin_file(catalog)[HAM]
    where = prefix / "share" / "hammunition" / "data" / "kiwix-library"
    where.mkdir(parents=True)
    with (where / pin.file).open("wb") as fh:
        fh.truncate(pin.size)
    asked: list[str] = []

    def text(self: KiwixProbe, url: str) -> str:
        asked.append(url)
        return (
            '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            f"<name>{HAM}</name>"
            '<link type="application/x-zim" href="https://lb.download.kiwix.org/zim/'
            f'stack_exchange/{pin.file}.meta4" /></entry></feed>'
        )

    monkeypatch.setattr(KiwixProbe, "text", text)
    assert cli.main(["--catalog", str(catalog), "update", "kiwix-library"]) == 0
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.strip().startswith("kiwix-library"))
    assert "up to date" in line and "1 book(s) installed at their pins" in line
    assert asked == []
    assert cli.main(["--catalog", str(catalog), "update", "--upstream", "kiwix-library"]) == 0
    out = capsys.readouterr().out
    assert f"kiwix-library/{HAM}" in out and "the pinned file is Kiwix's newest" in out
    assert len(asked) == 1


def test_a_newer_book_upstream_prints_the_command_that_works() -> None:
    """Final review, I1: a book row's unit is `kiwix-library/<id>`, which is
    not a unit; the advice for a book is the pin generator, then the unit."""
    newer = "wikipedia_en_medicine_nopic_2026-10.zim"
    rows = probe_kiwix(
        "kiwix-library",
        [BOOK],
        text=_text({OPDS_URL: opds(newer), f"{URL}.meta4": "<metalink/>"}),
    )
    text = render(rows)
    assert "hammunition install kiwix-library/" not in text
    assert "`hammunition install kiwix-library`" in text
    assert "scripts/gen_kiwix_pins.py" in text.split("upstream,")[-1]
    assert "measure the build" not in text
