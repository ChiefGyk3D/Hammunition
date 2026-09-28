# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The regions and derived backends turn resolved region files into steps.  D-057.

* **Each region says how it is verified**, in the step the plan prints: a
  pinned sha256 or Geofabrik's MD5, never silently the weaker one.
* **A region dropped from station config is removed**, disclosed as its own
  step, on the next install -- its ``.osm.pbf`` and its ``.bin``.
* **Conversion verifies the effect** (D-031): maptool exiting 0 and writing
  nothing is a failure, and its temporary output is not left behind.
* **Idempotent**: a region already converted from the same snapshot is not
  converted again.

No network and no maptool: every test injects a fake fetcher or a fake
``subprocess.run``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import BackendError
from hammunition.backends.derived import DerivedBackend
from hammunition.backends.regions import (
    MIB,
    RegionsBackend,
    disk_shortfall,
    estimated_bytes,
    region_lines,
)
from hammunition.fetch import FetchResult
from hammunition.geofabrik import RegionFile, UrllibProbe
from hammunition.manifest.schema import (
    DerivedDataInstall,
    PackageManifest,
    RegionalDataInstall,
    RemoteArtifact,
)

FIXTURE = Path(__file__).parent / "fixtures" / "navit.xml"

VT = RegionFile(
    "north-america/us/vermont",
    "260101",
    "https://download.geofabrik.de/north-america/us/vermont-260101.osm.pbf",
    10,
    "a" * 64,
    None,
)
NH = RegionFile(
    "north-america/us/new-hampshire",
    "260101",
    "https://download.geofabrik.de/north-america/us/new-hampshire-260101.osm.pbf",
    10,
    None,
    "b" * 32,
)

_LICENCE = {"licence": "ODbL-1.0", "licence_url": "https://www.openstreetmap.org/copyright"}
_DOCS = {
    "what_it_does": "Map data for a test, nothing more.",
    "why_you_want_it": "Because the test suite needs a manifest.",
    "upstream_url": "https://download.geofabrik.de/",
}


def regions_manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "osm-regions",
            "version": "1",
            "summary": "OpenStreetMap regions",
            "categories": ["digital-modes"],
            "install": [
                {"install": {"method": "osm-regions", "provider": "geofabrik", **_LICENCE}}
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": _DOCS,
        }
    )


def navit_manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "osm-navit",
            "version": "1",
            "summary": "Regions converted for Navit",
            "categories": ["digital-modes"],
            "depends": ["osm-regions", "maptool"],
            "install": [
                {
                    "install": {
                        "method": "derived",
                        "converter": "navit-maptool",
                        "source": "osm-regions",
                        **_LICENCE,
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": _DOCS,
        }
    )


@pytest.fixture
def manifest_regions() -> PackageManifest:
    return regions_manifest()


@pytest.fixture
def block_regions(manifest_regions: PackageManifest) -> RegionalDataInstall:
    block = manifest_regions.install[0].install
    assert isinstance(block, RegionalDataInstall)
    return block


@pytest.fixture
def manifest_navit() -> PackageManifest:
    return navit_manifest()


@pytest.fixture
def block_navit(manifest_navit: PackageManifest) -> DerivedDataInstall:
    block = manifest_navit.install[0].install
    assert isinstance(block, DerivedDataInstall)
    return block


def _data(prefix: Path, unit: str) -> Path:
    return prefix / "share" / "hammunition" / "data" / unit


class FakeFetcher:
    """Hands back a cache file of the declared size; records how it was asked."""

    def __init__(self, cache: Path, *, size: int = 10) -> None:
        self.cache = cache
        self.size = size
        self.calls: list[tuple[str, Any]] = []

    def _file(self, name: str) -> Path:
        self.cache.mkdir(parents=True, exist_ok=True)
        path = self.cache / name
        path.write_bytes(b"p" * self.size)
        return path

    def fetch(self, artifact: RemoteArtifact, *, max_bytes: int | None = None) -> FetchResult:
        self.calls.append(("sha256", (artifact.url, artifact.sha256, max_bytes)))
        return FetchResult(self._file("s.pbf"), artifact.sha256, False, self.size)

    def fetch_md5(self, url: str, md5: str, *, expected_size: int) -> FetchResult:
        self.calls.append(("md5", (url, md5, expected_size)))
        return FetchResult(self._file("m.pbf"), "c" * 64, False, self.size)


def _kinds(steps: Sequence[Any], kind: str) -> list[Any]:
    return [s for s in steps if getattr(s, "kind", None) == kind]


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------


def test_each_region_is_fetched_and_says_how_it_is_verified(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    steps: list[Any] = RegionsBackend(fetcher=None, prefix=tmp_path, files=[VT, NH]).steps(  # type: ignore[arg-type]
        manifest_regions, block_regions
    )
    fetches = _kinds(steps, "fetch")
    assert len(fetches) == 2
    assert fetches[0].description.endswith("sha256, pinned by Hammunition")
    assert fetches[1].description.endswith("MD5 from Geofabrik only; not pinned")
    installs = _kinds(steps, "install-data")
    assert [s.detail for s in installs] == [
        str(_data(tmp_path, "osm-regions") / "north-america-us-vermont.osm.pbf"),
        str(_data(tmp_path, "osm-regions") / "north-america-us-new-hampshire.osm.pbf"),
    ]


def test_a_pinned_region_is_fetched_by_sha256_with_a_cap_above_its_size(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    """Review focus 1: the cap is raised to the declared size plus a margin, never removed."""
    fetcher = FakeFetcher(tmp_path / "cache")
    steps: list[Any] = RegionsBackend(fetcher=fetcher, prefix=tmp_path, files=[VT, NH]).steps(  # type: ignore[arg-type]
        manifest_regions, block_regions
    )
    for step in steps:
        step.perform()
    assert fetcher.calls == [
        ("sha256", (VT.url, VT.sha256, VT.size + MIB)),
        ("md5", (NH.url, NH.md5, NH.size)),
    ]
    out = _data(tmp_path, "osm-regions")
    assert (out / "north-america-us-vermont.osm.pbf").read_bytes() == b"p" * 10
    # The snapshot sidecar a later `update` report reads.
    assert (out / "north-america-us-vermont.osm.pbf.source").read_text() == "260101\n"
    assert (out / "north-america-us-new-hampshire.osm.pbf.source").read_text() == "260101\n"


def test_a_download_of_the_wrong_size_is_refused(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    fetcher = FakeFetcher(tmp_path / "cache", size=11)
    steps: list[Any] = RegionsBackend(fetcher=fetcher, prefix=tmp_path, files=[VT]).steps(  # type: ignore[arg-type]
        manifest_regions, block_regions
    )
    with pytest.raises(BackendError, match="10 bytes"):
        steps[0].perform()


def test_a_region_already_installed_at_this_snapshot_is_not_fetched_again(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    out = _data(tmp_path, "osm-regions")
    out.mkdir(parents=True)
    (out / "north-america-us-vermont.osm.pbf").write_bytes(b"p" * 10)
    (out / "north-america-us-vermont.osm.pbf.source").write_text("260101\n")
    steps: list[Any] = RegionsBackend(fetcher=None, prefix=tmp_path, files=[VT, NH]).steps(  # type: ignore[arg-type]
        manifest_regions, block_regions
    )
    assert [s.detail for s in _kinds(steps, "install-data")] == [
        str(out / "north-america-us-new-hampshire.osm.pbf")
    ]


def test_a_region_dropped_from_station_config_is_removed(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    """Review focus 4."""
    old = _data(tmp_path, "osm-regions") / "north-america-us-maine.osm.pbf"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")
    sidecar = old.with_name(old.name + ".source")
    sidecar.write_text("250101\n")
    steps: list[Any] = RegionsBackend(fetcher=None, prefix=tmp_path, files=[VT]).steps(  # type: ignore[arg-type]
        manifest_regions, block_regions
    )
    removals = _kinds(steps, "remove-data")
    assert [s.detail for s in removals] == [str(old)]
    assert removals[0].description == (
        "Remove north-america-us-maine: no longer in your map regions"
    )
    removals[0].perform()
    assert not old.exists()
    assert not sidecar.exists()


# ---------------------------------------------------------------------------
# Derived: maptool
# ---------------------------------------------------------------------------


def _stock(tmp_path: Path) -> Path:
    stock = tmp_path / "navit.xml"
    stock.write_text(FIXTURE.read_text())
    return stock


def test_derived_skips_a_region_already_converted_from_the_same_snapshot(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    out = _data(tmp_path, "osm-navit")
    out.mkdir(parents=True)
    (out / "north-america-us-vermont.bin").write_bytes(b"bin")
    (out / "north-america-us-vermont.bin.source").write_text("260101\n")
    steps: list[Any] = DerivedBackend(
        prefix=tmp_path, files=[VT, NH], stock=_stock(tmp_path)
    ).steps(manifest_navit, block_navit)
    converts = [s for s in steps if "maptool" in s.description]
    assert [s.detail for s in converts] == [str(out / "north-america-us-new-hampshire.bin")]
    # The Navit config is written last, over every region, converted now or before.
    assert steps[-1].detail == str(out / "navit.xml")


def test_a_changed_snapshot_is_converted_again(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    out = _data(tmp_path, "osm-navit")
    out.mkdir(parents=True)
    (out / "north-america-us-vermont.bin").write_bytes(b"bin")
    (out / "north-america-us-vermont.bin.source").write_text("250101\n")
    steps: list[Any] = DerivedBackend(prefix=tmp_path, files=[VT], stock=_stock(tmp_path)).steps(
        manifest_navit, block_navit
    )
    assert [s.detail for s in steps if "maptool" in s.description] == [
        str(out / "north-america-us-vermont.bin")
    ]


def _fake_maptool(
    monkeypatch: pytest.MonkeyPatch, *, write: bytes | None, returncode: int = 0
) -> list[list[str]]:
    seen: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append(list(argv))
        assert kwargs.get("shell", False) is False
        if write is not None:
            Path(argv[-1]).write_bytes(write)
        return subprocess.CompletedProcess(argv, returncode, "", "maptool: boom")

    monkeypatch.setattr("hammunition.backends.derived.subprocess.run", run)
    return seen


def test_conversion_runs_the_fixed_argv_and_records_the_snapshot(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _fake_maptool(monkeypatch, write=b"navit-bin")
    steps: list[Any] = DerivedBackend(prefix=tmp_path, files=[VT], stock=_stock(tmp_path)).steps(
        manifest_navit, block_navit
    )
    for step in steps:
        step.perform()
    out = _data(tmp_path, "osm-navit")
    pbf = _data(tmp_path, "osm-regions") / "north-america-us-vermont.osm.pbf"
    bin_ = out / "north-america-us-vermont.bin"
    (argv,) = seen
    assert argv[:4] == ["maptool", "--protobuf", "-i", str(pbf)]
    assert argv[4] != str(bin_)  # a temporary, replaced into place once verified
    assert len(argv) == 5
    assert bin_.read_bytes() == b"navit-bin"
    assert (out / "north-america-us-vermont.bin.source").read_text() == "260101\n"
    config = (out / "navit.xml").read_text()
    assert f'data="{bin_}"' in config
    assert "espeak-ng" in config
    assert list(out.glob("*.part*")) == []


@pytest.mark.parametrize(("write", "returncode"), [(None, 0), (b"", 0), (b"half", 1)])
def test_maptool_that_writes_nothing_or_fails_is_refused_and_leaves_no_temp(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
    write: bytes | None,
    returncode: int,
) -> None:
    """D-031: the effect is checked, not the exit status."""
    _fake_maptool(monkeypatch, write=write, returncode=returncode)
    steps: list[Any] = DerivedBackend(prefix=tmp_path, files=[VT], stock=_stock(tmp_path)).steps(
        manifest_navit, block_navit
    )
    with pytest.raises(BackendError, match=r"north-america-us-vermont\.osm\.pbf"):
        steps[0].perform()
    out = _data(tmp_path, "osm-navit")
    assert not (out / "north-america-us-vermont.bin").exists()
    assert not (out / "north-america-us-vermont.bin.source").exists()
    assert list(out.glob("*")) == []


def test_a_missing_stock_navit_config_is_refused_with_its_path(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    """Review focus 5: the path, not a traceback."""
    out = _data(tmp_path, "osm-navit")
    out.mkdir(parents=True)
    (out / "north-america-us-vermont.bin").write_bytes(b"bin")
    (out / "north-america-us-vermont.bin.source").write_text("260101\n")
    missing = tmp_path / "etc" / "navit.xml"
    steps: list[Any] = DerivedBackend(prefix=tmp_path, files=[VT], stock=missing).steps(
        manifest_navit, block_navit
    )
    with pytest.raises(BackendError, match=str(missing)):
        steps[-1].perform()


def test_a_dropped_region_loses_its_navit_map(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    out = _data(tmp_path, "osm-navit")
    out.mkdir(parents=True)
    old = out / "north-america-us-maine.bin"
    old.write_bytes(b"bin")
    (out / "north-america-us-maine.bin.source").write_text("250101\n")
    steps: list[Any] = DerivedBackend(prefix=tmp_path, files=[VT], stock=_stock(tmp_path)).steps(
        manifest_navit, block_navit
    )
    removals = _kinds(steps, "remove-data")
    assert [s.detail for s in removals] == [str(old)]
    removals[0].perform()
    assert list(out.glob("north-america-us-maine*")) == []


# ---------------------------------------------------------------------------
# Disclosure and disk space
# ---------------------------------------------------------------------------


def test_the_plan_prints_one_line_per_region() -> None:
    lines = region_lines([VT, NH])
    assert any(
        "north-america/us/vermont" in line
        and "260101" in line
        and "sha256, pinned by Hammunition" in line
        for line in lines
    )
    assert any(
        "north-america/us/new-hampshire" in line and "MD5 from Geofabrik only; not pinned" in line
        for line in lines
    )


def test_disk_space_is_estimated_at_three_times_the_download() -> None:
    assert estimated_bytes([VT, NH]) == 60
    assert disk_shortfall([VT, NH], free=60) is None
    message = disk_shortfall([VT, NH], free=59)
    assert message is not None
    assert "estimate" in message and "60" in message and "59" in message


def test_the_real_probe_constructs_without_touching_the_network() -> None:
    probe = UrllibProbe()
    assert probe.timeout == 30


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------


def test_a_removed_region_is_no_longer_attributed(tmp_path: Path) -> None:
    import json

    from hammunition.state import TransactionLog
    from hammunition.state.uninstall import files_installed_by_hammunition

    vt = "/usr/local/share/hammunition/data/osm-regions/north-america-us-vermont.osm.pbf"
    nh = "/usr/local/share/hammunition/data/osm-regions/north-america-us-new-hampshire.osm.pbf"
    entries = [
        {"event": "action_end", "version": 1, "kind": "install-data", "detail": vt},
        {"event": "action_end", "version": 1, "kind": "install-data", "detail": nh},
        {"event": "action_end", "version": 1, "kind": "remove-data", "detail": nh},
    ]
    path = tmp_path / "transactions.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    assert files_installed_by_hammunition(TransactionLog(path=path)) == {vt}


@pytest.mark.parametrize("unit", ["osm-regions", "osm-navit"])
def test_uninstall_removes_a_map_unit_s_data_directory(tmp_path: Path, unit: str) -> None:
    from hammunition.distro import Target
    from hammunition.state.uninstall import RemovalPaths, plan_removal

    paths = RemovalPaths(
        prefix=tmp_path / "prefix",
        venv_root=tmp_path / "venvs",
        bin_dir=tmp_path / "bin",
        applications_dir=tmp_path / "applications",
    )
    directory = _data(paths.prefix, unit)
    directory.mkdir(parents=True)
    (directory / "north-america-us-vermont.bin").write_bytes(b"x")
    catalog = {"osm-regions": regions_manifest(), "osm-navit": navit_manifest()}
    plan = plan_removal(
        [unit],
        catalog=catalog,
        profiles={},
        target=Target(distro="debian", version="13", arch="x86_64"),
        attributed=frozenset(),
        states={},
        paths=paths,
    )
    assert [(a.kind, a.path) for a in plan.artifacts[unit]] == [("tree", directory)]


# ---------------------------------------------------------------------------
# Execution order
# ---------------------------------------------------------------------------


def _map_plan() -> Any:
    from hammunition.distro import Target
    from hammunition.plan import InstallPlan, PlannedPackage

    regions, navit = regions_manifest(), navit_manifest()
    return InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        # The order `resolve` produces: `after`, alphabetical here, so the
        # converter's unit comes before the unit whose data it converts.
        packages=(
            PlannedPackage(manifest=navit, block=navit.install[0], apt_packages=("maptool",)),
            PlannedPackage(manifest=regions, block=regions.install[0], apt_packages=()),
        ),
    )


def test_a_map_plan_without_its_backends_is_refused_not_skipped() -> None:
    from hammunition.backends import AptBackend, RecordingRunner
    from hammunition.execute import commands_for

    with pytest.raises(BackendError, match="no derived backend"):
        commands_for(_map_plan(), AptBackend(RecordingRunner()))
    derived = DerivedBackend(prefix=Path("/nonexistent"), files=[VT])
    with pytest.raises(BackendError, match="no regions backend"):
        commands_for(_map_plan(), AptBackend(RecordingRunner()), derived=derived)


def test_regions_are_fetched_first_and_converted_after_apt(tmp_path: Path) -> None:
    from hammunition.backends import Action, AptBackend, RecordingRunner
    from hammunition.execute import commands_for

    steps: list[Any] = commands_for(
        _map_plan(),
        AptBackend(RecordingRunner()),
        regions=RegionsBackend(fetcher=None, prefix=tmp_path, files=[VT]),  # type: ignore[arg-type]
        derived=DerivedBackend(prefix=tmp_path, files=[VT], stock=_stock(tmp_path)),
    )
    shape = [
        s.kind if isinstance(s, Action) else ("apt" if "apt-get" in s.argv else "cmd")
        for s in steps
    ]
    assert shape[0] == "fetch"
    apt_at = shape.index("apt")
    assert shape[apt_at + 1 :] == ["install-data", "install-data", "install-data"]
    details = [s.detail for s in steps[apt_at + 1 :]]
    # The region is installed before it is converted, and Navit's config last.
    assert details[0].endswith("osm-regions/north-america-us-vermont.osm.pbf")
    assert details[1].endswith("osm-navit/north-america-us-vermont.bin")
    assert details[2].endswith("osm-navit/navit.xml")
