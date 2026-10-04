# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a screen may ask of the application, as a Protocol, so screens are
tested against a fake and never import the Shell."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from hammunition.console.config import Config
from hammunition.console.engine import Document
from hammunition.console.worker import Background

if TYPE_CHECKING:
    from hammunition.console.screens.base import Screen


@dataclass
class Shared:
    """What the one-line header shows. Never a station value: only whether it is set."""

    engine_version: str = "?"
    target: str = "?"
    doctor: tuple[int, int, int] | None = None
    station_set: bool | None = None

    def header_text(self) -> str:
        doctor = "?" if self.doctor is None else f"{self.doctor[0]}F {self.doctor[1]}W"
        station = "?" if self.station_set is None else ("set" if self.station_set else "not set")
        return f"hammunition {self.engine_version} | {self.target} | doctor {doctor} | station {station}"


class EngineLike(Protocol):
    def command(self, *words: str) -> list[str]: ...

    def read(self, *words: str, timeout: float | None = ...) -> Document: ...


class Context(Protocol):
    engine: EngineLike
    config: Config
    bg: Background
    shared: Shared

    def push(self, screen: Screen) -> None: ...
    def pop(self, count: int = 1) -> None: ...
    def replace(self, screen: Screen) -> None: ...
    def open_screen(self, name: str, **kwargs: Any) -> None: ...
    def run_pane(
        self, argv: Sequence[str], title: str, on_exit: Callable[[int | None], None]
    ) -> None: ...
    def fatal(self, exc: BaseException) -> None: ...
    def refresh_header(self) -> None: ...
    def after(self, seconds: float, fn: Callable[[], None]) -> None: ...
    def save_config(self) -> None: ...


def header_target(target: Mapping[str, Any] | None) -> str:
    """A short target name for the header from a TargetView."""
    if not target:
        return "?"
    pretty = target.get("pretty_name")
    if isinstance(pretty, str) and pretty:
        return pretty
    return f"{target.get('distro', '?')} {target.get('version', '')}".strip()
