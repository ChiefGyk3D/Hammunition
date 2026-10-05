# Branding

The logo, the mark, the palette, and the rules for using them. The marks and
rasters live in [`brand/`](https://github.com/Renegade-Penguin/Hammunition/tree/main/brand);
the logo itself is in `docs/images/` because the README and this site use it.
The Hill has its own package in the same layout
([the Hill's branding page](https://github.com/Renegade-Penguin/hammunition-hill/blob/main/docs/BRANDING.md)),
drawn as a variation on this one.

<p align="center">
  <img src="../../images/logo.png" alt="Hammunition" width="360">
</p>

## The logo

Tux in a field cap with the circle-A, a mobile rig showing 144.390, a handheld,
a ruggedised laptop with a topographic map, a lattice mast, and a stack of
manuals labelled radio, mapping, repeaters, EMCOMM, Linux and offline, in front
of a sunset over mountains. The penguin is the author's own mark and is meant to
be there. Drawn by the maintainer, 2026-10-05.

| File | Use |
|---|---|
| `docs/images/logo.png` | 720 px, transparent. The primary logo: README, this site, the org profile. |
| `docs/images/logo-256.png` | 256 px, for anywhere the full file is wasteful. |
| `brand/logo-1254.png` | The artwork as delivered, 1254 px. Everything else is derived from it; re-derive from here, never from a derived file. |

## The mark

Used at 16 to 48 px as the favicon and the site's header icon. It is the
compass rose from the logo's own base, set in the sunset disc.

| File | Use |
|---|---|
| `brand/mark.svg` | Three colours on the ink disc, for dark grounds. Also served as `docs/images/mark.svg`. |
| `brand/mark-light.svg` | The same geometry on the purple disc, for light grounds. |
| `brand/mark-mono.svg` | One colour, inherited through `currentColor`. Screen printing, vinyl, laser, embroidery. |
| `brand/favicon-{16,32,48}.png`, `brand/apple-touch-icon.png`, `brand/icon-512.png` | Rasterised from `mark.svg` by headless Chromium, then `optipng`. |
| `brand/social-preview.png` | 1280 by 640, the logo on the ink colour, for GitHub's repository social preview. |

It is **not a shrunk logo**. At 16 px the full illustration is mud; a mark that
works small is a different drawing with the same identity. Two things found by
rendering rather than reasoning:

- The variants share their path data. `tests/test_brand.py` asserts that the
  light and mono marks reuse `mark.svg`'s paths, so none of them can drift.
- `mark-mono.svg` draws in `currentColor`, so it is for **inlining**. Loaded
  through an `<img>` tag it renders black, because an SVG referenced that way
  is an isolated document that cannot see the page around it.

## Palette

Published as `brand/palette.json`. Every value is **sampled from the artwork**,
not chosen beside it.

| Token | Hex | |
|---|---|---|
| `brand` | `#972883` | The sunset purple. |
| `brand-ink` | `#f99412` | The amber. |
| `brand-deep` | `#280423` | The aubergine ink every line is drawn in; the ground the mark and the social preview sit on. |
| `paper` | `#faedd6` | The cream of the lettering. |

The Hill's palette measures `#912795`, `#ed9a1c` and `#481050` from its own
artwork. The family is the shared hue; each repository publishes what its
artwork measures, and a new colour goes into that repository's palette file,
never beside it.

## Using it

- Keep clear space around the mark of at least a quarter of its width.
- Do not recolour it outside the palette; use `mark-mono.svg` when you have one
  ink.
- Do not set type in the logo's lettering style beside it; the logo carries its
  own name.
- The logo and the marks are **CC0-1.0**, like the catalog (D-023): they are
  data about the project, and a downstream that carries the catalog may carry
  the mark that goes with it.
- A new repository in the suite gets the same package in the same layout, with
  its own variation on the logo, and a line in its own `BRANDING.md` saying
  what it varied.
