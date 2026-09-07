# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The EmComm Tools inventory is read from upstream's scripts, not typed.

`scripts/gen_etc_inventory.py` parses every ``install-*.sh`` EmComm Tools OS
Community runs and classifies what each one does from the commands in it.
These tests pin the parser to fixture scripts written in upstream's own idiom
-- backslash-continued ``apt install`` lists, ``${VAR}`` URLs assembled from
``VERSION``, a ``dpkg -i`` of a fetched .deb -- so a change to the parser that
starts mis-reading a real script fails here by name. The tests that need the
upstream clone under ``reference/`` skip without it; the parser tests do not.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

GENERATOR = REPO_ROOT / "scripts" / "gen_etc_inventory.py"
CLONE = REPO_ROOT / "reference" / "emcomm-tools-os-community"
OUT = REPO_ROOT / "docs" / "reference" / "etc-inventory.md"


def _gen() -> object:
    spec = importlib.util.spec_from_file_location("gen_etc_inventory", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


APT_SCRIPT = """#!/bin/bash
. ./env.sh
et-log "Installing GIS tools..."
apt install \\
  gpsbabel \\
  gpsbabel-gui \\
  sqlite3 \\
  qgis -y
apt install libqt5serialport5:i386 -y
"""


def test_apt_packages_are_read_across_continuations() -> None:
    facts = _gen().parse_script("install-gis-tools.sh", APT_SCRIPT)  # type: ignore[attr-defined]
    assert facts.apt_install == [
        "gpsbabel",
        "gpsbabel-gui",
        "sqlite3",
        "qgis",
        "libqt5serialport5:i386",
    ]
    assert facts.method == "apt"


PURGE_SCRIPT = """#!/bin/bash
apt purge \\
  libreoffice-\\* \\
  thunderbird \\
  snapd -y
apt autoremove -y
"""


def test_purges_are_read_and_classified_as_removal() -> None:
    facts = _gen().parse_script("remove-packages.sh", PURGE_SCRIPT)  # type: ignore[attr-defined]
    assert facts.apt_purge == ["libreoffice-\\*", "thunderbird", "snapd"]
    assert facts.method == "removal"


DEB_SCRIPT = """#!/bin/bash
. ./env.sh
VERSION=0.16.0
FILE="pat_${VERSION}_linux_amd64.deb"
URL="https://github.com/la5nta/pat/releases/download/v${VERSION}/${FILE}"
cd ${ET_DIST_DIR}
curl -s -L -o ${FILE} --fail ${URL}
dpkg -i ${ET_DIST_DIR}/${FILE}
"""


def test_variables_resolve_into_the_fetched_url() -> None:
    facts = _gen().parse_script("install-winlink.sh", DEB_SCRIPT)  # type: ignore[attr-defined]
    assert facts.version == "0.16.0"
    assert (
        facts.url
        == "https://github.com/la5nta/pat/releases/download/v0.16.0/pat_0.16.0_linux_amd64.deb"
    )
    assert facts.method == "deb"
    assert facts.verifies_download is False


GIT_BUILD = """#!/bin/bash
APP="fldigi"
VERSION="4.2.09"
GIT_URL="https://git.code.sf.net/p/fldigi/fldigi"
[[ ! -e fldigi ]] && git clone ${GIT_URL} fldigi
git checkout v${VERSION}
autoreconf -f -i && ./configure --prefix=/opt/${APP}-${VERSION}
make
make install
"""

TARBALL_BUILD = """#!/bin/bash
VERSION=1.7
TARBALL=direwolf-$VERSION.tar.gz
URL=https://github.com/wb2osz/direwolf/archive/refs/tags/${VERSION}.tar.gz
curl -s -L -o $TARBALL --fail $URL
tar -xzf $TARBALL && cd direwolf-$VERSION
cmake ..
make -j4
make install
"""

PREBUILT = """#!/bin/bash
VERSION=1.0.4.1.3
DOWNLOAD_FILE=ardopcf_amd64_Linux_64
URL="https://github.com/pflarue/ardop/releases/download/${VERSION}/${DOWNLOAD_FILE}"
curl -s -L -o ${DOWNLOAD_FILE} --fail ${URL}
chmod +x ${DOWNLOAD_FILE}
ln -s /opt/ardop-${VERSION} /opt/ardop
"""

OVERLAY = """#!/bin/bash
cp -v ../overlay/etc/udev/rules.d/*.rules /etc/udev/rules.d/
systemctl mask brltty-udev.service
"""

SETUP_PY = """#!/bin/bash
VERSION=0.3.0
URL="https://github.com/mapbox/mbutil/archive/refs/tags/v${VERSION}.tar.gz"
curl -s -L -o mbutil.tar.gz --fail ${URL}
tar -xzf mbutil.tar.gz
python setup.py install
"""

DATA = """#!/bin/bash
URL="https://download.geofabrik.de/north-america.html"
curl -s -L -f -o index.html ${URL}
curl -L -f -O ${download_url}
maptool --protobuf -i ${download_file} /opt/maps/osm.bin
"""


@pytest.mark.parametrize(
    ("name", "text", "method"),
    [
        ("install-fldigi.sh", GIT_BUILD, "git build"),
        ("install-direwolf.sh", TARBALL_BUILD, "tarball build"),
        ("install-ardop.sh", PREBUILT, "prebuilt binary"),
        ("install-udev.sh", OVERLAY, "overlay"),
        ("install-mbutil.sh", SETUP_PY, "python setup.py"),
        ("download-osm-maps.sh", DATA, "data download"),
    ],
)
def test_method_is_classified_from_the_commands(name: str, text: str, method: str) -> None:
    facts = _gen().parse_script(name, text)  # type: ignore[attr-defined]
    assert facts.method == method, facts


def test_a_git_build_records_the_clone_url_and_version() -> None:
    facts = _gen().parse_script("install-fldigi.sh", GIT_BUILD)  # type: ignore[attr-defined]
    assert facts.url == "https://git.code.sf.net/p/fldigi/fldigi"
    assert facts.version == "4.2.09"


def test_checksum_verification_is_detected_when_present() -> None:
    text = DEB_SCRIPT + 'echo "abc  ${FILE}" | sha256sum -c -\n'
    facts = _gen().parse_script("install-winlink.sh", text)  # type: ignore[attr-defined]
    assert facts.verifies_download is True


ORCHESTRATOR = """#!/bin/bash
. ./env.sh
exitIfNotRoot
./bootstrap.sh
./install-base.sh
./install-udev.sh
./install-gps.sh
[ ! -z "${ET_EXPERT}" ] && ./download-wikipedia.sh
./install-wsjtx.sh
"""


def test_orchestrated_order_is_read_from_install_sh() -> None:
    steps = _gen().parse_orchestrator(ORCHESTRATOR)  # type: ignore[attr-defined]
    assert [s.script for s in steps] == [
        "bootstrap.sh",
        "install-base.sh",
        "install-udev.sh",
        "install-gps.sh",
        "download-wikipedia.sh",
        "install-wsjtx.sh",
    ]
    assert [s.script for s in steps if s.expert_only] == ["download-wikipedia.sh"]


def test_every_curated_catalog_name_is_a_real_manifest() -> None:
    """The overlap column is computed against the catalog; a typo here would
    report a covered unit as a delta, or the reverse."""
    gen = _gen()
    names = {p.stem for p in (REPO_ROOT / "catalog" / "packages").glob("*.yaml")}
    missing = sorted(
        f"{script}: {n}"
        for script, entry in gen.CURATION.items()  # type: ignore[attr-defined]
        for n in entry.catalog
        if n not in names
    )
    assert not missing, "CURATION names manifests that do not exist:\n  " + "\n  ".join(missing)


needs_clone = pytest.mark.skipif(
    not (CLONE / "scripts" / "install.sh").exists(),
    reason="needs the upstream clone under reference/ — see the generator's docstring",
)


@needs_clone
def test_curation_covers_exactly_the_scripts_upstream_ships() -> None:
    gen = _gen()
    shipped = {p.name for p in (CLONE / "scripts").glob("*.sh")} - set(gen.NOT_UNITS)  # type: ignore[attr-defined]
    curated = set(gen.CURATION)  # type: ignore[attr-defined]
    assert shipped == curated, (
        f"uncurated: {sorted(shipped - curated)}; curated but not shipped: {sorted(curated - shipped)}"
    )


@needs_clone
def test_regenerating_the_inventory_is_a_no_op() -> None:
    gen = _gen()
    before = OUT.read_text()
    after = gen.render()  # type: ignore[attr-defined]

    def without_date(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if not ln.startswith("**Generated:**")]

    assert without_date(before) == without_date(after), (
        "docs/reference/etc-inventory.md is stale — regenerate it"
    )
