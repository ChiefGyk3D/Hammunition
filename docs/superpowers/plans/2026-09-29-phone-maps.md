# Phone maps from the laptop (D-067) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two derived converters (`mapsforge-map`, `mapsforge-poi`) that build Mapsforge phone files per region as the operator, a `phone-maps` profile, and `hammunition maps phone`, which stages the phone files with a `SHA256SUMS` and prints the transfer routes without transferring anything.

**Architecture:** One backend module, `backends/mapsforge.py`, holds both converters (they differ in classpath, argv, magic and output suffix) and a phone ledger, on D-061's `Staging`; `phone_plan.py` builds them for a run and counts their disk; `phone.py` is the `maps phone` command's pure logic; `interface/phone.py` its JSON document. The one pinned jar travels on the derived block as a new optional `tool` field.

**Tech Stack:** Python 3.11+, pydantic schema, pytest with fake programs on `PATH` (`tests/fake_tools.py`), mypy --strict, ruff.

**Spec:** `docs/superpowers/specs/2026-09-29-phone-maps-design.md`

## Global Constraints

- Pin: `https://repo1.maven.org/maven2/org/mapsforge/mapsforge-poi-writer/0.25.0/mapsforge-poi-writer-0.25.0-jar-with-dependencies.jar`, sha256 `85dd23488511f51a710139dffc8c622d184ea93e817c4ec27dde1c222b7432a7`, size 18827962, signature `.asc` beside it (key ID `B51D6498DA0031B6`, not verified).
- Main class `org.openstreetmap.osmosis.core.Osmosis`; heap `-Xmx2g`; map argv tail `-q --rbf file=<pbf> --mapfile-writer file=<out> type=hd`; poi argv tail `-q --rbf file=<pbf> --poi-writer file=<out>`.
- Map classpath: `/usr/share/osmosis/*.jar` then `/usr/share/java/<j>.jar` for commons-codec commons-compress commons-csv commons-dbcp commons-io commons-logging commons-pool guava jpf osmpbf protobuf spring3-beans spring3-core spring3-jdbc spring3-transaction mapsforge-core mapsforge-map mapsforge-map-reader mapsforge-map-writer mapsforge-poi jts-core kxml2 trove-3 sqlite-jdbc (the spike's `mfw.sh`, which reported none missing).
- Poi classpath: `/usr/share/osmosis/*.jar`, then commons-codec commons-compress commons-io commons-logging guava jpf osmpbf protobuf, then the pinned jar (the spike's `poiw.sh`).
- Factors, "measured on one region": map 0.78x output, 15x scratch; poi 0.21x output, 0.5x scratch.
- Tests use `north-america/us/vermont` and `north-america/us/delaware` only; no network; no real install.
- Every converter child runs through `Staging`; root never reads the operator's files.
- `maps phone` refuses root, transfers nothing, binds nothing.

## Review Focus

- A region already current at the same snapshot and converter: no step at all, and no tool fetch when the tool is current (Task 2 test).
- A classpath jar missing after apt: the region fails naming the jar; the others continue (Task 2 test).
- `java` exits 0 and writes a file that is not the format (a stack trace to stdout redirected, a truncated file): refused by magic (Task 2 test).
- `maps phone` run twice: the second copies nothing and the `SHA256SUMS` is unchanged; a region dropped removes only our file (Task 5 tests).
- The phone directory is a symbolic link, or not enough room: refused by name, nothing copied (Task 5 tests).

---

### Task 1: Schema — two converters and the `tool` field

**Files:**
- Modify: `src/hammunition/manifest/schema.py` (converter Literal, `CONVERTER_SOURCE_METHOD`, new `ConverterTool`, `DerivedDataInstall.tool` + validator)
- Test: `tests/test_mapsforge_schema.py`

**Interfaces:**
- Produces: `ConverterTool(artifact: RemoteArtifact, size: int, licence: str, licence_url: str)`, `ConverterTool.file_name -> str`; `DerivedDataInstall.tool: ConverterTool | None`; `CONVERTERS_WITH_TOOL = frozenset({"mapsforge-poi"})`.

- [ ] **Step 1: failing tests**

```python
def _block(**extra):
    return {"method": "derived", "converter": "mapsforge-poi", "source": "osm-regions",
            "licence": "ODbL-1.0", "licence_url": "https://www.openstreetmap.org/copyright", **extra}

def test_mapsforge_poi_requires_its_tool():
    with pytest.raises(ValidationError, match="tool"):
        DerivedDataInstall.model_validate(_block())

def test_a_tool_on_another_converter_is_refused():
    with pytest.raises(ValidationError, match="tool"):
        DerivedDataInstall.model_validate({**_block(tool=TOOL), "converter": "mkgmap"})

def test_the_tool_names_a_bare_file():
    block = DerivedDataInstall.model_validate(_block(tool=TOOL))
    assert block.tool.file_name == "mapsforge-poi-writer-0.25.0-jar-with-dependencies.jar"
```

- [ ] **Step 2:** `pytest tests/test_mapsforge_schema.py` fails (unknown converter).
- [ ] **Step 3: implement**

```python
class ConverterTool(Strict):
    artifact: RemoteArtifact
    size: int = Field(gt=0)
    licence: str = Field(min_length=2)
    licence_url: str

    @property
    def file_name(self) -> str:
        return self.artifact.url.rstrip("/").rsplit("/", 1)[-1]

    @model_validator(mode="after")
    def _check(self) -> ConverterTool:
        if not self.licence_url.startswith("https://"): raise ManifestError(...)
        if not self.artifact.url.startswith("https://"): raise ManifestError(...)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", self.file_name): raise ManifestError(...)
        return self
```

and in `DerivedDataInstall._check`: `tool` present iff `converter in CONVERTERS_WITH_TOOL`.
- [ ] **Step 4:** tests pass; `mypy --strict` clean.
- [ ] **Step 5:** commit `schema: mapsforge-map and mapsforge-poi converters, and a pinned converter tool (D-067)`.

### Task 2: The converters

**Files:**
- Create: `src/hammunition/backends/mapsforge.py`
- Test: `tests/test_mapsforge.py`

**Interfaces:**
- Consumes: `Staging` (`prepare`, `clear`, `run`, `digest`, `publish`, `workdir`, `who`), `MapLedger`, `removal_steps`, `installed_snapshot`, `installed_converter`, `data_root`, `prefix_writer`, `Fetcher.fetch(RemoteArtifact) -> FetchResult`, `signature_gap`.
- Produces: `PhoneLedger` (`fail`, `check`, `step`), `MapsforgeConverter(kind, prefix, files, staging, keep, regions, ledger, runner, euid, privileged, fetcher, osmosis_dir, java_dir)` with `pending(manifest, block) -> list[RegionFile]`, `tool_path(manifest, block) -> Path | None`, `tool_current(manifest, block) -> bool`, `steps(manifest, block)`; constants `MAP_FACTOR`, `MAP_SCRATCH_FACTOR`, `POI_FACTOR`, `POI_SCRATCH_FACTOR`, `PHONE_NOTE`; `classpath(kind, osmosis_dir, java_dir, tool) -> tuple[list[Path], list[str]]`; `java_argv(kind, pbf, out, work, cp) -> list[str]`.

- [ ] **Step 1: failing tests** — fake `java` on PATH that logs argv and writes the magic to the `file=` output named in its argv:

```python
JAVA_MAP = 'o=$(echo "$*" | sed -n "s/.*--mapfile-writer file=\\([^ ]*\\).*/\\1/p"); printf "mapsforge binary OSM body" > "$o"'

def test_map_runs_java_with_the_measured_argv_as_the_operator_in_its_workdir(...):
    ...
    (cwd, argv), = calls(log)
    assert cwd == str(work)
    assert argv.startswith(f"java -Xmx2g -Djava.io.tmpdir={work} -cp ")
    assert argv.endswith(f"org.openstreetmap.osmosis.core.Osmosis -q --rbf file={pbf} "
                         f"--mapfile-writer file={work}/{VERMONT.slug}.map type=hd")
    assert (out / f"{VERMONT.slug}.map.source").read_text() == "260101\nconverter: mapsforge-map 1\n"
```

plus: poi fetches and installs the tool then puts it last on the classpath with `-Dorg.sqlite.tmpdir`; a current region and current tool give no steps; a missing jar fails the region naming it and the other region builds; a wrong magic fails; a dropped region is removed; a region piece 1 failed is skipped; the ledger step fails by name.
- [ ] **Step 2:** run, fails on import.
- [ ] **Step 3:** implement, following `backends/garmin.py` step for step (convert Action, install-data Action with the destination as detail, `removal_steps`), with the tool fetch (`kind="fetch"`) and tool install (`kind="install-data"`, detail the jar's destination) first for `mapsforge-poi` when the installed jar does not hash to the pin.
- [ ] **Step 4:** tests pass, mypy clean.
- [ ] **Step 5:** commit `mapsforge converters: a phone map and POI file per region, run as the operator (D-067)`.

### Task 3: Wiring — run, disk, uninstall, update, plan status

**Files:**
- Create: `src/hammunition/phone_plan.py` (`PhoneRun`, `build_phone_run`)
- Modify: `src/hammunition/cli/main.py` (build it, merge converters, disk, leftover patterns), `src/hammunition/backends/terrain.py` (`combined_shortfall(..., phone=...)`), `src/hammunition/state/uninstall.py` (a derived unit with a tool: remove `share/hammunition/<unit>`), `src/hammunition/update.py` (name the two units when `osm-regions` is behind), `src/hammunition/interface/plan.py` (a mapsforge unit with nothing pending says "already installed")
- Test: `tests/test_phone_plan.py`

- [ ] **Step 1: failing tests**: `PhoneRun.needs` counts 15x a pending region's size in the map staging and 0.78x + 0.21x under the prefix and the tool's size once when it is not current; `combined_shortfall` names the phone note; uninstall plans a tree removal of `share/hammunition/mapsforge-poi`; `update_command` names both units.
- [ ] **Step 2–4:** implement until green.
- [ ] **Step 5:** commit `wire the phone converters into install, disk, uninstall and update (D-067)`.

### Task 4: Catalog — two units and the `phone-maps` profile

**Files:**
- Create: `catalog/packages/mapsforge-map.yaml`, `catalog/packages/mapsforge-poi.yaml`, `catalog/profiles/phone-maps.yaml`
- Modify: whatever `tests/` count profiles; generated `docs/packages/`, `docs/profiles/`
- Test: `tests/test_phone_catalog.py`

- [ ] **Step 1:** test that both units load, depend on `osm-regions`, `osmosis`, `libmapsforge-java`, name their converters, and that `phone-maps` holds exactly the three units at `post-1.0`.
- [ ] **Step 2–4:** write the manifests and profile; run every generator.
- [ ] **Step 5:** commit `catalog: mapsforge-map, mapsforge-poi and the phone-maps profile (D-067)`.

### Task 5: `hammunition maps phone`

**Files:**
- Create: `src/hammunition/phone.py`, `src/hammunition/interface/phone.py`
- Modify: `src/hammunition/cli/main.py` (subcommand, `@envelope.json_capable()`)
- Test: `tests/test_phone.py`

- [ ] **Step 1: failing tests**: staging copies `.map`/`.poi`/`.img` as `<slug>.<ext>` with a `sha256sum -c`-valid `SHA256SUMS`; a second run copies nothing; a removed region's file goes and a foreign file stays; a symlinked directory refuses; too little room refuses before copying; nothing installed says what to install; root refused; `--json` validates and carries the routes; the text prints `--bind 10.42.0.1` and never a bare `http.server` without `--bind`.
- [ ] **Step 2–4:** implement until green.
- [ ] **Step 5:** commit `maps phone: stage the phone files with SHA256SUMS and print the ways across (D-067)`.

### Task 6: Documentation and the decision

**Files:** `docs/DECISIONS.md` (append `## D-067` at the end), `CLAUDE.md` (table row), `CHANGELOG.md` (Unreleased), `docs/reference/cli.md`, `docs/guides/offline-navigation.md` (section "Maps for your phone"), regenerated `docs/reference/json-interface.md`, `docs/packages/*`, `docs/profiles/*`.

- [ ] Write, regenerate, `make check` to a log, test `$?`, commit `docs: D-067, phone maps from the laptop`.
