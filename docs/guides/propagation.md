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
- **WSJT-X's own WSPR mode** — the empirical answer: beacon a few milliwatts
  and see where you are actually heard.

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
