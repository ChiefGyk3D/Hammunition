# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Atheris target: the Maidenhead grid-square parser (``maidenhead.centre``).

Any string in; a ``LocatorError`` is the documented rejection. A locator that
is accepted must give a centre on the globe.
"""

import sys

import atheris

with atheris.instrument_imports():
    from hammunition.maidenhead import LocatorError, centre


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    text = fdp.ConsumeUnicodeNoSurrogates(32)
    try:
        lat, lon = centre(text)
    except LocatorError:
        return
    assert -90.0 <= lat <= 90.0, (text, lat)
    assert -180.0 <= lon <= 180.0, (text, lon)


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
