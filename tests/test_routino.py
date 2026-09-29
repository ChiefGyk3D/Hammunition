# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""One Routino database over every region.  D-061.

Synthetic regions only; a fake ``planetsplitter`` stands in for Routino's.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from fake_tools import calls, install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.regions import MapLedger
from hammunition.backends.routino import DB_FILES, RECORD, RoutinoConverter
from hammunition.backends.staging import Staging
from hammunition.geofabrik import RegionFile
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest

BODY = b"p" * 10


def _region(name: str) -> RegionFile:
    return RegionFile(
        f"atlantis/{name}",
        "260101",
        f"https://download.geofabrik.de/atlantis/{name}-260101.osm.pbf",
        10,
        hashlib.sha256(BODY).hexdigest(),
        None,
    )


OCEANIA, LEMURIA = _region("oceania"), _region("lemuria")

#: Writes the four database files on --process-only; fails to parse any
#: region whose path contains FAIL_ON (unset: none).
PLANETSPLITTER = """
dir=$(echo "$*" | sed -n 's/.*--dir=\\([^ ]*\\).*/\\1/p')
case "$*" in
  *--process-only*) for p in nodes segments ways relations; do printf db > "$dir/hammunition-$p.mem"; done ;;
  *"${FAIL_ON:-no-such-region}"*) echo "cannot parse" >&2; exit 1 ;;
  *) printf parsed > "$dir/nodesx.parsed.mem" ;;
esac
"""


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "osm-routino",
            "version": "station",
            "summary": "A Routino database for a test",
            "categories": ["navigation-maps"],
            "depends": ["osm-regions", "routino"],
            "install": [
                {
                    "install": {
                        "method": "derived",
                        "converter": "routino-planetsplitter",
                        "source": "osm-regions",
                        "licence": "ODbL-1.0",
                        "licence_url": "https://www.openstreetmap.org/copyright",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "A routing database for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://www.routino.org/",
            },
        }
    )


def _block(m: PackageManifest) -> DerivedDataInstall:
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    return block


def _data(prefix: Path, unit: str) -> Path:
    return prefix / "share" / "hammunition" / "data" / unit


def _install_region(tmp_path: Path, region: RegionFile) -> Path:
    out = _data(tmp_path, "osm-regions")
    out.mkdir(parents=True, exist_ok=True)
    pbf = out / f"{region.slug}.osm.pbf"
    pbf.write_bytes(BODY)
    (out / f"{region.slug}.osm.pbf.source").write_text(f"{region.snapshot}\n")
    return pbf


#: The engine as the operator, never root, however the suite runs (it also
#: runs under ``unshare -r``, where the real euid is 0).
NOT_ROOT = 4242


def _converter(tmp_path: Path, files: list[RegionFile], **kw: Any) -> RoutinoConverter:
    return RoutinoConverter(
        prefix=tmp_path,
        files=files,
        staging=Staging(tmp_path / "staging", euid=NOT_ROOT),
        euid=NOT_ROOT,
        privileged=False,
        **kw,
    )


def _actions(steps: list[Action | Command]) -> list[Action]:
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _run(conv: RoutinoConverter) -> list[str]:
    m = manifest()
    return [step.perform() for step in _actions(conv.steps(m, _block(m)))]


def test_every_region_is_parsed_into_one_database_then_processed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", {"planetsplitter": PLANETSPLITTER})
    one, two = _install_region(tmp_path, OCEANIA), _install_region(tmp_path, LEMURIA)
    conv = _converter(tmp_path, [OCEANIA, LEMURIA])
    _run(conv)
    assert conv.ledger.failed == {}
    work = tmp_path / "staging" / "routino.work"
    common = f"planetsplitter --dir={work} --prefix=hammunition"
    tagging = "--tagging=/usr/share/routino/tagging.xml"
    assert [c for _, c in calls(log)] == [
        f"{common} {tagging} --parse-only {one}",
        f"{common} {tagging} --parse-only --append {two}",
        f"{common} --process-only",
    ]
    assert {where for where, _ in calls(log)} == {str(work)}
    out = _data(tmp_path, "osm-routino")
    assert all((out / name).read_bytes() == b"db" for name in DB_FILES)
    assert (out / RECORD).read_text() == "atlantis-lemuria 260101\natlantis-oceania 260101\n"
    assert not work.exists()


def test_one_region_that_fails_to_parse_fails_the_database_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAIL_ON", "lemuria")
    log = install_fakes(monkeypatch, tmp_path / "bin", {"planetsplitter": PLANETSPLITTER})
    _install_region(tmp_path, OCEANIA)
    _install_region(tmp_path, LEMURIA)
    out = _data(tmp_path, "osm-routino")
    out.mkdir(parents=True)
    (out / "hammunition-nodes.mem").write_bytes(b"old")
    conv = _converter(tmp_path, [OCEANIA, LEMURIA])
    outcomes = _run(conv)
    message = conv.ledger.failed["osm-routino"]
    assert "atlantis/lemuria" in message and "cannot parse" in message
    assert not any("--process-only" in c for _, c in calls(log))
    assert outcomes[-1].startswith("skipped")
    assert (out / "hammunition-nodes.mem").read_bytes() == b"old", "left as it was"
    assert not (tmp_path / "staging" / "routino.work").exists()


def test_a_region_that_did_not_install_skips_the_database_without_double_reporting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", {"planetsplitter": PLANETSPLITTER})
    _install_region(tmp_path, OCEANIA)
    regions = MapLedger()
    regions.fail(LEMURIA.slug, "atlantis/lemuria: md5 did not match")
    conv = _converter(tmp_path, [OCEANIA, LEMURIA], regions=regions)
    outcomes = _run(conv)
    assert all(o.startswith(("parsed", "skipped")) for o in outcomes)
    assert conv.ledger.failed == {}
    assert not any("--process-only" in c for _, c in calls(log))


def test_process_exiting_zero_without_every_file_fails_the_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = PLANETSPLITTER.replace("nodes segments ways relations", "nodes segments ways")
    install_fakes(monkeypatch, tmp_path / "bin", {"planetsplitter": broken})
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv)
    assert "hammunition-relations.mem" in conv.ledger.failed["osm-routino"]
    assert not (_data(tmp_path, "osm-routino") / RECORD).exists()


def test_a_database_matching_its_record_is_not_rebuilt_and_a_changed_one_is(
    tmp_path: Path,
) -> None:
    _install_region(tmp_path, OCEANIA)
    out = _data(tmp_path, "osm-routino")
    out.mkdir(parents=True)
    for name in DB_FILES:
        (out / name).write_bytes(b"db")
    (out / RECORD).write_text("atlantis-oceania 260101\n")
    m = manifest()
    assert _converter(tmp_path, [OCEANIA]).steps(m, _block(m)) == []
    newer = RegionFile(**{**OCEANIA.__dict__, "snapshot": "270101"})
    assert _converter(tmp_path, [newer]).pending(m, _block(m))
    _install_region(tmp_path, LEMURIA)
    assert len(_converter(tmp_path, [OCEANIA, LEMURIA]).pending(m, _block(m))) == 2


def test_a_kept_region_stays_in_the_database_at_its_installed_snapshot(tmp_path: Path) -> None:
    _install_region(tmp_path, OCEANIA)
    kept = _install_region(tmp_path, LEMURIA)
    (kept.with_name(kept.name + ".source")).write_text("250101\n")
    m = manifest()
    sources = _converter(tmp_path, [OCEANIA], keep=frozenset({LEMURIA.slug})).pending(m, _block(m))
    assert [(s.slug, s.snapshot) for s in sources] == [
        (OCEANIA.slug, "260101"),
        (LEMURIA.slug, "250101"),
    ]


def test_the_steps_state_the_measured_factors_and_the_trade(tmp_path: Path) -> None:
    _install_region(tmp_path, OCEANIA)
    m = manifest()
    steps = _actions(_converter(tmp_path, [OCEANIA]).steps(m, _block(m)))
    process = steps[-2]
    assert "0.67x the downloads together" in process.description
    assert "measured on one region" in process.description
    assert "fails the database" in process.description
    assert not any(s.requires_root for s in steps[:-1])


def test_a_busy_working_directory_fails_the_database_by_name_without_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fcntl

    log = install_fakes(monkeypatch, tmp_path / "bin", {"planetsplitter": PLANETSPLITTER})
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    lock = tmp_path / "staging" / "routino.work.lock"
    lock.parent.mkdir(parents=True)
    with lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        _run(conv)
    message = conv.ledger.failed["osm-routino"]
    assert "atlantis/oceania" in message and "another conversion" in message
    assert calls(log) == []


def test_root_with_nobody_to_run_as_refuses_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", {"planetsplitter": PLANETSPLITTER})
    _install_region(tmp_path, OCEANIA)
    conv = RoutinoConverter(
        prefix=tmp_path, files=[OCEANIA], staging=Staging(tmp_path / "staging", euid=0)
    )
    _run(conv)
    assert "not root's" in conv.ledger.failed["osm-routino"]
    assert calls(log) == []
