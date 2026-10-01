# Navigation, piece 3a: official topographic maps

**Status:** design approved by the maintainer on 2026-09-29, on the spike
report (official park, forest and topographic data beyond OSM); this
document is the architectural write-up of that approved design, for the
record and for the implementation plan.
**Decision record:** D-068, written with the implementation. It extends
D-061 (QMapShack, terrain, converters as the operator), D-057 (regions are
station data; derived data by a converter enum; MD5 disclosed, never
silent) and D-049 (offline data is a catalog unit).

Every figure below was measured on 2026-09-29 on the development host
(Parrot 7, GDAL 3.10.3) on public example areas only: Delaware, Vermont,
Shenandoah National Park (SHEN). No maintainer region appears anywhere.

## 1. What this piece delivers

| Unit | Kind | What it is |
|---|---|---|
| `usgs-ustopo` | new install method `topo-quads`, provider `usgs-ustopo` | USGS US Topo 7.5-minute quads, GeoTIFF, public domain, for the quads the station's regions touch |
| `ustopo-qmapshack` | `derived`, converter `ustopo-mosaic` | each quad warped to EPSG:3857 with its collar cropped, and one `ustopo.vrt` over them that QMapShack lists as a map |
| `usfs-fstopo` | next plan (section 8) | Forest Service FSTopo quads |
| `dem-3dep` | next plan (section 8) | USGS 3DEP 1/3" bare-earth elevation, opt-in beside Copernicus |

US Topo is the official trail map: the quads carry named NPS and USFS
trails, campgrounds, visitor centres and 40 ft contours, drawn by the
publisher. It lays over the Garmin maps in QMapShack; nothing interprets a
schema, and the tools are `gdal-bin`, already carried for `dem-qmapshack`.

## 2. The carried index: which quads a region needs, offline

USGS publishes `StagedProducts/Maps/Metadata/ustopo_current.zip` (10.5 MB,
rebuilt daily): `ustopo_current.csv`, 65,240 rows, one per current quad,
with `westbc,eastbc,northbc,southbc`, `primary_state` and the dated
`original_product` file name. The TNM Access API lists only the Geospatial
PDFs; the GeoTIFFs live beside them in the `prd-tnm` bucket at
`StagedProducts/Maps/USTopo/GeoTIFF/<ST>/<ST>_<Name>_<date>_TM_geo.tif`.

`scripts/gen_ustopo_index.py --fetch` reads the CSV and a listing of the
bucket's GeoTIFF prefix (273 `ListObjectsV2` pages, 272,910 objects: every
edition since 2009) and writes `catalog/data/ustopo-quads.txt`, one line
per quad:

```
<south> <west> <north> <east> <size> <etag> <ST>/<stem>_<date>
```

Measured on the 2026-09-29 index: **64,423** of the 65,240 current quads
have a GeoTIFF of the current edition. **817** do not yet: their current
edition (2026) exists only as a PDF. For those the generator carries the
newest GeoTIFF edition the bucket holds, and the file header counts them.
A quad with no GeoTIFF at all is left out and counted. The bbox is the
CSV's own: 6,638 rows (Alaska, and oversized and off-grid quads) are not on
the 1/8-degree grid, so it is carried as decimals, never as a cell number.

`--check --offline` checks the shape (generated mark, header counts, rows
sorted and parsed). `--check` also lists the bucket and fails, naming each,
when a carried key is gone or its ETag or size has changed, because that
breaks an install. A newer edition appearing does not fail it: it is
counted in the output, and `--fetch` picks it up. The weekly pin-review job
runs `--check`; the test suite runs `--check --offline`.

## 3. Selection: the squares the outline touches, at an eighth of a degree

A region's quads are those whose bbox overlaps a 1/8-degree cell its
Geofabrik outline (`<region>.poly`, D-061) touches, edge or interior. That
is `copernicus.squares_touching` at eight cells a degree, generalised with a
`per_degree` argument; Copernicus keeps calling it at one. The answer is
recorded in `<data>/usgs-ustopo/<slug>.quads` when the quads install, so a
later plan needs no network; until then every plan asks for the outline,
which D-061 already does and the plan already says. One outline fetch
serves both: the plan's region probe is wrapped in a memo for the run.

A region outside the United States touches no quad. Its plan line says
"no US Topo quad covers <region> (US Topo covers the United States and its
territories)", nothing is fetched, and the transaction is not failed.

## 4. Verification: the publisher's ETag, carried and re-asked

The index carries each object's size and S3 ETag from the listing. At plan
time every quad about to be fetched is asked for with a `HEAD` (the
reachability rule of D-061): it must answer 200 with the same size and
ETag, else the plan refuses naming the quad and
`scripts/gen_ustopo_index.py --fetch`. The download is checked against
the ETag:

- a single-part upload's ETag is its MD5 (measured by the spike on one
  quad);
- a multipart ETag, `<md5>-<parts>`, is the MD5 of the parts' MD5s. The
  part size is not published; it is found by trying every whole-MiB part
  size from 5 MiB up that splits the size into exactly that many parts
  (the spike measured 8 MiB on a US Topo PDF and 5 MiB on a 3DEP tile).
  No candidate reproducing the ETag is a verification failure, named.

In the carried index, 13,209 of the 64,423 current GeoTIFFs are multipart
(two parts for 10,000-odd of them). The plan says, quad by quad, **"MD5
from the publisher's object metadata; not pinned by Hammunition"** — the
Copernicus wording, since the ETag is the publisher's and no sha256 was
measured by Hammunition. Editions are years old (Vermont 2024, Delaware
2023), so sha256 pins could be grown later exactly as
`gen_copernicus_pins.py` does; this piece does not.

## 5. The converter: `ustopo-mosaic`

Each GeoTIFF is the full 300 dpi page, collar included, in its own
Transverse Mercator (central meridian at the quad centre, NAD83), so
`gdalbuildvrt` cannot mosaic them as they come, and stacked uncropped each
collar hides its neighbour. Per quad, as the operator, in
`~/.cache/hammunition/build/ustopo-qmapshack/ustopo.work/` under one lock:

```
gdalwarp -q -overwrite -t_srs EPSG:3857 -te_srs EPSG:4269 -te <w> <s> <e> <n> \
  -r bilinear -co COMPRESS=JPEG -co PHOTOMETRIC=YCBCR -co TILED=YES <quad.tif> <out.tif>
gdaladdo -q -r average --config COMPRESS_OVERVIEW JPEG \
  --config PHOTOMETRIC_OVERVIEW YCBCR <out.tif> 2 4 8 16
```

The output is published as `<data>/ustopo-qmapshack/quads/<stem>_<date>.tif`
with a `.source` sidecar (`ustopo-mosaic 1`). Then one
`gdalbuildvrt -q ustopo.vrt <every warped quad>`, published as
`<data>/ustopo-qmapshack/ustopo.vrt`, rebuilt when the set changes, and
recorded in `quads.source`. Effects are checked, not exit statuses (D-031):
the output must exist and be non-empty and hash to what is published.
Failures go into D-061's terrain ledger, which fails the run by name at its
end; one quad failing does not stop the others.

`hammunition maps qmapshack` adds `<data>/ustopo-qmapshack` to `[Canvas]
mapPath`. QMapShack lists `*.vrt` there; the warped quads are one level
down, where it does not look.

## 6. The plan, disk and privacy

The Terrain block gains a *US Topo* part: quads per region and their total
size; each quad to fetch with its size and verification; how many are
installed already; the licence (public domain, USGS); and what the
converter builds, with its estimate "measured on one quad". Quad names
encode places, so they are printed in the plan only, never in `update`,
`doctor` or a doc. The disk check counts the downloads twice (cache and
prefix) and the warped output with its scratch.

## 7. Not carried, and why

| Source | Why not |
|---|---|
| NPS, USFS and state trail lines as a second vector layer | OSM already carries 97.5 % of SHEN's official mileage within 25 m (96 % of a GW&J sample); a duplicate layer draws every trail twice, and US Topo already shows the official names |
| 1 m lidar | 26.9 GB for one SHEN project |
| GeoPDF | 6x the GeoTIFF, and rasterised anyway |
| Historical Topo (HTMC) | historical interest; 9.4 GB for Vermont alone |
| Park PDF maps | not georeferenced: no coordinate system, no neatline |
| BLM and USFWS layers | REST queries only: no fixed bytes, no checksum |
| PAD-US | boundaries later; ScienceBase publishes a null checksum |
| NPS points of interest and boundaries as GPX | deferred to a later piece, pending a checksum (the Data Store boundary FGDB could be sha256-pinned) |

Outside the US, OSM stays the trail layer. OS OpenData publishes an MD5 per
file, which is the pattern a UK source would follow; CanVec has none.

## 8. The next plan: FSTopo and 3DEP

Recorded here because this branch ships sections 1 to 7 only.

- **`usfs-fstopo`.** A second `topo-quads` provider. Index from
  `FSTopo_Index_GTAC` (18,188 quads), fetched by
  `downloadMap.php?mapID=<secoord>&mapType=tif&seriesType=FSTopo` (302 to
  the file). **No checksum is published** (Apache's ETag), so each quad is
  sha256-pinned by Hammunition where the maintainer has measured one and
  otherwise disclosed as unverified in the plan, by name, never silently.
  The generator starts with no pins and can grow them later. FSTopo is
  collarless in EPSG:4269, so the converter is a plain `gdalbuildvrt`
  (mixed palettes may need `-expand rgb`, unmeasured on a second quad).
- **`dem-3dep`.** A second `dem-tiles` provider, opt-in through a station
  key `--dem-source copernicus|3dep` (default `copernicus`). Bare earth:
  Copernicus reads 11.8 m above it on average in SHEN forest, the canopy.
  488 MB a tile against 46 MB. Three changes to `gdal-dem`: tile names by
  the north-west corner (`USGS_13_n39w079`), its own tile list, and
  `PIXELS` at least 10,812 so the 1/3" tile is not thrown away. Verified by
  the full-object CRC64NVME or the multipart ETag, disclosed as the
  publisher's check.

## 9. Measured, and not

Measured: the index (2026-09-29), the join against the bucket listing, the
multipart share; one Delaware quad end to end (download, ETag check, warp,
overviews) in the build, recorded in D-068. Not measured: **QMapShack
drawing the mosaic.** The spike's one run opened the VRT and listed it in
the Maps dock, and the canvas stayed blank at the configured focus; why is
unknown. The bench owes it, in a VM, never on the maintainer's desktop (a
scratch `HOME` does not isolate QMapShack's single-instance socket).
