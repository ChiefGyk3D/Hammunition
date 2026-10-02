#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate the WRI Global Power Plant Database pin.  D-075.

WRI's database v1.3.0 is one zip on S3, frozen since 2021-06-02
(4,178,889 bytes, CC BY 4.0 in its README). S3's ETag for a single-part
object is the MD5 of its bytes: the publisher's own checksum, which the spike
matched. This fetches the zip, checks its MD5 against the ETag the same
answer carried, checks the CSV and the README's licence are there, and
writes our sha256, the size and the publisher's MD5 (a comment line the
generator owns) into ``catalog/packages/wri-power-plants.yaml``. MD5 catches
a damaged download, not a deliberately altered one; the sha256 is the pin.

``--check`` HEADs the URL and goes red when its ETag or size no longer
match; ``--check --offline`` checks the manifest's shape only.

    scripts/gen_wri_pin.py                    # regenerate (4.2 MB)
    scripts/gen_wri_pin.py --check            # a HEAD
    scripts/gen_wri_pin.py --check --offline  # the manifest's shape only
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import zipfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_pin  # noqa: E402
from hammunition.manifest.load import load_manifest  # noqa: E402
from hammunition.manifest.schema import DataInstall  # noqa: E402

MANIFEST = REPO_ROOT / "catalog" / "packages" / "wri-power-plants.yaml"
HOST = "https://wri-dataportal-prod.s3.amazonaws.com/"
URL = f"{HOST}manual/global_power_plant_database_v_1_3.zip"
INSTALL_AS = "global_power_plant_database.zip"
CSV = "global_power_plant_database.csv"
LICENCE = "CC-BY-4.0"
LIMIT = 32 * 1024 * 1024
REGENERATE = "regenerate with scripts/gen_wri_pin.py"
OWNED = ("sha256", "size", "md5")
_MD5 = re.compile(r"^# publisher MD5 \(the S3 ETag\): ([0-9a-f]{32})$", re.MULTILINE)

Ask = Callable[..., data_pin.Answer]


def etag_md5(headers: Mapping[str, str]) -> str:
    """The single-part ETag as an MD5, or "" when it is not one."""
    value = headers.get("etag", "").strip().strip('"')
    return value if re.fullmatch(r"[0-9a-f]{32}", value) else ""


def checked_body(body: bytes, etag: str) -> tuple[str, int, str]:
    """sha256, size and MD5 of *body*, or SystemExit when its MD5 is not the
    ETag or it is not WRI's database under CC BY 4.0."""
    md5 = hashlib.md5(body, usedforsecurity=False).hexdigest()
    if not etag:
        raise SystemExit(
            "S3 sent no single-part ETag to check the MD5 against. Nothing was written."
        )
    if md5 != etag:
        raise SystemExit(f"the download's MD5 {md5} is not the ETag {etag}. Nothing was written.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
        names = set(archive.namelist())
        readme = archive.read("README.txt").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise SystemExit(f"not WRI's database zip ({exc}). Nothing was written.") from None
    if CSV not in names:
        raise SystemExit(f"the zip holds no {CSV}. Nothing was written.")
    if "Creative Commons Attribution 4.0" not in readme:
        raise SystemExit("the README no longer states CC BY 4.0. Nothing was written.")
    return hashlib.sha256(body).hexdigest(), len(body), md5


def _block(path: Path) -> DataInstall:
    block = load_manifest(path).install[0].install
    if not isinstance(block, DataInstall):
        raise SystemExit(f"{path}: its first install block is not a data block")
    return block


def pinned_md5(path: Path) -> str:
    found = _MD5.findall(path.read_text())
    return found[0] if len(found) == 1 else ""


def shape_problems(path: Path) -> list[str]:
    """What is wrong with the manifest, offline."""
    try:
        block = _block(path)
    except Exception as exc:  # a schema or YAML error, named
        return [f"{path.name} does not load: {exc}"]
    if len(block.artifacts) != 1:
        return [f"{path.name} must carry exactly one artifact"]
    artifact = block.artifacts[0]
    problems: list[str] = []
    if artifact.url != URL:
        problems.append(f"the URL is {artifact.url!r}, not {URL!r}")
    if artifact.install_as != INSTALL_AS:
        problems.append(f"the artifact must install as {INSTALL_AS}")
    if block.licence != LICENCE:
        problems.append(f"the licence must be {LICENCE!r}, as WRI's README states it")
    if set(artifact.sha256) == {"0"} or artifact.size <= 1:
        problems.append(f"the pin is a placeholder; {REGENERATE}")
    problems += data_pin.owned_problems(path.read_text(), OWNED, path.name)
    return problems


def main(
    argv: Sequence[str] | None = None,
    *,
    ask: Ask | None = None,
    manifest_path: Path = MANIFEST,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="check the pin; write nothing")
    parser.add_argument(
        "--offline", action="store_true", help="with --check: the manifest's shape only"
    )
    args = parser.parse_args(argv)
    get = ask or data_pin.ask

    if args.check:
        problems = shape_problems(manifest_path)
        if not problems and not args.offline:
            artifact = _block(manifest_path).artifacts[0]
            head = get(URL, HOST, method="HEAD", limit=0)
            length = head.headers.get("content-length", "")
            etag = etag_md5(head.headers)
            if (
                head.status != 200
                or etag != pinned_md5(manifest_path)
                or (length and int(length) != artifact.size)
            ):
                problems.append(
                    f"{URL} answered {head.status}, ETag {etag or 'none'}, {length or 'no'} "
                    f"bytes; pinned MD5 {pinned_md5(manifest_path)}, {artifact.size} bytes. "
                    f"WRI's file was frozen in 2021: {REGENERATE} only after reading why it moved"
                )
        if problems:
            print(f"{len(problems)} problem(s):")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print(f"{manifest_path.name} is " + ("well formed" if args.offline else "up to date"))
        return 0

    answer = get(URL, HOST, limit=LIMIT)
    if answer.status != 200:
        raise SystemExit(f"{URL} answered {answer.status}. Nothing was written.")
    sha256, size, md5 = checked_body(answer.body, etag_md5(answer.headers))
    data_pin.write(
        manifest_path,
        data_pin.rewrite(
            manifest_path.read_text(), {"sha256": sha256, "size": str(size), "md5": md5}
        ),
    )
    # Verify the effect, not the exit status (D-031): read back what was written.
    artifact = _block(manifest_path).artifacts[0]
    if (artifact.sha256, artifact.size, pinned_md5(manifest_path)) != (sha256, size, md5):
        raise SystemExit(f"{manifest_path} did not take the new pin; check it by hand")
    print(f"wrote {manifest_path.name}: {size:,} bytes, MD5 {md5} (the ETag), sha256 {sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
