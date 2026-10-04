# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Atheris target: the gpsd JSON the resume script and the time reader take in.

``gps_resume_script.devices`` and ``watch`` read newline-delimited JSON from
gpsd's TCP port and must ignore whatever a local account sends instead; the
fuzzed bytes are served to them through a fake socket (nothing opens a real
connection). The same input also goes to ``gpstime.state``'s ``ntpq`` readers,
which parse a daemon's text the same way.
"""

import sys

import atheris

with atheris.instrument_imports():
    from hammunition.gpstime import state
    from hammunition.hardware import gps_resume_script as script


class _Socket:
    """A connected socket that answers with *chunks*, then closes."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def __enter__(self) -> "_Socket":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def sendall(self, _data: bytes) -> None:
        return None

    def settimeout(self, _value: float | None) -> None:
        return None

    def recv(self, _size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


def _chunks(fdp: atheris.FuzzedDataProvider) -> list[bytes]:
    body = fdp.ConsumeBytes(fdp.ConsumeIntInRange(0, 2048))
    if fdp.ConsumeBool():
        # Well-formed lines around the noise reach the field handling.
        body = b'{"class":"DEVICES","devices":[{"path":"/dev/ttyACM0"}]}\n' + body
        body += b'\n{"class":"TPV","device":"/dev/ttyACM0","mode":3}\n'
    step = max(1, fdp.ConsumeIntInRange(1, 64))
    return [body[i : i + step] for i in range(0, len(body), step)]


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    chunks = _chunks(fdp)
    real = script.socket.create_connection
    script.socket.create_connection = lambda *_a, **_k: _Socket(list(chunks))  # type: ignore[assignment]
    try:
        script.devices("127.0.0.1", 2947, 5.0)
        script.watch("127.0.0.1", 2947, {0: {"/dev/ttyACM0"}, 1: {"/dev/gps1"}}, 5.0)
    finally:
        script.socket.create_connection = real
    text = fdp.ConsumeUnicodeNoSurrogates(2048)
    state.parse_peers(text)
    state.parse_rv(text)
    state.ntp_time(text)


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
