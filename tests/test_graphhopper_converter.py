# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""GraphHopper's route graph over every region.  D-076.

Synthetic regions only; fakes stand in for ``java`` and ``osmium``. The real
import was run on a synthetic region with this argv and configuration
(D-076, measured 2026-10-01).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from fake_tools import calls, install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.base import BackendError
from hammunition.backends.graphhopper import GraphConverter
from hammunition.backends.regions import MapLedger
from hammunition.backends.staging import Staging
from hammunition.geofabrik import RegionFile
from hammunition.graphhopper import CONVERTER, RECORD, import_config
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest

BODY = b"p" * 10
JAR = "graphhopper-web-11.1.jar"


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

#: ``import <config>``: the graph location read back from the config the
#: engine wrote, then a graph written there. NO_PROPERTIES leaves its
#: properties file out; FAIL makes it exit 1 having written nothing.
JAVA = """
[ -n "${FAIL:-}" ] && { echo "java failed" >&2; exit 1; }
for a; do cfg=$a; done
loc=$(sed -n 's/^  graph.location: "\\(.*\\)"$/\\1/p' "$cfg")
mkdir -p "$loc"
[ -n "${NO_PROPERTIES:-}" ] || printf props > "$loc/properties"
printf edges > "$loc/edges"
printf ch > "$loc/nodes_ch_car"
"""
OSMIUM = """
while [ "$1" != "-o" ]; do shift; done
printf merged > "$2"
"""
TOOLS = {"java": JAVA, "osmium": OSMIUM}
NOT_ROOT = 4242


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "graphhopper-graph",
            "version": "station",
            "summary": "A route graph for a test",
            "categories": ["navigation-maps"],
            "depends": ["osm-regions", "graphhopper"],
            "install": [
                {
                    "install": {
                        "method": "derived",
                        "converter": "graphhopper-import",
                        "source": "osm-regions",
                        "program": "graphhopper",
                        "licence": "ODbL-1.0",
                        "licence_url": "https://www.openstreetmap.org/copyright",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "A route graph for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://github.com/graphhopper/graphhopper",
            },
        }
    )


def _block(m: PackageManifest) -> DerivedDataInstall:
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    return block


def _data(prefix: Path, unit: str) -> Path:
    return prefix / "share" / "hammunition" / "data" / unit


def _install_jar(prefix: Path, name: str = JAR) -> None:
    tree = prefix / "share" / "hammunition" / "graphhopper"
    tree.mkdir(parents=True, exist_ok=True)
    (tree / name).write_bytes(b"jar")


def _install_region(prefix: Path, region: RegionFile) -> Path:
    out = _data(prefix, "osm-regions")
    out.mkdir(parents=True, exist_ok=True)
    pbf = out / f"{region.slug}.osm.pbf"
    pbf.write_bytes(BODY)
    return pbf


def _converter(tmp_path: Path, files: list[RegionFile], **kw: Any) -> GraphConverter:
    return GraphConverter(
        prefix=tmp_path,
        files=files,
        staging=Staging(tmp_path / "staging", euid=NOT_ROOT),
        euid=NOT_ROOT,
        privileged=False,
        **kw,
    )


def _run(conv: GraphConverter) -> list[str]:
    m = manifest()
    steps = conv.steps(m, _block(m))
    assert all(isinstance(s, Action) for s in steps)
    return [s.perform() for s in steps if isinstance(s, Action)]


def _work(tmp_path: Path) -> Path:
    return tmp_path / "staging" / "graphhopper.work"


def test_one_region_builds_and_installs_the_graph_with_its_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_jar(tmp_path)
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    outcomes = _run(conv)
    assert conv.ledger.failed == {}, outcomes
    work = _work(tmp_path)
    jar = tmp_path / "share" / "hammunition" / "graphhopper" / JAR
    assert [c for _, c in calls(log)] == [f"java -Xmx4000m -jar {jar} import {work}/config.yml"]
    assert {where for where, _ in calls(log)} == {str(work)}
    out = _data(tmp_path, "graphhopper-graph")
    assert (out / "properties").read_bytes() == b"props"
    assert (out / "edges").read_bytes() == b"edges"
    assert (out / RECORD).read_text() == (
        f"atlantis-oceania 260101\nprogram {JAR}\nprofiles car bike foot hike\n"
        f"file edges\nfile nodes_ch_car\nfile properties\nconverter: {CONVERTER}\n"
    )
    assert list(work.iterdir()) == [], "the scratch is cleared, the directory kept"


def test_the_config_the_import_read_is_the_engines_own_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keep = tmp_path / "kept.yml"
    install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {**TOOLS, "java": f'for a; do c=$a; done; cp "$c" {keep}\n' + JAVA},
    )
    _install_jar(tmp_path)
    pbf = _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv)
    assert keep.read_text() == import_config(pbf, _work(tmp_path) / "graph")
    assert yaml.safe_load(keep.read_text())["graphhopper"]["datareader.file"] == str(pbf)


def test_two_regions_are_merged_into_one_input_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keep = tmp_path / "kept.yml"
    log = install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {**TOOLS, "java": f'for a; do c=$a; done; cp "$c" {keep}\n' + JAVA},
    )
    _install_jar(tmp_path)
    one, two = _install_region(tmp_path, OCEANIA), _install_region(tmp_path, LEMURIA)
    conv = _converter(tmp_path, [OCEANIA, LEMURIA])
    _run(conv)
    assert conv.ledger.failed == {}
    work = _work(tmp_path)
    run = [c for _, c in calls(log)]
    assert run[0] == f"osmium merge {one} {two} -o {work}/merged.osm.pbf --overwrite"
    assert yaml.safe_load(keep.read_text())["graphhopper"]["datareader.file"] == str(
        work / "merged.osm.pbf"
    )
    record = (_data(tmp_path, "graphhopper-graph") / RECORD).read_text()
    assert record.startswith("atlantis-lemuria 260101\natlantis-oceania 260101\nprogram ")


def test_the_graph_is_current_until_a_region_the_jar_or_the_converter_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_jar(tmp_path)
    _install_region(tmp_path, OCEANIA)
    m = manifest()
    _run(_converter(tmp_path, [OCEANIA]))
    assert _converter(tmp_path, [OCEANIA]).steps(m, _block(m)) == []
    _install_region(tmp_path, LEMURIA)
    assert _converter(tmp_path, [OCEANIA, LEMURIA]).steps(m, _block(m)) != []
    newer = _converter(tmp_path, [OCEANIA], jar="graphhopper-web-12.0.jar")
    assert newer.steps(m, _block(m)) != [], "a jar bumped in this run rebuilds the graph"
    record = _data(tmp_path, "graphhopper-graph") / RECORD
    record.write_text(record.read_text().replace(CONVERTER, "graphhopper-import 0"))
    assert _converter(tmp_path, [OCEANIA]).steps(m, _block(m)) != []


def test_a_missing_graph_file_rebuilds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_jar(tmp_path)
    _install_region(tmp_path, OCEANIA)
    _run(_converter(tmp_path, [OCEANIA]))
    (_data(tmp_path, "graphhopper-graph") / "edges").unlink()
    m = manifest()
    assert _converter(tmp_path, [OCEANIA]).steps(m, _block(m)) != []


def test_a_file_no_longer_built_and_a_crashed_temporary_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_jar(tmp_path)
    _install_region(tmp_path, OCEANIA)
    out = _data(tmp_path, "graphhopper-graph")
    out.mkdir(parents=True)
    (out / "landmarks_old").write_bytes(b"old")
    (out / "edges.new").write_bytes(b"half")
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv)
    assert conv.ledger.failed == {}
    assert sorted(p.name for p in out.iterdir()) == sorted(
        [RECORD, "edges", "nodes_ch_car", "properties"]
    )


@pytest.mark.parametrize(
    ("env", "why"), [("FAIL", "wrote no graph"), ("NO_PROPERTIES", "no properties")]
)
def test_an_import_that_writes_no_whole_graph_fails_by_name_and_keeps_the_installed_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: str, why: str
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_jar(tmp_path)
    _install_region(tmp_path, OCEANIA)
    out = _data(tmp_path, "graphhopper-graph")
    out.mkdir(parents=True)
    (out / "properties").write_bytes(b"old")
    (out / RECORD).write_text("old record\n")
    monkeypatch.setenv(env, "1")
    conv = _converter(tmp_path, [OCEANIA])
    outcomes = _run(conv)
    assert why in conv.ledger.failed["graphhopper-graph"], outcomes
    assert (out / "properties").read_bytes() == b"old"
    assert (out / RECORD).read_text() == "old record\n"
    assert outcomes[-1].startswith("skipped")
    assert list(_work(tmp_path).iterdir()) == []
    with pytest.raises(BackendError, match="route graph did not install"):
        conv.ledger.check()


def test_a_missing_jar_fails_by_name_before_anything_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv)
    assert "graphhopper-web-*.jar" in conv.ledger.failed["graphhopper-graph"]
    assert calls(log) == []


def test_a_region_that_did_not_install_skips_the_build_without_double_reporting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_jar(tmp_path)
    _install_region(tmp_path, OCEANIA)
    regions = MapLedger()
    regions.fail(LEMURIA.slug, "atlantis/lemuria: md5 did not match")
    conv = _converter(tmp_path, [OCEANIA, LEMURIA], regions=regions)
    outcomes = _run(conv)
    assert conv.ledger.failed == {}
    assert all(o.startswith("skipped") for o in outcomes)
    assert calls(log) == []


def test_a_publish_failing_partway_leaves_the_previous_graph_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_jar(tmp_path)
    _install_region(tmp_path, OCEANIA)
    out = _data(tmp_path, "graphhopper-graph")
    out.mkdir(parents=True)
    (out / "properties").write_bytes(b"old")
    (out / RECORD).write_text("old record\n")
    real = Staging.publish
    count = {"n": 0}

    def publish(self: Staging, staged: Path, dest: Path, **kw: Any) -> None:
        count["n"] += 1
        if count["n"] == 2:
            raise BackendError(f"{dest}: no space left on device")
        real(self, staged, dest, **kw)

    monkeypatch.setattr(Staging, "publish", publish)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv)
    assert "no space left on device" in conv.ledger.failed["graphhopper-graph"]
    assert sorted(p.name for p in out.iterdir()) == [RECORD, "properties"]
    assert (out / "properties").read_bytes() == b"old"


def test_the_plan_text_names_the_merge_the_import_the_cost_and_who_runs_it(
    tmp_path: Path,
) -> None:
    _install_jar(tmp_path)
    _install_region(tmp_path, OCEANIA)
    _install_region(tmp_path, LEMURIA)
    m = manifest()
    steps = _converter(tmp_path, [OCEANIA, LEMURIA]).steps(m, _block(m))
    text = "\n".join(s.description for s in steps if isinstance(s, Action | Command))
    for phrase in (
        "osmium merge",
        "import",
        "as the operator",
        "sac_scale",
        "3.7x the downloads together",
        "1.2 GB of memory",
        "one region measured",
        "nothing is downloaded",
    ):
        assert phrase in text, phrase
