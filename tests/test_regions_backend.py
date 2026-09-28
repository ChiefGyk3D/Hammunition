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

* **One bad region does not sink the others** (spec §8): its failure is
  recorded, the rest install and convert, Navit gets the maps that exist,
  and the transaction still ends non-zero naming it.
* **Downloaded data is not handled as root** where it need not be: maptool
  runs as the operator into a staging directory, and the copy into the
  prefix is re-verified without following a symlink.

No network and no maptool: every test injects a fake fetcher or a fake
``subprocess.run``.
"""

from __future__ import annotations

import hashlib
import os
import pwd
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import BackendError
from hammunition.backends.derived import DerivedBackend
from hammunition.backends.regions import (
    MIB,
    MapLedger,
    RegionsBackend,
    disk_needs,
    disk_shortfall,
    installed_slugs,
)
from hammunition.fetch import Fetcher, FetchResult, VerificationError
from hammunition.geofabrik import RegionFile, UrllibProbe
from hammunition.manifest.schema import (
    DerivedDataInstall,
    PackageManifest,
    RegionalDataInstall,
    RemoteArtifact,
)
from test_osm_pbf import pbf

FIXTURE = Path(__file__).parent / "fixtures" / "navit.xml"
BODY = b"p" * 10
#: Synthetic boxes, nowhere in particular: (left, right, top, bottom).
VT_BOX = (-73.0, -71.0, 45.0, 43.0)
NH_BOX = (-72.0, -70.0, 46.0, 42.0)
BOXES = {"north-america-us-vermont": VT_BOX, "north-america-us-new-hampshire": NH_BOX}

VT = RegionFile(
    "north-america/us/vermont",
    "260101",
    "https://download.geofabrik.de/north-america/us/vermont-260101.osm.pbf",
    10,
    hashlib.sha256(BODY).hexdigest(),
    None,
)
NH = RegionFile(
    "north-america/us/new-hampshire",
    "260101",
    "https://download.geofabrik.de/north-america/us/new-hampshire-260101.osm.pbf",
    10,
    None,
    hashlib.md5(BODY, usedforsecurity=False).hexdigest(),
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


class FakeFetcher(Fetcher):
    """The real cache layout, no network: each fetch writes *BODY* under the
    name the real fetcher would use. A URL in *bad* fails verification."""

    def __init__(self, cache: Path, *, size: int = 10, bad: Sequence[str] = ()) -> None:
        super().__init__(cache)
        self.size = size
        self.bad = set(bad)
        self.calls: list[tuple[str, Any]] = []

    def _file(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(BODY[:1] * self.size)
        return path

    def fetch(self, artifact: RemoteArtifact, *, max_bytes: int | None = None) -> FetchResult:
        self.calls.append(("sha256", (artifact.url, artifact.sha256, max_bytes)))
        if artifact.url in self.bad:
            raise VerificationError(f"{artifact.url} does not match the digest")
        path = self._file(self.path_for(artifact))
        return FetchResult(path, artifact.sha256, False, self.size)

    def fetch_md5(self, url: str, md5: str, *, expected_size: int) -> FetchResult:
        self.calls.append(("md5", (url, md5, expected_size)))
        if url in self.bad:
            raise VerificationError(f"{url} does not match the md5 its publisher lists")
        path = self._file(self.md5_path_for(url, md5))
        return FetchResult(path, "c" * 64, False, self.size)


def _acts(steps: Sequence[Any]) -> list[Any]:
    return list(steps)


def _kinds(steps: Sequence[Any], kind: str) -> list[Any]:
    return [s for s in steps if getattr(s, "kind", None) == kind]


def _regions(tmp_path: Path, files: Sequence[RegionFile], **kw: Any) -> RegionsBackend:
    kw.setdefault("fetcher", FakeFetcher(tmp_path / "cache"))
    return RegionsBackend(prefix=tmp_path, files=files, **kw)


def _derived(tmp_path: Path, files: Sequence[RegionFile], **kw: Any) -> DerivedBackend:
    kw.setdefault("stock", _stock(tmp_path))
    return DerivedBackend(prefix=tmp_path, files=files, staging=tmp_path / "staging", **kw)


def _install_region(tmp_path: Path, region: RegionFile, body: bytes | None = None) -> None:
    """An installed region whose ``.osm.pbf`` is a synthetic header (the centre
    Navit opens on is read from it), or *body*."""
    out = _data(tmp_path, "osm-regions")
    out.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = pbf(BOXES.get(region.slug, VT_BOX))
    (out / f"{region.slug}.osm.pbf").write_bytes(body)
    (out / f"{region.slug}.osm.pbf.source").write_text(f"{region.snapshot}\n")


# ---------------------------------------------------------------------------
# installed_slugs -- what `update` reads back, offline
# ---------------------------------------------------------------------------


def test_installed_slugs_reads_the_source_sidecar(tmp_path: Path) -> None:
    _install_region(tmp_path, VT)
    _install_region(tmp_path, NH)
    assert installed_slugs(_data(tmp_path, "osm-regions")) == {
        "north-america-us-vermont": "260101",
        "north-america-us-new-hampshire": "260101",
    }


def test_installed_slugs_skips_a_pbf_with_no_sidecar(tmp_path: Path) -> None:
    out = _data(tmp_path, "osm-regions")
    out.mkdir(parents=True)
    (out / f"{VT.slug}.osm.pbf").write_bytes(BODY)
    assert installed_slugs(out) == {}


def test_installed_slugs_of_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert installed_slugs(_data(tmp_path, "osm-regions")) == {}


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------


def test_each_region_is_fetched_and_says_how_it_is_verified(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    steps: list[Any] = _regions(tmp_path, [VT, NH]).steps(manifest_regions, block_regions)
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
    backend = _regions(tmp_path, [VT, NH], fetcher=fetcher)
    for step in _acts(backend.steps(manifest_regions, block_regions)):
        assert isinstance(step.perform(), str)
    assert backend.ledger.failed == {}
    assert fetcher.calls == [
        ("sha256", (VT.url, VT.sha256, VT.size + MIB)),
        ("md5", (NH.url, NH.md5, NH.size)),
    ]
    out = _data(tmp_path, "osm-regions")
    assert (out / "north-america-us-vermont.osm.pbf").read_bytes() == BODY
    # The snapshot sidecar a later `update` report reads.
    assert (out / "north-america-us-vermont.osm.pbf.source").read_text() == "260101\n"
    assert (out / "north-america-us-new-hampshire.osm.pbf.source").read_text() == "260101\n"


def test_a_download_of_the_wrong_size_fails_that_region_only(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    backend = _regions(tmp_path, [VT], fetcher=FakeFetcher(tmp_path / "cache", size=11))
    steps: list[Any] = backend.steps(manifest_regions, block_regions)
    assert "FAILED" in steps[0].perform()
    assert "skipped" in steps[1].perform()
    assert "10 bytes" in backend.ledger.failed[VT.slug]
    assert not (_data(tmp_path, "osm-regions") / f"{VT.slug}.osm.pbf").exists()
    with pytest.raises(BackendError, match="north-america/us/vermont"):
        backend.ledger.check()


def test_one_bad_region_does_not_stop_the_others(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    """Fix round 1, item 1 (spec §8): a mismatch installs nothing for that region only."""
    backend = _regions(tmp_path, [NH, VT], fetcher=FakeFetcher(tmp_path / "cache", bad=[NH.url]))
    for step in _acts(backend.steps(manifest_regions, block_regions)):
        step.perform()
    out = _data(tmp_path, "osm-regions")
    assert (out / f"{VT.slug}.osm.pbf").read_bytes() == BODY
    assert not (out / f"{NH.slug}.osm.pbf").exists()
    with pytest.raises(BackendError) as excinfo:
        backend.ledger.check()
    assert "north-america/us/new-hampshire" in str(excinfo.value)
    assert "north-america/us/vermont" not in str(excinfo.value)


def test_a_cache_file_swapped_for_a_symlink_is_not_installed(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    """Fix round 1, item 7: re-verified without following a link on the way in."""
    fetcher = FakeFetcher(tmp_path / "cache")
    backend = _regions(tmp_path, [VT], fetcher=fetcher)
    steps: list[Any] = backend.steps(manifest_regions, block_regions)
    steps[0].perform()  # the fetch, verified
    cached = fetcher.path_for(RemoteArtifact(url=VT.url, sha256=VT.sha256 or ""))
    secret = tmp_path / "secret"
    secret.write_bytes(BODY)  # same bytes: only the link gives it away
    cached.unlink()
    cached.symlink_to(secret)
    assert "FAILED" in steps[1].perform()
    assert "symlink" in backend.ledger.failed[VT.slug]
    assert not (_data(tmp_path, "osm-regions") / f"{VT.slug}.osm.pbf").exists()


def test_a_region_already_installed_at_this_snapshot_is_not_fetched_again(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    _install_region(tmp_path, VT, BODY)  # current means its size too
    steps: list[Any] = _regions(tmp_path, [VT, NH]).steps(manifest_regions, block_regions)
    out = _data(tmp_path, "osm-regions")
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
    steps: list[Any] = _regions(tmp_path, [VT]).steps(manifest_regions, block_regions)
    removals = _kinds(steps, "remove-data")
    assert [s.detail for s in removals] == [str(old)]
    assert removals[0].description == (
        "Remove north-america-us-maine: no longer in your map regions"
    )
    removals[0].perform()
    assert not old.exists()
    assert not sidecar.exists()


def test_a_region_kept_because_it_could_not_be_checked_is_not_removed(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    """Fix round 1, item 4: offline, an installed region stays installed."""
    _install_region(tmp_path, NH)
    steps: list[Any] = _regions(tmp_path, [VT], keep=frozenset({NH.slug})).steps(
        manifest_regions, block_regions
    )
    assert _kinds(steps, "remove-data") == []


def test_older_cached_snapshots_of_a_reinstalled_region_are_pruned(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    """Fix round 1, item 2: the cache does not keep a full copy per year."""
    fetcher = FakeFetcher(tmp_path / "cache")
    cache = fetcher.cache_dir
    cache.mkdir(parents=True)
    old_sha = cache / f"{'d' * 64}-vermont-250101.osm.pbf"
    old_md5 = cache / f"md5-{'e' * 32}-vermont-240101.osm.pbf"
    other = cache / f"{'f' * 64}-new-hampshire-250101.osm.pbf"
    unrelated = cache / f"{'0' * 64}-cty.dat"
    for path in (old_sha, old_md5, other, unrelated):
        path.write_bytes(b"old")
    steps: list[Any] = _regions(tmp_path, [VT], fetcher=fetcher).steps(
        manifest_regions, block_regions
    )
    (prune,) = _kinds(steps, "prune-cache")
    assert str(old_sha.name) in prune.detail and str(old_md5.name) in prune.detail
    assert "new-hampshire" not in prune.detail
    for step in steps:
        step.perform()
    assert not old_sha.exists() and not old_md5.exists()
    assert other.exists() and unrelated.exists()
    assert fetcher.path_for(RemoteArtifact(url=VT.url, sha256=VT.sha256 or "")).exists()


def test_a_failed_region_keeps_its_older_cache(
    tmp_path: Path, manifest_regions: PackageManifest, block_regions: RegionalDataInstall
) -> None:
    fetcher = FakeFetcher(tmp_path / "cache", bad=[VT.url])
    fetcher.cache_dir.mkdir(parents=True)
    old = fetcher.cache_dir / f"{'d' * 64}-vermont-250101.osm.pbf"
    old.write_bytes(b"old")
    for step in _acts(
        _regions(tmp_path, [VT], fetcher=fetcher).steps(manifest_regions, block_regions)
    ):
        step.perform()
    assert old.exists()


# ---------------------------------------------------------------------------
# Derived: maptool
# ---------------------------------------------------------------------------


def _stock(tmp_path: Path) -> Path:
    stock = tmp_path / "navit.xml"
    stock.write_text(FIXTURE.read_text())
    return stock


def _converted(tmp_path: Path, region: RegionFile, snapshot: str | None = None) -> None:
    out = _data(tmp_path, "osm-navit")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{region.slug}.bin").write_bytes(b"bin")
    (out / f"{region.slug}.bin.source").write_text(f"{snapshot or region.snapshot}\n")


def test_derived_skips_a_region_already_converted_from_the_same_snapshot(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    _converted(tmp_path, VT)
    out = _data(tmp_path, "osm-navit")
    steps: list[Any] = _derived(tmp_path, [VT, NH]).steps(manifest_navit, block_navit)
    assert [s.detail for s in _kinds(steps, "install-data")][:-1] == [
        str(out / "north-america-us-new-hampshire.bin")
    ]
    assert len(_kinds(steps, "convert")) == 1
    # The Navit config is written last, over every region, converted now or before.
    assert steps[-1].detail == str(out / "navit.xml")


def test_a_changed_snapshot_is_converted_again(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    _converted(tmp_path, VT, "250101")
    steps: list[Any] = _derived(tmp_path, [VT]).steps(manifest_navit, block_navit)
    assert [s.detail for s in _kinds(steps, "install-data")][:-1] == [
        str(_data(tmp_path, "osm-navit") / "north-america-us-vermont.bin")
    ]


def test_each_conversion_states_an_output_size_estimate(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    """Fix round 1, item 8 (spec §5)."""
    (convert,) = _kinds(_derived(tmp_path, [VT]).steps(manifest_navit, block_navit), "convert")
    assert "0 KB" in convert.description
    assert "estimate, measured on three regions" in convert.description


def _fake_maptool(
    monkeypatch: pytest.MonkeyPatch,
    *,
    write: bytes | None,
    returncode: int = 0,
    fail_for: str | None = None,
) -> list[tuple[list[str], dict[str, Any]]]:
    seen: list[tuple[list[str], dict[str, Any]]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append((list(argv), kwargs))
        assert kwargs.get("shell", False) is False
        if fail_for is not None and fail_for in argv[3]:
            return subprocess.CompletedProcess(argv, 1, "", "maptool: boom")
        if write is not None:
            Path(argv[-1]).write_bytes(write)
        return subprocess.CompletedProcess(argv, returncode, "", "maptool: boom")

    monkeypatch.setattr("hammunition.backends.derived.subprocess.run", run)
    return seen


def test_conversion_runs_the_fixed_argv_as_the_operator_and_records_the_snapshot(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _fake_maptool(monkeypatch, write=b"navit-bin")
    _install_region(tmp_path, VT)
    backend = _derived(tmp_path, [VT])
    for step in _acts(backend.steps(manifest_navit, block_navit)):
        step.perform()
    assert backend.ledger.failed == {}
    out = _data(tmp_path, "osm-navit")
    pbf = _data(tmp_path, "osm-regions") / "north-america-us-vermont.osm.pbf"
    bin_ = out / "north-america-us-vermont.bin"
    ((argv, _),) = seen
    assert argv[:4] == ["maptool", "--protobuf", "-i", str(pbf)]
    # Written into the operator's staging directory, never straight into the prefix.
    assert Path(argv[4]).parent == tmp_path / "staging"
    assert len(argv) == 5
    assert bin_.read_bytes() == b"navit-bin"
    assert (out / "north-america-us-vermont.bin.source").read_text() == "260101\n"
    config = (out / "navit.xml").read_text()
    assert f'data="{bin_}"' in config
    assert "espeak-ng" in config
    assert list(out.glob("*.part*")) == []
    assert list((tmp_path / "staging").iterdir()) == []


def test_conversion_is_unprivileged_and_only_the_install_needs_root(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    """Fix round 1, item 6: maptool never runs as root over downloaded data."""
    steps: list[Any] = _derived(tmp_path, [VT], privileged=True).steps(manifest_navit, block_navit)
    (convert,) = _kinds(steps, "convert")
    assert convert.requires_root is False
    assert all(s.requires_root for s in _kinds(steps, "install-data"))
    steps = _derived(tmp_path, [VT], privileged=False).steps(manifest_navit, block_navit)
    assert not any(s.requires_root for s in steps)


#: A fixed non-root operator, whoever runs the suite: as real root in CI the
#: real uid is 0, and an "operator" copied from it would be root, whom the
#: engine rightly never drops to.
OPERATOR = pwd.struct_passwd(("operator", "x", 4242, 4242, "", "/nonexistent", "/bin/sh"))


def _as_root_for_operator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The engine is root (pinned, not read) acting for :data:`OPERATOR`."""
    home = tmp_path / "home" / "operator"
    operator = pwd.struct_passwd((*OPERATOR[:5], str(home), OPERATOR.pw_shell))
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: operator)
    monkeypatch.setattr(pwd, "getpwall", lambda: [operator])


class _AsOperator:
    """``subprocess`` under root, faked: records each call and its drop, then
    runs it for real without the drop (a test cannot setgroups) -- except
    maptool, which writes *write* to its output inside its cwd."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, write: bytes = b"navit-bin") -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.write = write
        real_popen = subprocess.Popen

        def strip(kwargs: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in kwargs.items() if k not in ("user", "group", "extra_groups")}

        def run(argv: list[str], **kwargs: Any) -> Any:
            self.calls.append((list(argv), kwargs))
            if argv[:2] == ["env", "-C"] and argv[3] == "maptool":
                # The chdir is env's, as the operator (fix round 3, item 2).
                Path(argv[2], argv[-1]).write_bytes(self.write)
                return subprocess.CompletedProcess(argv, 0, "", "")
            # Not real_run: it calls subprocess.Popen, which is patched below.
            kept = strip(kwargs)
            text = kept.pop("text", False)
            kept.pop("check", None)
            kept.pop("capture_output", None)
            with real_popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, **kept
            ) as proc:
                out, err = proc.communicate()
            return subprocess.CompletedProcess(argv, proc.returncode, out, err)

        def popen(argv: list[str], **kwargs: Any) -> Any:
            self.calls.append((list(argv), kwargs))
            return real_popen(argv, **strip(kwargs))

        monkeypatch.setattr("hammunition.backends.derived.subprocess.run", run)
        monkeypatch.setattr("hammunition.backends.derived.subprocess.Popen", popen)

    def dropped(self) -> bool:
        return all(
            k.get("user") == OPERATOR.pw_uid
            and k.get("group") == OPERATOR.pw_gid
            and k.get("extra_groups") == []
            for _, k in self.calls
        )


def _no_root_filesystem_writes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Root-side chown/mkdir/unlink on the staging side would show up here."""
    touched: list[str] = []
    monkeypatch.setattr(
        "hammunition.backends.derived.os.chown", lambda *a, **k: touched.append(f"chown {a}")
    )
    return touched


def test_under_root_every_staging_step_runs_as_the_operator(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix round 2, item 1: root does no filesystem work on the operator's staging path."""
    _as_root_for_operator(monkeypatch, tmp_path)
    fake = _AsOperator(monkeypatch)
    touched = _no_root_filesystem_writes(monkeypatch)
    _install_region(tmp_path, VT)
    backend = _derived(tmp_path, [VT], euid=0, owner=OPERATOR.pw_name, privileged=False)
    for step in _acts(backend.steps(manifest_navit, block_navit)):
        step.perform()
    assert backend.ledger.failed == {}
    assert touched == []
    assert fake.calls and fake.dropped()
    maptool = [(argv, k) for argv, k in fake.calls if "maptool" in argv]
    assert len(maptool) == 1
    ((argv, kwargs),) = maptool
    # Fix round 3, item 2: the chdir happens as the operator, inside env, and
    # no cwd= makes the child chdir as root before it drops.
    assert argv[:4] == ["env", "-C", str(tmp_path / "staging"), "maptool"]
    assert "cwd" not in kwargs
    assert all("cwd" not in k for _, k in fake.calls)
    out = _data(tmp_path, "osm-navit")
    assert (out / f"{VT.slug}.bin").read_bytes() == b"navit-bin"
    assert list((tmp_path / "staging").iterdir()) == []


def test_under_root_a_symlinked_staging_directory_fails_the_region_and_is_not_used(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix round 2, item 1: `osm-navit -> /etc/sudoers.d` must not become a root chown."""
    _as_root_for_operator(monkeypatch, tmp_path)
    fake = _AsOperator(monkeypatch)
    touched = _no_root_filesystem_writes(monkeypatch)
    target = tmp_path / "sudoers.d"
    target.mkdir()
    (tmp_path / "staging").symlink_to(target)
    _install_region(tmp_path, VT)
    backend = _derived(tmp_path, [VT], euid=0, owner=OPERATOR.pw_name, privileged=False)
    (convert,) = _kinds(backend.steps(manifest_navit, block_navit), "convert")
    assert "FAILED" in convert.perform()
    assert "north-america/us/vermont" in backend.ledger.failed[VT.slug]
    assert "symlink" in backend.ledger.failed[VT.slug]
    assert touched == []
    assert list(target.iterdir()) == []
    assert not any("maptool" in argv for argv, _ in fake.calls)


def test_maptool_runs_in_the_staging_directory(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix round 2, item 2: its *.tmp scratch goes to staging, never the caller's cwd."""
    seen = _fake_maptool(monkeypatch, write=b"navit-bin")
    _install_region(tmp_path, VT)
    (convert,) = _kinds(_derived(tmp_path, [VT]).steps(manifest_navit, block_navit), "convert")
    convert.perform()
    ((_, kwargs),) = seen
    assert kwargs["cwd"] == tmp_path / "staging"


@pytest.mark.parametrize(("write", "returncode"), [(None, 0), (b"", 0), (b"half", 1)])
def test_maptool_that_writes_nothing_or_fails_fails_that_region_and_leaves_no_temp(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
    write: bytes | None,
    returncode: int,
) -> None:
    """D-031: the effect is checked, not the exit status."""
    _fake_maptool(monkeypatch, write=write, returncode=returncode)
    _install_region(tmp_path, VT)
    backend = _derived(tmp_path, [VT])
    steps: list[Any] = backend.steps(manifest_navit, block_navit)
    assert "FAILED" in steps[0].perform()
    assert "skipped" in steps[1].perform()
    assert "north-america-us-vermont.osm.pbf" in backend.ledger.failed[VT.slug]
    out = _data(tmp_path, "osm-navit")
    assert not (out / "north-america-us-vermont.bin").exists()
    assert not (out / "north-america-us-vermont.bin.source").exists()
    assert list((tmp_path / "staging").glob("*")) == []


#: What maptool left in the staging directory after a successful conversion
#: on the bench (2026-09-28): its per-country boundary scratch.
SCRATCH = ("country_840_broken_.tmp", "country_US_poly_.tmp")


def _litter(staging: Path, outside: Path) -> dict[str, Path]:
    """Scratch to remove, and look-alikes that must stay."""
    staging.mkdir(parents=True, exist_ok=True)
    for name in SCRATCH:
        (staging / name).write_bytes(b"scratch")
    outside.write_bytes(b"not maptool's")
    keep = {
        # a symlink named like scratch: removing it is harmless, but only a
        # regular file is maptool's, and the target must never be touched
        "link": staging / "country_124_poly_.tmp",
        "dir": staging / "country_484_broken_.tmp",
        "other-region": staging / f"{NH.slug}.bin.part",
        "other-tmp": staging / "coords.tmp",
        "near-miss": staging / "country_840.tmp",
        # fullmatch, not match or search: a scratch name with more around it
        # is not maptool's (fix round 1, M7)
        "suffixed": staging / "country_US_poly_.tmp.keep",
        "prefixed": staging / "old-country_US_poly_.tmp",
    }
    keep["link"].symlink_to(outside)
    keep["dir"].mkdir()
    for name in ("other-region", "other-tmp", "near-miss", "suffixed", "prefixed"):
        keep[name].write_bytes(b"keep")
    return keep


def test_maptool_scratch_is_removed_once_the_map_is_installed(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bench, 2026-09-28: country_*_broken_.tmp and country_*_poly_.tmp stayed behind."""
    _fake_maptool(monkeypatch, write=b"navit-bin")
    _install_region(tmp_path, VT)
    staging = tmp_path / "staging"
    outside = tmp_path / "precious"
    keep = _litter(staging, outside)
    steps: list[Any] = _derived(tmp_path, [VT]).steps(manifest_navit, block_navit)
    convert, install = _kinds(steps, "convert")[0], _kinds(steps, "install-data")[0]
    assert "country_*_broken_.tmp" in install.description
    assert str(staging) in install.description
    convert.perform()
    # Nothing is removed before the map is installed.
    assert all((staging / name).exists() for name in SCRATCH)
    result = install.perform()
    assert "removed 2 maptool scratch file(s)" in result
    assert not any((staging / name).exists() for name in SCRATCH)
    assert all(p.is_symlink() or p.exists() for p in keep.values())
    assert outside.read_bytes() == b"not maptool's"


def test_scratch_is_left_when_the_map_did_not_install(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_maptool(monkeypatch, write=None)
    _install_region(tmp_path, VT)
    staging = tmp_path / "staging"
    _litter(staging, tmp_path / "precious")
    steps: list[Any] = _derived(tmp_path, [VT]).steps(manifest_navit, block_navit)
    for step in _acts(steps)[:2]:
        step.perform()
    assert all((staging / name).exists() for name in SCRATCH)


def test_under_root_scratch_is_removed_through_the_operator_dir_helper(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Root removes by name through a descriptor the helper proved the
    operator's, O_NOFOLLOW from their home; never by path."""
    _as_root_for_operator(monkeypatch, tmp_path)
    _AsOperator(monkeypatch)
    staging = tmp_path / "staging"
    _litter(staging, tmp_path / "precious")
    asked: list[tuple[Path, str | None]] = []

    def helper(path: Path, owner: str | None = None) -> int:
        asked.append((path, owner))
        return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    monkeypatch.setattr("hammunition.backends.derived.open_operator_dir", helper)
    _install_region(tmp_path, VT)
    backend = _derived(tmp_path, [VT], euid=0, owner=OPERATOR.pw_name, privileged=False)
    for step in _acts(backend.steps(manifest_navit, block_navit))[:2]:
        step.perform()
    assert asked == [(staging, OPERATOR.pw_name)]
    assert not any((staging / name).exists() for name in SCRATCH)


def test_a_staging_directory_refused_by_the_helper_is_named_and_not_cleared(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hammunition.paths import OperatorDirError

    _fake_maptool(monkeypatch, write=b"navit-bin")
    _install_region(tmp_path, VT)
    staging = tmp_path / "staging"
    _litter(staging, tmp_path / "precious")

    def refuse(path: Path, owner: str | None = None) -> int:
        raise OperatorDirError(f"{path} is a symlink")

    monkeypatch.setattr("hammunition.backends.derived.open_operator_dir", refuse)
    steps: list[Any] = _derived(tmp_path, [VT]).steps(manifest_navit, block_navit)
    _acts(steps)[0].perform()
    result = _acts(steps)[1].perform()
    assert result.startswith("installed ")
    assert "scratch not cleared" in result and "is a symlink" in result
    assert all((staging / name).exists() for name in SCRATCH)


def test_one_failed_conversion_leaves_navit_the_others(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix round 1, item 1: Navit still gets the regions that did convert."""
    _fake_maptool(monkeypatch, write=b"navit-bin", fail_for=VT.slug)
    _install_region(tmp_path, VT)
    _install_region(tmp_path, NH)
    backend = _derived(tmp_path, [VT, NH])
    for step in _acts(backend.steps(manifest_navit, block_navit)):
        step.perform()
    out = _data(tmp_path, "osm-navit")
    config = (out / "navit.xml").read_text()
    assert f"{NH.slug}.bin" in config and f"{VT.slug}.bin" not in config
    with pytest.raises(BackendError, match="north-america/us/vermont"):
        backend.ledger.check()


def test_a_region_that_did_not_install_is_not_converted(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _fake_maptool(monkeypatch, write=b"navit-bin")
    ledger = MapLedger()
    ledger.fail(VT.slug, "north-america/us/vermont: md5 mismatch")
    (convert,) = _kinds(
        _derived(tmp_path, [VT], ledger=ledger).steps(manifest_navit, block_navit), "convert"
    )
    assert "skipped" in convert.perform()
    assert seen == []


def test_a_missing_stock_navit_config_is_refused_with_its_path(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    """Review focus 5: the path, not a traceback."""
    _converted(tmp_path, VT)
    missing = tmp_path / "etc" / "navit.xml"
    steps: list[Any] = _derived(tmp_path, [VT], stock=missing).steps(manifest_navit, block_navit)
    with pytest.raises(BackendError, match=str(missing)):
        steps[-1].perform()


def test_a_dropped_region_loses_its_navit_map_and_a_kept_one_does_not(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    out = _data(tmp_path, "osm-navit")
    out.mkdir(parents=True)
    old = out / "north-america-us-maine.bin"
    old.write_bytes(b"bin")
    (out / "north-america-us-maine.bin.source").write_text("250101\n")
    _converted(tmp_path, VT)
    _converted(tmp_path, NH)
    steps: list[Any] = _derived(tmp_path, [VT], keep=frozenset({NH.slug})).steps(
        manifest_navit, block_navit
    )
    removals = _kinds(steps, "remove-data")
    assert [s.detail for s in removals] == [str(old)]
    for step in steps:
        step.perform()
    assert list(out.glob("north-america-us-maine*")) == []
    config = (out / "navit.xml").read_text()
    assert f"{VT.slug}.bin" in config and f"{NH.slug}.bin" in config


def _navit_center(config: str) -> str:
    start = config.index("<navit ")
    tag = config[start : config.index(">", start)]
    return tag.split('center="', 1)[1].split('"', 1)[0]


def test_navit_opens_on_the_first_region_s_bbox_midpoint(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    """Bench, 2026-09-28: Navit opened on the stock centre, Munich, and showed nothing."""
    for region in (VT, NH):
        _install_region(tmp_path, region)
        _converted(tmp_path, region)
    steps: list[Any] = _derived(tmp_path, [VT, NH]).steps(manifest_navit, block_navit)
    assert (
        "centred on the first region whose header gives a bounding box, "
        "else the stock centre" in steps[-1].description
    )
    assert "follow" in steps[-1].description
    steps[-1].perform()
    config = (_data(tmp_path, "osm-navit") / "navit.xml").read_text()
    assert _navit_center(config) == "-72.0000 44.0000"
    assert 'follow="1" source="gpsd://' in config


def test_a_first_region_that_did_not_convert_gives_way_to_the_next(
    tmp_path: Path,
    manifest_navit: PackageManifest,
    block_navit: DerivedDataInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_maptool(monkeypatch, write=b"navit-bin", fail_for=VT.slug)
    _install_region(tmp_path, VT)
    _install_region(tmp_path, NH)
    backend = _derived(tmp_path, [VT, NH])
    for step in _acts(backend.steps(manifest_navit, block_navit)):
        step.perform()
    config = (_data(tmp_path, "osm-navit") / "navit.xml").read_text()
    assert _navit_center(config) == "-71.0000 44.0000"


def test_a_region_header_without_a_bbox_keeps_the_stock_centre_and_says_so(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    _install_region(tmp_path, VT, pbf(None))
    _converted(tmp_path, VT)
    steps: list[Any] = _derived(tmp_path, [VT]).steps(manifest_navit, block_navit)
    result = steps[-1].perform()
    assert "stock centre" in result
    config = (_data(tmp_path, "osm-navit") / "navit.xml").read_text()
    assert _navit_center(config) == "11.5666 48.1333"


def test_the_outcome_names_the_region_the_centre_came_from(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    for region in (VT, NH):
        _install_region(tmp_path, region)
        _converted(tmp_path, region)
    steps: list[Any] = _derived(tmp_path, [VT, NH]).steps(manifest_navit, block_navit)
    assert f"opening on -72.0000 44.0000 (from {VT.slug})" in steps[-1].perform()


def test_a_first_region_whose_pbf_is_gone_is_named_not_silently_skipped(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    """Fix round 1, M4: a kept region's .bin with no .osm.pbf beside it."""
    _install_region(tmp_path, NH)
    for region in (VT, NH):
        _converted(tmp_path, region)
    steps: list[Any] = _derived(tmp_path, [VT, NH]).steps(manifest_navit, block_navit)
    result = steps[-1].perform()
    gone = _data(tmp_path, "osm-regions") / f"{VT.slug}.osm.pbf"
    assert f"passed over {gone}: not installed" in result
    assert f"(from {NH.slug})" in result


def test_not_exactly_one_gpsd_vehicle_writes_the_config_and_says_navit_will_not_follow(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    """Fix round 1, I2: soft, like the centre."""
    # Not _stock()'s path: _derived() rewrites that one from the fixture.
    stock = tmp_path / "serial-navit.xml"
    stock.write_text(
        FIXTURE.read_text().replace(
            'enabled="yes" active="1" source="gpsd://', 'enabled="no" active="1" source="gpsd://'
        )
    )
    _install_region(tmp_path, VT)
    _converted(tmp_path, VT)
    steps: list[Any] = _derived(tmp_path, [VT], stock=stock).steps(manifest_navit, block_navit)
    result = steps[-1].perform()
    assert "Navit will not follow the GPS: " in result
    assert "0 enabled" in result
    config = (_data(tmp_path, "osm-navit") / "navit.xml").read_text()
    assert f"{VT.slug}.bin" in config
    assert 'follow="1" source="gpsd://' not in config


def test_one_gpsd_vehicle_says_nothing_about_not_following(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    _install_region(tmp_path, VT)
    _converted(tmp_path, VT)
    steps: list[Any] = _derived(tmp_path, [VT]).steps(manifest_navit, block_navit)
    assert "will not follow" not in steps[-1].perform()


def test_a_malformed_region_header_is_named_and_passed_over_not_fatal(
    tmp_path: Path, manifest_navit: PackageManifest, block_navit: DerivedDataInstall
) -> None:
    """The config still loads every map; failing the step would leave Navit none,
    and would hide the ledger's report of a region that did fail."""
    _install_region(tmp_path, VT, BODY)
    _install_region(tmp_path, NH)
    for region in (VT, NH):
        _converted(tmp_path, region)
    steps: list[Any] = _derived(tmp_path, [VT, NH]).steps(manifest_navit, block_navit)
    result = steps[-1].perform()
    assert f"passed over {_data(tmp_path, 'osm-regions') / f'{VT.slug}.osm.pbf'}" in result
    config = (_data(tmp_path, "osm-navit") / "navit.xml").read_text()
    assert _navit_center(config) == "-71.0000 44.0000"
    assert f"{VT.slug}.bin" in config


# ---------------------------------------------------------------------------
# Disclosure and disk space
# ---------------------------------------------------------------------------


def test_disk_needs_count_the_cache_the_staging_and_the_prefix(tmp_path: Path) -> None:
    """Fix round 1, item 2: the cache holds a copy too. Fix round 2, item 2:
    maptool's scratch (2x the input) and its .bin (0.9x). The .bin factor was
    0.8 from one country-sized region; two US-state-sized regions on the field
    laptop, 2026-09-28, converted at 0.874x and 0.856x, so it was raised."""
    big = RegionFile("x/big", "260101", "https://x/big.osm.pbf", 1000, None, "c" * 32)
    needs = disk_needs([big], [big], cache=tmp_path / "c", staging=tmp_path / "s", prefix=tmp_path)
    assert needs == {tmp_path / "c": 1000, tmp_path / "s": 2900, tmp_path: 1900}


def test_a_region_installed_but_not_converted_still_needs_conversion_space(
    tmp_path: Path,
) -> None:
    """Fix round 2, item 3: an osm-navit-only run is disk-checked too."""
    big = RegionFile("x/big", "260101", "https://x/big.osm.pbf", 1000, None, "c" * 32)
    needs = disk_needs([], [big], cache=tmp_path / "c", staging=tmp_path / "s", prefix=tmp_path)
    assert needs == {tmp_path / "c": 0, tmp_path / "s": 2900, tmp_path: 900}


def test_derived_pending_names_the_regions_it_will_convert(
    tmp_path: Path, manifest_navit: PackageManifest
) -> None:
    _converted(tmp_path, VT)
    assert _derived(tmp_path, [VT, NH]).pending(manifest_navit) == [NH]


def test_disk_needs_on_one_file_system_are_summed_against_one_free_figure(
    tmp_path: Path,
) -> None:
    needs = {tmp_path / "c": 20, tmp_path / "s": 40, tmp_path: 60}
    same = {"device_of": lambda _p: 1}
    assert disk_shortfall(needs, free_at=lambda _p: 120, **same) is None
    message = disk_shortfall(needs, free_at=lambda _p: 119, **same)
    assert message is not None
    assert "estimate, measured on three regions" in message
    assert "120" in message and "119" in message
    # On separate file systems each is compared with its own free space.
    split = {"device_of": lambda p: hash(str(p))}
    assert disk_shortfall(needs, free_at=lambda _p: 60, **split) is None


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
# Execution order and the transaction's outcome
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


def test_a_map_plan_without_its_backends_is_refused_not_skipped(tmp_path: Path) -> None:
    from hammunition.backends import AptBackend, RecordingRunner
    from hammunition.execute import commands_for

    with pytest.raises(BackendError, match="no derived backend"):
        commands_for(_map_plan(), AptBackend(RecordingRunner()))
    derived = _derived(tmp_path, [VT])
    with pytest.raises(BackendError, match="no regions backend"):
        commands_for(_map_plan(), AptBackend(RecordingRunner()), derived=derived)


def test_regions_are_fetched_first_converted_after_apt_and_checked_last(
    tmp_path: Path,
) -> None:
    from hammunition.backends import Action, AptBackend, RecordingRunner
    from hammunition.execute import commands_for

    ledger = MapLedger()
    steps: list[Any] = commands_for(
        _map_plan(),
        AptBackend(RecordingRunner()),
        regions=_regions(tmp_path, [VT], ledger=ledger),
        derived=_derived(tmp_path, [VT], ledger=ledger),
    )
    shape = [
        s.kind if isinstance(s, Action) else ("apt" if "apt-get" in s.argv else "cmd")
        for s in steps
    ]
    assert shape[0] == "fetch"
    apt_at = shape.index("apt")
    assert shape[apt_at + 1 :] == [
        "install-data",
        "convert",
        "install-data",
        "install-data",
        "check-map-regions",
    ]
    details = [s.detail for s in steps[apt_at + 1 :]]
    # The region is installed before it is converted, and Navit's config last.
    assert details[0].endswith("osm-regions/north-america-us-vermont.osm.pbf")
    assert details[2].endswith("osm-navit/north-america-us-vermont.bin")
    assert details[3].endswith("osm-navit/navit.xml")


@pytest.mark.parametrize("failure", ["md5", "maptool"])
def test_a_failed_region_ends_the_transaction_non_zero_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Fix round 1, item 1: the others install and convert; the run is still not a success."""
    from hammunition.backends import AptBackend, RecordingRunner
    from hammunition.execute import commands_for, execute
    from hammunition.state import TransactionLog

    _fake_maptool(
        monkeypatch, write=b"navit-bin", fail_for=NH.slug if failure == "maptool" else None
    )
    bad = [NH.url] if failure == "md5" else []
    ledger = MapLedger()
    plan = _map_plan()
    apt = AptBackend(RecordingRunner())
    steps = commands_for(
        plan,
        apt,
        regions=_regions(
            tmp_path, [VT, NH], ledger=ledger, fetcher=FakeFetcher(tmp_path / "cache", bad=bad)
        ),
        derived=_derived(tmp_path, [VT, NH], ledger=ledger),
    )
    report = execute(
        steps, apt.runner, log=TransactionLog(path=tmp_path / "log.jsonl"), plan=plan, euid=0
    )
    assert not report.ok
    assert "north-america/us/new-hampshire" in report.stderr
    assert "north-america/us/vermont" not in report.stderr
    navit = _data(tmp_path, "osm-navit")
    assert (navit / f"{VT.slug}.bin").read_bytes() == b"navit-bin"
    assert not (navit / f"{NH.slug}.bin").exists()
    assert f"{VT.slug}.bin" in (navit / "navit.xml").read_text()
