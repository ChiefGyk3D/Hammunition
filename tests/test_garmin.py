# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``mkgmap`` converter: a Garmin map per region.  D-061.

Synthetic regions only (``atlantis/oceania``, ``atlantis/lemuria``); the
fakes in :mod:`fake_tools` stand in for mkgmap-splitter and mkgmap.
"""

from __future__ import annotations

import fcntl
import hashlib
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import hammunition
from fake_tools import arg, calls, install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.garmin import CONVERTER, MKGMAP_HEAP, SPLITTER_HEAP, GarminConverter
from hammunition.backends.regions import MapLedger
from hammunition.backends.staging import REFUSED, Staging
from hammunition.geofabrik import RegionFile
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest

#: The engine is not root, whoever runs the suite (``unshare -r`` included).
NOT_ROOT = 1000

BODY = b"p" * 10
OCEANIA = RegionFile(
    "atlantis/oceania",
    "260101",
    "https://download.geofabrik.de/atlantis/oceania-260101.osm.pbf",
    10,
    hashlib.sha256(BODY).hexdigest(),
    None,
)
LEMURIA = RegionFile(
    "atlantis/lemuria",
    "260101",
    "https://download.geofabrik.de/atlantis/lemuria-260101.osm.pbf",
    10,
    None,
    hashlib.md5(BODY, usedforsecurity=False).hexdigest(),
)

SPLITTER_OK = 'd=$(echo "$*" | sed -n "s/.*--output-dir=\\([^ ]*\\).*/\\1/p"); echo "mapname: 1" > "$d/template.args"; echo tile > "$d/63240001.osm.pbf"'
MKGMAP_OK = 'd=$(echo "$*" | sed -n "s/.*--output-dir=\\([^ ]*\\).*/\\1/p"); printf garmin > "$d/gmapsupp.img"'


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "osm-garmin",
            "version": "station",
            "summary": "Garmin maps for a test",
            "categories": ["navigation-maps"],
            "depends": ["osm-regions", "mkgmap"],
            "install": [
                {
                    "install": {
                        "method": "derived",
                        "converter": "mkgmap",
                        "source": "osm-regions",
                        "licence": "ODbL-1.0",
                        "licence_url": "https://www.openstreetmap.org/copyright",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Garmin maps for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://www.mkgmap.org.uk/",
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
    return pbf


def _converter(tmp_path: Path, files: list[RegionFile], **kw: Any) -> GarminConverter:
    return GarminConverter(
        prefix=tmp_path,
        files=files,
        staging=Staging(tmp_path / "staging", euid=NOT_ROOT),
        jobs=4,
        **kw,
    )


def _actions(steps: list[Action | Command]) -> list[Action]:
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _run(conv: GarminConverter) -> list[str]:
    m = manifest()
    return [step.perform() for step in _actions(conv.steps(m, _block(m)))]


def test_the_split_and_the_build_run_with_their_fixed_argv_in_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(
        monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": MKGMAP_OK}
    )
    pbf = _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv)
    assert conv.ledger.failed == {}
    work = tmp_path / "staging" / f"{OCEANIA.slug}.work"
    (split_cwd, split), (build_cwd, build) = calls(log)
    assert split_cwd == str(work)
    assert split == (
        f"mkgmap-splitter --output=pbf --max-nodes=1600000 --output-dir={work / 'split'} {pbf}"
    )
    assert build_cwd == str(work / "split")
    assert build == (
        f"mkgmap --output-dir={work / 'img'} --style=default --route --add-pois-to-areas "
        f"--unicode --gmapsupp --max-jobs=4 -c {work / 'split' / 'template.args'}"
    )
    assert "--index" not in build and "--housenumbers" not in build
    out = _data(tmp_path, "osm-garmin")
    assert (out / f"{OCEANIA.slug}.img").read_bytes() == b"garmin"
    assert (out / f"{OCEANIA.slug}.img.source").read_text() == f"260101\nconverter: {CONVERTER}\n"
    assert list(work.iterdir()) == [], "the scratch is cleared after a successful build"


def test_each_program_gets_its_heap_through_the_staging_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {
            "mkgmap-splitter": f'echo "$JAVA_OPTS" > {tmp_path}/heap; {SPLITTER_OK}',
            "mkgmap": f'echo "$JAVA_TOOL_OPTIONS" > {tmp_path}/mkgmap-heap; {MKGMAP_OK}',
        },
    )
    _install_region(tmp_path, OCEANIA)
    conv = GarminConverter(
        prefix=tmp_path,
        files=[OCEANIA],
        staging=Staging(
            tmp_path / "staging",
            euid=NOT_ROOT,
            environ={"JAVA_OPTS": SPLITTER_HEAP, "JAVA_TOOL_OPTIONS": MKGMAP_HEAP},
        ),
    )
    _run(conv)
    assert (tmp_path / "heap").read_text().strip() == "-Xmx4000m"
    assert (tmp_path / "mkgmap-heap").read_text().strip() == "-Xmx6000m"


def test_mkgmap_exiting_zero_with_no_map_fails_that_region_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = 'd=$(echo "$*" | sed -n "s/.*--output-dir=\\([^ ]*\\).*/\\1/p"); case "$*" in *oceania*) : ;; *) printf garmin > "$d/gmapsupp.img";; esac'
    install_fakes(monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": empty})
    _install_region(tmp_path, OCEANIA)
    _install_region(tmp_path, LEMURIA)
    conv = _converter(tmp_path, [OCEANIA, LEMURIA])
    outcomes = _run(conv)
    assert any("FAILED" in o and "atlantis/oceania" in o for o in outcomes)
    assert list(conv.ledger.failed) == [f"osm-garmin:{OCEANIA.slug}"]
    out = _data(tmp_path, "osm-garmin")
    assert not (out / f"{OCEANIA.slug}.img").exists()
    assert (out / f"{LEMURIA.slug}.img").exists()
    assert list((tmp_path / "staging" / f"{OCEANIA.slug}.work").iterdir()) == [], (
        "a failed build's scratch goes too"
    )


def test_a_splitter_failure_names_the_region_and_skips_mkgmap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {"mkgmap-splitter": "echo 'out of memory' >&2; exit 1", "mkgmap": MKGMAP_OK},
    )
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv)
    message = conv.ledger.failed[f"osm-garmin:{OCEANIA.slug}"]
    assert "atlantis/oceania" in message and "out of memory" in message
    assert [c for _, c in calls(log) if c.startswith("mkgmap ")] == []


def test_a_region_that_did_not_install_is_not_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(
        monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": MKGMAP_OK}
    )
    regions = MapLedger()
    regions.fail(OCEANIA.slug, "atlantis/oceania: md5 did not match")
    conv = _converter(tmp_path, [OCEANIA], regions=regions)
    outcomes = _run(conv)
    assert outcomes[0].startswith("skipped")
    assert conv.ledger.failed == {}, "the region's own ledger already names it"
    assert calls(log) == []


def test_a_current_map_is_not_rebuilt_and_a_dropped_one_is_removed(tmp_path: Path) -> None:
    out = _data(tmp_path, "osm-garmin")
    out.mkdir(parents=True)
    (out / f"{OCEANIA.slug}.img").write_bytes(b"garmin")
    (out / f"{OCEANIA.slug}.img.source").write_text(f"260101\nconverter: {CONVERTER}\n")
    (out / "atlantis-sunk.img").write_bytes(b"old")
    conv = _converter(tmp_path, [OCEANIA])
    m = manifest()
    assert conv.pending(m) == []
    steps = _actions(conv.steps(m, _block(m)))
    assert [s.kind for s in steps] == ["remove-data"]
    for step in steps:
        step.perform()
    assert not (out / "atlantis-sunk.img").exists()
    assert (out / f"{OCEANIA.slug}.img").exists()


def test_the_step_states_the_factors_it_estimates_by(tmp_path: Path) -> None:
    conv = _converter(tmp_path, [OCEANIA])
    m = manifest()
    (convert, install) = _actions(conv.steps(m, _block(m)))
    assert "0.85x the download" in convert.description
    assert "measured on one region" in convert.description
    assert convert.requires_root is False
    assert install.detail == str(_data(tmp_path, "osm-garmin") / f"{OCEANIA.slug}.img")
    assert arg(convert.description, "--output-dir")


def test_a_leftover_from_an_interrupted_build_is_cleared_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review focus: a build killed halfway leaves its tiles; the next run
    must not hand them to mkgmap as this region's."""
    install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {
            "mkgmap-splitter": f"test ! -e {tmp_path}/staging/{OCEANIA.slug}.work/split/stale || exit 3; {SPLITTER_OK}",
            "mkgmap": MKGMAP_OK,
        },
    )
    stale = tmp_path / "staging" / f"{OCEANIA.slug}.work" / "split" / "stale"
    stale.parent.mkdir(parents=True)
    stale.write_text("from a killed run")
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv)
    assert conv.ledger.failed == {}
    assert (_data(tmp_path, "osm-garmin") / f"{OCEANIA.slug}.img").exists()


def test_a_busy_working_directory_fails_that_region_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another conversion holding the region's working directory: the run is
    refused with 125 before anything starts, and the region fails by name."""
    log = install_fakes(
        monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": MKGMAP_OK}
    )
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    lock = conv.staging.workdir(OCEANIA.slug).with_name(f"{OCEANIA.slug}.work.lock")
    tile = lock.parent / f"{OCEANIA.slug}.work" / "split" / "63240001.osm.pbf"
    tile.parent.mkdir(parents=True)
    tile.write_text("another run's tile")
    with lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        _run(conv)
    message = conv.ledger.failed[f"osm-garmin:{OCEANIA.slug}"]
    assert "atlantis/oceania" in message and "was not started" in message
    assert "another conversion" in message
    assert calls(log) == []
    assert tile.read_text() == "another run's tile", "a busy refusal deletes nothing"
    assert not (_data(tmp_path, "osm-garmin") / f"{OCEANIA.slug}.img").exists()


def test_the_outcome_says_who_built_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fakes(
        monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": MKGMAP_OK}
    )
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    monkeypatch.setattr(Staging, "who", lambda self: "as operator")
    built, _ = _run(conv)
    assert built.startswith("built the Garmin map of atlantis/oceania as operator")


def test_root_with_nobody_to_run_as_fails_the_region_and_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Root, a staging directory under no home and not root's own: nothing is
    run as root, and the region fails by name with the reason."""
    log = install_fakes(
        monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": MKGMAP_OK}
    )
    _install_region(tmp_path, OCEANIA)
    conv = GarminConverter(
        prefix=tmp_path, files=[OCEANIA], staging=Staging(tmp_path / "staging", euid=0)
    )
    _run(conv)
    message = conv.ledger.failed[f"osm-garmin:{OCEANIA.slug}"]
    assert message.startswith("atlantis/oceania: ") and "refusing" in message
    assert calls(log) == []


def _refuse(monkeypatch: pytest.MonkeyPatch, program: str, plant: Path) -> None:
    """*program*'s run is refused (125) after another conversion wrote *plant*."""
    real = Staging.run

    def run(self: Staging, argv: Any, *, cwd: Path, **kw: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == program:
            plant.write_text("another run's file")
            return subprocess.CompletedProcess(list(argv), REFUSED, "", "held by another")
        return real(self, argv, cwd=cwd, **kw)

    monkeypatch.setattr(Staging, "run", run)


@pytest.mark.parametrize("program", ["mkgmap-splitter", "mkgmap"])
def test_a_refused_run_leaves_the_working_directory_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, program: str
) -> None:
    install_fakes(
        monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": MKGMAP_OK}
    )
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    foreign = conv.staging.workdir(OCEANIA.slug) / "split" / "foreign-tile.osm.pbf"
    _refuse(monkeypatch, program, foreign)
    outcomes = _run(conv)
    message = conv.ledger.failed[f"osm-garmin:{OCEANIA.slug}"]
    assert "atlantis/oceania" in message and f"{program} was not started" in message
    assert foreign.read_text() == "another run's file"
    assert outcomes[1].startswith("skipped")


def test_the_heaps_are_jvm_max_heap_options() -> None:
    for heap in (SPLITTER_HEAP, MKGMAP_HEAP):
        assert re.fullmatch(r"-Xmx[0-9]+[mg]", heap), heap
    assert MKGMAP_HEAP == "-Xmx6000m"


def test_the_step_states_mkgmaps_memory_need(tmp_path: Path) -> None:
    conv = _converter(tmp_path, [OCEANIA])
    m = manifest()
    convert = _actions(conv.steps(m, _block(m)))[0]
    assert "needs about 6 GB free for mkgmap" in convert.description


def test_a_map_from_before_the_converter_was_recorded_is_rebuilt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(
        monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": MKGMAP_OK}
    )
    _install_region(tmp_path, OCEANIA)
    out = _data(tmp_path, "osm-garmin")
    out.mkdir(parents=True)
    (out / f"{OCEANIA.slug}.img").write_bytes(b"old garmin")
    (out / f"{OCEANIA.slug}.img.source").write_text("260101\n")
    conv = _converter(tmp_path, [OCEANIA])
    assert conv.pending(manifest()) == [OCEANIA]
    _run(conv)
    assert (out / f"{OCEANIA.slug}.img").read_bytes() == b"garmin"
    assert (out / f"{OCEANIA.slug}.img.source").read_text() == f"260101\nconverter: {CONVERTER}\n"


def test_a_map_from_another_converter_version_is_rebuilt(tmp_path: Path) -> None:
    out = _data(tmp_path, "osm-garmin")
    out.mkdir(parents=True)
    (out / f"{OCEANIA.slug}.img").write_bytes(b"old garmin")
    (out / f"{OCEANIA.slug}.img.source").write_text("260101\nconverter: mkgmap 0\n")
    assert _converter(tmp_path, [OCEANIA]).pending(manifest()) == [OCEANIA]


def test_nothing_can_clear_a_region_while_mkgmap_builds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The re-review's probe: mkgmap runs in ``split/`` but holds the region's
    one lock, ``<slug>.work.lock``, so a clear of the region during the build
    is refused (125) and the build's tiles survive it."""
    staging_dir = tmp_path / "staging"
    work = staging_dir / f"{OCEANIA.slug}.work"
    probe = (
        "from pathlib import Path; from hammunition.backends.staging import Staging; "
        f"print(Staging(Path({str(staging_dir)!r}), euid={NOT_ROOT})"
        f".clear(Path({str(work)!r})).returncode)"
    )
    install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {
            "mkgmap-splitter": SPLITTER_OK,
            "mkgmap": f"{sys.executable} -c {shlex.quote(probe)} > {tmp_path}/probe; "
            f"test -e 63240001.osm.pbf || exit 4; {MKGMAP_OK}",
        },
    )
    monkeypatch.setenv("PYTHONPATH", str(Path(hammunition.__file__).parent.parent))
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv)
    assert (tmp_path / "probe").read_text().strip() == str(REFUSED)
    assert conv.ledger.failed == {}, "the tiles survived the refused clear"
    assert not (work / "split.lock").exists(), "no second lock name for the region"


def _clear_fails_from(monkeypatch: pytest.MonkeyPatch, call: int) -> None:
    """Every :meth:`Staging.clear` from the *call*-th on fails (1-based)."""
    real = Staging.clear
    seen = [0]

    def clear(self: Staging, cwd: Path, **kw: Any) -> subprocess.CompletedProcess[str]:
        seen[0] += 1
        if seen[0] >= call:
            return subprocess.CompletedProcess(["find"], 1, "", "find: cannot delete: boom")
        return real(self, cwd, **kw)

    monkeypatch.setattr(Staging, "clear", clear)


def test_an_install_whose_scratch_did_not_clear_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(
        monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": MKGMAP_OK}
    )
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _clear_fails_from(monkeypatch, 2)
    _, installed = _run(conv)
    assert "cleared" not in installed.replace("not cleared", "")
    message = conv.ledger.failed[f"osm-garmin:{OCEANIA.slug}"]
    assert "atlantis/oceania" in message and "boom" in message and "not cleared" in message
    assert (_data(tmp_path, "osm-garmin") / f"{OCEANIA.slug}.img").exists()


def test_a_failed_build_whose_scratch_did_not_clear_names_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {"mkgmap-splitter": "echo 'out of memory' >&2; exit 1", "mkgmap": MKGMAP_OK},
    )
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _clear_fails_from(monkeypatch, 2)
    _run(conv)
    message = conv.ledger.failed[f"osm-garmin:{OCEANIA.slug}"]
    assert "out of memory" in message and "not cleared" in message and "boom" in message


def test_a_pre_clear_that_fails_fails_the_region_and_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(
        monkeypatch, tmp_path / "bin", {"mkgmap-splitter": SPLITTER_OK, "mkgmap": MKGMAP_OK}
    )
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _clear_fails_from(monkeypatch, 1)
    _run(conv)
    assert "boom" in conv.ledger.failed[f"osm-garmin:{OCEANIA.slug}"]
    assert calls(log) == []
