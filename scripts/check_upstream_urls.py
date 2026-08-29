#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Request every `upstream_url` in the catalog and report what does not answer.

CLAUDE.md requires each manifest to name "where to get real support for the
software itself". A URL that no longer resolves fails that quietly: it reads as
authoritative, and the operator finds out by getting nothing.

This is not theoretical. Checking by hand while writing manifests turned up
five upstreams in one night that Debian still declares and that are gone or no
longer the project's -- `w1hkj.com` 301s to a host with no DNS record,
`xastir.org` and `christianjacobs.uk` have no DNS at all, `wa0eir.bcts.info`
covers three packages and does not resolve, `opendigitalradio.org` answers
nothing on either scheme. Doing it by hand also MISSED one: pyqso's
`upstream_url` went in unchecked because the GitHub link in the same manifest
had been checked instead. Hence a script.

**Deliberately not in CI, and not in the test suite.** External URLs fail for
reasons that have nothing to do with this repository -- a site is down for an
hour, a host rate-limits a runner, a CDN blocks a data-centre range -- and a
check that reddens for those is the calendar-driven failure that teaches people
to ignore CI. `scripts/check_doc_links.py` declines external URLs for the same
reason. The test suite additionally blocks every non-loopback socket by design.

So this is a tool a maintainer runs, like `check_pin_reviews.py --verify-refs`.
Run it when writing manifests, and periodically.

A non-200 is a prompt to look, not a verdict:

* **000** -- no connection at all. Usually DNS, and usually real. Check with
  `getent hosts` before concluding: a host that resolves only to IPv6 will read
  as dead from a machine with no IPv6 route, which is how quisk's upstream
  nearly got recorded as gone.
* **403** -- very often bot-blocking rather than absence. Try it in a browser.
* **404** -- the path moved. The site may be fine; the manifest is not.
* **301/302** are followed, and the code reported is where the chain *ended*.
  A redirect landing on a healthy page elsewhere therefore reports 200 and
  looks fine -- which is the case this script cannot judge, and why
  `--show-final` prints where each request ended. Read those. `w1hkj.com` is
  the example and it is not quite that case: it 301s to a host with no DNS, so
  the chain dies and the reported code is 301. Its subpaths return 404. Both
  are caught; a redirect onto a live unrelated site would not be.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402

CATALOG = REPO_ROOT / "catalog" / "packages"
TIMEOUT = "25"


def probe(url: str, show_final: bool) -> tuple[str, str]:
    """Return (http status, final URL after redirects). '000' means no answer."""
    fmt = "%{http_code}\t%{url_effective}" if show_final else "%{http_code}\t"
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", fmt, "-L", "--max-time", TIMEOUT, url],
            capture_output=True,
            text=True,
            check=False,
            timeout=int(TIMEOUT) + 10,
        )
    except subprocess.TimeoutExpired:
        return "000", url
    code, _, final = result.stdout.partition("\t")
    return (code or "000"), (final or url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-final",
        action="store_true",
        help="print the URL each request ended at, so a redirect off-project is visible",
    )
    parser.add_argument("--only", help="check one package by name")
    args = parser.parse_args()

    catalog = load_catalog(CATALOG)
    if args.only:
        if args.only not in catalog:
            sys.exit(f"no such package: {args.only}")
        catalog = {args.only: catalog[args.only]}

    by_url: dict[str, list[str]] = {}
    for name, manifest in sorted(catalog.items()):
        by_url.setdefault(manifest.documentation.upstream_url, []).append(name)

    print(f"checking {len(by_url)} distinct upstream URL(s) across {len(catalog)} manifest(s)\n")
    bad: list[tuple[str, str, str, list[str]]] = []
    for url, names in sorted(by_url.items()):
        code, final = probe(url, args.show_final)
        if code != "200":
            bad.append((code, url, final, names))
        elif args.show_final and final.rstrip("/") != url.rstrip("/"):
            print(f"  redirect  {url}\n         -> {final}   ({', '.join(names)})")

    if not bad:
        print("every upstream URL answered 200")
        return 0

    print(f"\n{len(bad)} URL(s) did not answer 200:\n")
    for code, url, final, names in sorted(bad):
        print(f"  {code}  {url}")
        if args.show_final and final.rstrip("/") != url.rstrip("/"):
            print(f"        -> {final}")
        print(f"        {', '.join(names)}")
    print(
        "\nA non-200 is a prompt to look, not a verdict. 000 is usually DNS and usually\n"
        "real -- but confirm with `getent hosts` first, because an IPv6-only host reads\n"
        "as dead from a machine with no IPv6 route. 403 is often bot-blocking."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
