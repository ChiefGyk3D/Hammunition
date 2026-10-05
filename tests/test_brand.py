# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The brand package: the logo, the mark, the palette, and the places that use them.

Modelled on hammunition-hill's test_brand.py, which was written against things
that actually shipped broken there (an unparseable mark, an opaque logo). The
checks here read the PNG headers directly rather than through Pillow, which the
test environment does not carry.
"""

from __future__ import annotations

import json
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "brand"
IMAGES = ROOT / "docs" / "images"
PALETTE = json.loads((BRAND / "palette.json").read_text(encoding="utf-8"))
MARKS = sorted(BRAND.glob("mark*.svg"))
RASTERS = sorted(p for p in BRAND.glob("*.png") if p.name != "logo-1254.png")


def png_header(path: Path) -> tuple[int, int, int]:
    """(width, height, colour type) from IHDR; colour type 6 is RGBA, 3 is palette."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    assert data[12:16] == b"IHDR"
    width, height, _depth, colour = struct.unpack(">IIBB", data[16:26])
    return width, height, colour


def has_transparency(path: Path) -> bool:
    _w, _h, colour = png_header(path)
    return colour in (4, 6) or b"tRNS" in path.read_bytes()


def comment_bodies(text: str) -> list[str]:
    """The text inside each <!-- ... --> pair, found by scanning, never by regex."""
    bodies: list[str] = []
    pos = 0
    while True:
        start = text.find("<!--", pos)
        if start < 0:
            return bodies
        end = text.find("-->", start + 4)
        if end < 0:
            return bodies
        bodies.append(text[start + 4 : end])
        pos = end + 3


def test_there_are_marks_to_check() -> None:
    assert {m.name for m in MARKS} == {"mark.svg", "mark-light.svg", "mark-mono.svg"}


@pytest.mark.parametrize("svg", MARKS, ids=lambda p: p.name)
def test_every_mark_is_well_formed_xml(svg: Path) -> None:
    root = ET.fromstring(svg.read_bytes())
    assert root.tag.endswith("svg")
    assert root.get("viewBox") == "0 0 64 64"


@pytest.mark.parametrize("svg", MARKS, ids=lambda p: p.name)
def test_every_mark_carries_its_licence_and_a_label(svg: Path) -> None:
    text = svg.read_text(encoding="utf-8")
    assert "SPDX-License-Identifier: CC0-1.0" in text, (
        f"{svg.name}: the marks are CC0 like the catalog"
    )
    assert "<title>Hammunition</title>" in text
    # XML forbids "--" inside a comment, and the parse above already enforces it;
    # this names the trap in the failure message. Scanned, not matched by regex:
    # CodeQL (py/bad-tag-filter) is right that a regex for "-->" is not a parser.
    for body in comment_bodies(text):
        assert "--" not in body, f"{svg.name}: a double hyphen inside a comment breaks the parse"


def test_the_marks_agree_on_geometry() -> None:
    """The variants are recolourings of mark.svg, never redrawings."""

    def paths(svg: Path) -> set[str]:
        return {
            re.sub(r"\s+", " ", d).strip()
            for d in re.findall(r'\sd="([^"]+)"', svg.read_text(encoding="utf-8"))
        }

    colour = paths(BRAND / "mark.svg")
    for variant in ("mark-light.svg", "mark-mono.svg"):
        shared = colour & paths(BRAND / variant)
        assert len(shared) >= 3, f"{variant} shares only {len(shared)} paths with mark.svg"


def test_the_colour_marks_use_only_the_palette() -> None:
    allowed = {v.lower() for v in PALETTE["brand"].values()}
    for name in ("mark.svg", "mark-light.svg"):
        used = {
            c.lower()
            for c in re.findall(
                r'fill="(#[0-9a-fA-F]{6})"', (BRAND / name).read_text(encoding="utf-8")
            )
        }
        assert used <= allowed, (
            f"{name} uses {sorted(used - allowed)}, which palette.json does not publish"
        )
    assert 'fill="currentColor"' in (BRAND / "mark-mono.svg").read_text(encoding="utf-8")


def test_the_site_serves_the_brand_mark_and_favicon() -> None:
    """mkdocs reads from docs/, so the site carries copies; they must be the brand files."""
    assert (IMAGES / "mark.svg").read_bytes() == (BRAND / "mark.svg").read_bytes()
    assert (IMAGES / "favicon.png").read_bytes() == (BRAND / "favicon-32.png").read_bytes()
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "  logo: images/mark.svg\n" in mkdocs
    assert "  favicon: images/favicon.png\n" in mkdocs


def test_the_readme_and_the_site_home_carry_the_logo() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert (
        "Renegade-Penguin/Hammunition/main/docs/images/logo.png"
        in readme.split("# Hammunition", 1)[0]
    )
    home = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert 'src="images/logo.png"' in home


@pytest.mark.parametrize(
    "png,size",
    [
        (IMAGES / "logo.png", 720),
        (IMAGES / "logo-256.png", 256),
        (BRAND / "logo-1254.png", 1254),
        (BRAND / "icon-512.png", 512),
        (BRAND / "apple-touch-icon.png", 180),
        (BRAND / "favicon-48.png", 48),
        (BRAND / "favicon-32.png", 32),
        (BRAND / "favicon-16.png", 16),
    ],
    ids=lambda v: v.name if isinstance(v, Path) else str(v),
)
def test_each_image_is_square_at_its_stated_size_and_transparent(png: Path, size: int) -> None:
    width, height, _ = png_header(png)
    assert (width, height) == (size, size), f"{png.name} is {width}x{height}"
    assert has_transparency(png), (
        f"{png.name} has no alpha and no tRNS: it would ship with a box behind it"
    )


def test_the_social_preview_is_github_shaped() -> None:
    width, height, _ = png_header(BRAND / "social-preview.png")
    assert (width, height) == (1280, 640)


@pytest.mark.parametrize("png", RASTERS, ids=lambda p: p.name)
def test_rasterised_assets_are_sane(png: Path) -> None:
    size = png.stat().st_size
    assert size > 300, f"{png.name} is {size} bytes: did the render fail?"
    assert size < 500_000, f"{png.name} is {size // 1024} kB: quantise it"


def test_the_palette_is_documented() -> None:
    page = (ROOT / "docs" / "contributing" / "branding.md").read_text(encoding="utf-8")
    for token, value in PALETTE["brand"].items():
        assert f"`{token}` | `{value}`" in page, f"branding.md does not list {token} as {value}"
