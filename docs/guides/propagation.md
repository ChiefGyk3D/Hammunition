<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Propagation and solar conditions

Knowing whether a band is open beats calling into static. Two kinds of tool
answer that: software this catalog installs, and websites that are better
than anything installable. The websites live here as prose — AHRL shipped
them as browser bookmarks and menu launchers, and this project retired those
units (a menu entry that opens a URL is not software, and it rots exactly as
fast), keeping the destinations where documentation belongs instead.

## Installed tools

- **hamclock-next** — the kitchen-sink dashboard: space weather, band
  conditions, DX spots, satellite passes, all on one screen.
- **splat** — RF path modeling over real terrain, for point-to-point questions
  rather than ionospheric ones.
- **signal-server** — coverage maps over the same terrain, every input on
  the command line; see *Terrain for coverage plots* below.
- **WSJT-X's own WSPR mode** — the empirical answer: beacon a few milliwatts
  and see where you are actually heard.

## Terrain for coverage plots

Above about 30 MHz the question is what is in the way, and SPLAT! and
Signal-Server answer it from elevation data. Without that data both still
run: they assume a flat earth at sea level and print a confident answer
that is worthless. So the first job is terrain.

### Where the terrain comes from

`splat-sdf` (in the `antenna` profile) makes SPLAT's terrain files from the
elevation Hammunition already holds for your map regions: the Copernicus
30 m tiles (`dem-copernicus`), or USGS 3DEP when you chose it with
`hammunition station set --dem-source 3dep`. It writes two files per one
degree square, compressed, under
`/usr/local/share/hammunition/data/splat-sdf/`:

| File | For | Resolution |
|---|---|---|
| `36:37:116:117-hd.sdf.bz2` | `splat-hd`, `signalserverHD` | one arc second, about 30 m |
| `36:37:116:117.sdf.bz2` | `splat`, `signalserver` | three arc seconds, about 90 m |

and beside each a link under the name Signal-Server asks for
(`36_37_116_117-hd.sdf.bz2`). The square in the names is south-west corner
36 N 117 W, counted west and positive the way SPLAT! counts longitude.

With no map regions set, `splat-sdf` is deferred by name and nothing is
made; set them first:

```bash
hammunition station set --map-regions <region>
hammunition install antenna
```

The plan lists the tiles to download, the files to make and the disk they
take before anything happens. One tile took about 15 s and 151 MB of
memory to convert, and its two files are 6.5 MB (measured on one Copernicus
tile; a whole region has not yet been run through an install).

**What the converter does differently from SPLAT's own instructions.**
SPLAT's `srtm2sdf` tools replace every elevation below zero with their
neighbours' average unless told otherwise, which turns Death Valley, the
Dead Sea or a polder into dry land. Hammunition runs them with
`-n -32767`, so only true gaps in the data are filled.

### Point SPLAT! at it

Run this once, as yourself:

```bash
hammunition maps splat
```

It writes `~/.splat_path`, the file SPLAT! reads for its terrain directory,
when you have none. If you already have one naming another directory it is
left alone, and the command tells you to pass `-d` instead:

```bash
splat-hd -t site.qth -r other.qth -d /usr/local/share/hammunition/data/splat-sdf/
```

### A coverage plot from `FN31pr`'s centre

`FN31pr` is the documentation's placeholder grid square; its centre is
41.7292 N, 72.7083 W. Put your own position in its place, and make sure
your map regions cover the area the plot reaches, or the squares without
terrain read as sea level.

**Signal-Server**, a 2 m station 10 m up at 50 W ERP, 30 km out:

```bash
signalserverHD -sdf /usr/local/share/hammunition/data/splat-sdf/ \
  -lat 41.7292 -lon -72.7083 -txh 10 -f 146.52 -erp 50 -rxh 2 -m \
  -R 30 -res 3600 -pm 1 -rt -100 -dbm -nothreads -o fn31pr-coverage
```

It writes `fn31pr-coverage.ppm`, the map, and `fn31pr-coverage.dcf`, the
colour key in dBm. Any image viewer that reads PPM opens it; ImageMagick's
`convert fn31pr-coverage.ppm fn31pr-coverage.png` makes a PNG. `-pm` picks
the propagation model (1 is ITM, Longley-Rice; its usage text lists all
twelve). `signalserver`, without `HD` and without
`-res`, reads the 90 m files and is much faster.

**Always pass `-nothreads`.** Measured on 2026-10-01 over one tile at a
20 km radius, the threaded 30 m plot crashed 2 times in 10 and the
unthreaded one completed every time it was run, in 19 to 29 s with 1.36 GB
of memory; the 90 m plot took 1 to 2 s and 600 MB. A missing terrain file is
not an error in Signal-Server either: the square is taken as sea level with
a warning in its log, and it exits 0.

**SPLAT!**, line-of-sight coverage from the same spot, with a 2 m receiving
antenna. A site file gives the name, latitude, longitude west and positive,
and height:

```bash
printf 'FN31pr\n41.7292\n72.7083\n10 meters\n' > fn31pr.qth
splat -t fn31pr.qth -c 2 -R 30 -metric -o fn31pr.ppm -geo
```

`splat` covers up to 8 square degrees and `splat-hd` 4, by their own build;
on one tile a 20 km coverage map took `splat` 1.3 s and `splat-hd` 22 s.
`-geo` writes a `.geo` file beside the map, which is how Xastir lays a
picture over its own maps: the plot becomes an Xastir layer.

### Which readers the terrain serves

| Program | Reads | Served |
|---|---|---|
| QMapShack | one virtual raster over the tiles | yes, `dem-qmapshack` |
| SPLAT! | SPLAT Data Files | yes, `splat-sdf` |
| Signal-Server | the same files under its own names | yes, `splat-sdf` |
| Xastir | a GeoTIFF or a `.geo`-described image | not yet: an elevation layer for Xastir would be a shaded-relief image per tile with a `.geo` file beside it, not built because nobody has measured Xastir drawing one; SPLAT's `-geo` output is a layer today |
| gpredict, hamclock-next | nothing | a horizon mask from the elevation is what a satellite station would want; after 1.0 |

### What has not been measured yet

- `splat-sdf` through `hammunition install` on a real region: its time,
  memory and scratch over tens of tiles;
- SPLAT! and Signal-Server plots over that region on the field laptop;
- Signal-Server's threaded crash on other hardware, and the square east of
  Greenwich, whose name Signal-Server builds differently from SPLAT! (read
  from its source, linked accordingly, not run).

## The sites worth knowing

- **[PSKReporter](https://pskreporter.info/pskmap.html)** — who is hearing
  whom, right now, on which band, from real decodes. The single most useful
  propagation page in amateur radio: before you call, see whether anyone on
  the far end is decoding your band at all.
- **[VOACAP Online](http://www.voacap.com/hf/)** — point-to-point HF
  prediction: your station, their station, and the probability a circuit
  exists at each hour and frequency.
- **[N0NBH solar data](https://www.hamqsl.com/solar.html)** — Paul Herrman's
  solar-terrestrial banners: SFI, A and K indices, band-by-band condition
  calls at a glance. (AHRL's `solar_data` unit fetched one of these banners
  with `wget` and displayed it with a deprecated ImageMagick command — this
  link is that unit, without the plumbing.)
- **[DXLook](http://dxlook.com)** — live DX activity on a map, cluster spots
  and FT8 decodes merged.
- **[HamTab](http://hamtab.net)** — a shack browser-tab dashboard: clocks,
  conditions, spots in one page.
- **[Open HamClock](http://openhamclock.com)** — the web face of the
  HamClock world; the installed `hamclock-next` is its desk-side sibling.

## RF exposure

AHRL's `rf_exposure_calc` unit was a two-line script opening
**[hintlink's power-density calculator](http://hintlink.com/power_density.htm)**
in a browser. For US operators the durable reference is the ARRL's RF-exposure
material and the FCC's own calculator requirements that took effect in 2023 —
run your numbers when you change antenna, power, or shack layout, not once
ever. The [hamexposure.org calculator](https://hamexposure.org/) implements
the FCC formulas directly.
