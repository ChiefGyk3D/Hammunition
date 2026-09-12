# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The USB vendor:product pair a udev rule line names, in any of the three
syntaxes a rule can use to name one.

Standard library only: this file is mounted into the sweep container beside
``udev-sweep.sh`` and imported there, so it has nothing but ``re`` to lean on.
It exists as a module because the same regexes lived inline in the sweep's
heredoc, where nothing could test them -- and one syntax of three was read,
which is how ``brltty`` had zero rows in a sweep that claimed to filter nothing
(found 2026-09-12, D-047). A parser that reads one syntax is a curated
shortlist by accident.

The three forms:

``ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001"``
    sysfs attributes, matched on the device or any parent. The common form,
    and the only one read before 2026-09-12.
``ENV{PRODUCT}=="403/6001/*"``
    the kernel's PRODUCT uevent string, ``vendor/product/bcdDevice`` in hex
    **without leading zeros**. brltty's whole rules file is written this way.
``ENV{ID_VENDOR_ID}=="0403", ENV{ID_MODEL_ID}=="6001"``
    the udev-builtin ``usb_id`` properties. udisks2, tlp-rdw and libhackrf0's
    rad1o lines use it.
"""

from __future__ import annotations

import re

ATTRS_PAIR = re.compile(
    r'idVendor\}\s*==\s*"([0-9a-fA-F]{4})".*?idProduct\}\s*==\s*"([0-9a-fA-F]{4})"'
)
PRODUCT_ENV = re.compile(r'ENV\{PRODUCT\}\s*==\s*"([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/')
ID_ENV = re.compile(
    r'ID_VENDOR_ID\}\s*==\s*"([0-9a-fA-F]{4})".*?ID_MODEL_ID\}\s*==\s*"([0-9a-fA-F]{4})"'
)
# Order matters. ENV{PRODUCT} and ENV{ID_*} are properties of the device the
# rule is being evaluated for; ATTRS{} walks up through the parents, and brltty's
# CH340 line names the device by PRODUCT and *its hub* by ATTRS -- read
# ATTRS first and the sweep files a Terminus hub as a braille display.
SYNTAXES = (PRODUCT_ENV, ID_ENV, ATTRS_PAIR)


def find_pair(text: str) -> tuple[str, str] | None:
    """``(vendor, product)`` as four lower-case hex digits each, or ``None``.

    A line naming only a vendor is ``None``: half a pair identifies nothing.
    """
    for rx in SYNTAXES:
        m = rx.search(text)
        if m:
            return m.group(1).lower().zfill(4), m.group(2).lower().zfill(4)
    return None
