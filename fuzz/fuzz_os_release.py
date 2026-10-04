# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Atheris target: the ``/etc/os-release`` parser (``distro.detect.parse_os_release``).

Any text in. The parser documents that it never raises on a malformed line.
"""

import sys

import atheris

with atheris.instrument_imports():
    from hammunition.distro.detect import parse_os_release

_SEED = (
    'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nNAME=\'Debian\'\nID=debian\n# c\nVERSION_ID="13"\n'
)


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    text = fdp.ConsumeUnicodeNoSurrogates(2048)
    if fdp.ConsumeBool():
        text = _SEED + text
    fields = parse_os_release(text)
    for key, value in fields.items():
        assert isinstance(key, str) and isinstance(value, str)


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
