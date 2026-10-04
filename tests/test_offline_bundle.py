# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The offline documentation bundle (issue #298) works with the network off.

`scripts/build_offline_bundle.py` builds the bundle and verifies it. A verifier
nobody has seen fail is a check nobody should trust (CLAUDE.md), so most of this
file breaks a small valid bundle on purpose, one way at a time, and asserts the
verifier names the fault. One test builds the real bundle and requires it clean.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _script() -> ModuleType:
    path = REPO_ROOT / "scripts" / "build_offline_bundle.py"
    spec = importlib.util.spec_from_file_location("build_offline_bundle", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_offline_bundle"] = module
    spec.loader.exec_module(module)
    return module


bundle = _script()


def _page(extra_head: str = "", body: str = "", footer: str = "Offline copy built today") -> str:
    return (
        "<html><head>"
        '<link rel="stylesheet" href="assets/style.css">'
        '<script src="assets/vendor/iframe-worker/shim.js"></script>'
        f"{extra_head}</head><body>"
        f'<div class="md-copyright">{footer}</div>'
        f'<h2 id="here">Here</h2><a href="other.html#there">other</a>{body}'
        "</body></html>"
    )


def _make(root: Path) -> Path:
    """The smallest folder the verifier accepts."""
    (root / "assets/vendor/iframe-worker").mkdir(parents=True)
    (root / "search").mkdir()
    (root / "suite").mkdir()
    (root / "emcomm").mkdir()
    (root / "offline").mkdir()
    (root / "index.html").write_text(_page())
    (root / "other.html").write_text('<h2 id="there">There</h2>')
    for name in ("suite", "emcomm", "offline"):
        (root / name / "index.html").write_text("<p>x</p>")
    (root / "assets/style.css").write_text('a::after{content:" (online)"}')
    (root / "assets/vendor/iframe-worker/shim.js").write_text("//")
    locations = [
        "index.html",
        "other.html",
        "suite/index.html",
        "emcomm/index.html",
        "offline/index.html",
    ]
    (root / "search/search_index.json").write_text(
        json.dumps({"docs": [{"location": loc} for loc in locations]})
    )
    (root / "search/search_index.js").write_text("var __index = {}")
    for name in ("README-OFFLINE.txt", "BUILD-INFO.txt", "THIRD-PARTY-NOTICES.txt", "LICENSE"):
        (root / name).write_text(name)
    return root


def _problems(root: Path) -> list[str]:
    bundle.write_sums(root)
    return list(bundle.verify(root)) + list(bundle.verify_sums(root))


@pytest.fixture
def good(tmp_path: Path) -> Path:
    root = _make(tmp_path / "b")
    assert _problems(root) == []
    return root


@pytest.mark.parametrize(
    ("head", "body", "needle"),
    [
        ('<script src="https://cdn.example.org/x.js"></script>', "", "loads https://cdn"),
        ('<link rel="stylesheet" href="//fonts.example/f.css">', "", "loads //fonts"),
        ('<link rel="preconnect" href="https://fonts.gstatic.com">', "", "fonts.gstatic.com"),
        ('<script src="missing.js"></script>', "", "missing asset missing.js"),
        ("", '<img src="https://example.org/i.png">', "loads https://example.org/i.png"),
        ("", '<div style="background:url(https://x.test/a.png)"></div>', "inline style"),
        ("", '<a href="nowhere.html">gone</a>', "broken link nowhere.html"),
        ("", '<a href="other.html#absent">gone</a>', "missing anchor"),
        ("", '<a href="/etc/passwd">abs</a>', "broken link /etc/passwd"),
        ("", '<pre class="mermaid">graph</pre>', "mermaid"),
        ("", '<div data-md-component="source"></div>', "repository widget"),
    ],
)
def test_the_verifier_names_each_fault(good: Path, head: str, body: str, needle: str) -> None:
    home = (good / "index.html").read_text()
    (good / "index.html").write_text(
        home.replace("</head>", head + "</head>").replace("</body>", body + "</body>")
    )
    problems = _problems(good)
    assert any(needle in p for p in problems), (needle, problems)


def test_an_external_link_is_allowed_because_it_is_marked(good: Path) -> None:
    home = (good / "index.html").read_text()
    (good / "index.html").write_text(
        home.replace(
            "</body>", '<a href="https://github.com/ChiefGyk3D/Hammunition">repo</a></body>'
        )
    )
    assert _problems(good) == []


def test_a_css_import_from_the_internet_fails(good: Path) -> None:
    (good / "assets/style.css").write_text('@import url("https://fonts.example/x.css");(online)')
    assert any("loads https://fonts.example" in p for p in _problems(good))


def test_a_stylesheet_asset_that_is_missing_fails(good: Path) -> None:
    (good / "assets/style.css").write_text('a{background:url("gone.png")}(online)')
    assert any("missing asset gone.png" in p for p in _problems(good))


def test_a_script_naming_a_cdn_fails(good: Path) -> None:
    (good / "assets/vendor/iframe-worker/shim.js").write_text('load("https://unpkg.com/x")')
    assert any("unpkg.com" in p for p in _problems(good))


def test_the_known_conditional_scripts_are_not_a_fault(good: Path) -> None:
    (good / "assets/vendor/iframe-worker/shim.js").write_text(
        'load("https://unpkg.com/resize-observer-polyfill")'
    )
    assert _problems(good) == []


def test_a_missing_search_index_fails(good: Path) -> None:
    (good / "search/search_index.js").unlink()
    assert any("search_index.js" in p for p in _problems(good))


def test_an_incomplete_search_index_fails(good: Path) -> None:
    (good / "search/search_index.json").write_text(
        json.dumps({"docs": [{"location": "index.html"}]})
    )
    assert any("not complete" in p or "lacks" in p for p in _problems(good))


def test_unmarked_external_links_fail(good: Path) -> None:
    (good / "assets/style.css").write_text("a{}")
    assert any("(online)" in p for p in _problems(good))


def test_a_home_page_without_the_build_line_fails(good: Path) -> None:
    (good / "index.html").write_text(_page(footer="nothing here"))
    assert any("build date" in p for p in _problems(good))


def test_a_changed_file_fails_the_checksums(good: Path) -> None:
    (good / "other.html").write_text('<h2 id="there">Edited</h2>')
    problems = bundle.verify_sums(good)
    assert any("checksum mismatch: other.html" in p for p in problems)


def test_the_checksums_cover_every_file(good: Path) -> None:
    (good / "extra.txt").write_text("x")
    assert any("not in SHA256SUMS: extra.txt" in p for p in bundle.verify_sums(good))
    listed = (good / "SHA256SUMS").read_text()
    digest = hashlib.sha256((good / "LICENSE").read_bytes()).hexdigest()
    assert f"{digest}  LICENSE" in listed


def test_the_build_line_names_date_commit_and_versions() -> None:
    from datetime import UTC, datetime

    info = bundle.build_info("abc1234567890", datetime(2026, 1, 2, 3, 4, tzinfo=UTC))
    line = bundle.build_line(info)
    assert "2026-01-02 03:04 UTC" in line and "abc123456789" in line
    assert "hammunition-hill" in line and "gps-tether" in line
    assert info["engine"] in line


def test_the_real_bundle_builds_and_verifies(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_offline_bundle.py"),
            "--out",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    zips = list(tmp_path.glob("hammunition-docs-*.zip"))
    assert len(zips) == 1
    folder = tmp_path / "hammunition-docs"
    assert (folder / "index.html").is_file()
    assert (folder / "BUILD-INFO.txt").read_text().startswith("Hammunition offline documentation")
    # The same check, run on its own, as a reader would run it on a copy.
    verify = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_offline_bundle.py"),
            "--verify",
            str(folder),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify.returncode == 0, verify.stderr
