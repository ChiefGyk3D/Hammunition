# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Grouping repeated same-shape plan steps for the text rendering.  D-016.

A unit that does one thing for each of hundreds of items (a US Topo sheet, a
terrain tile, a Kiwix book) puts hundreds of near-identical steps in the plan.
Printed in full that hides the plan under its own repetition. The text
rendering therefore collapses a run of steps that share a *template* into one
block: the template once, one fully written-out example, then every item on
its own short line, then the totals.

Nothing is lost, and this module proves it every time it runs:

* A template is found from the steps' own rendered text (description and
  display together), never from a per-unit rule. Two in-process steps share one
  when they have the same kind, the same privilege, the same number of tokens
  and agree on at least half of them. Commands never group. The tokens that differ are the per-item arguments.
* A group is kept only if rebuilding every step from its template and its item
  values gives back that step's text exactly (:meth:`Group.expand`). A run that
  does not round-trip is printed step by step instead.
* The JSON document and the transaction log never see this: both carry every
  step already. ``--full`` prints every step expanded.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

__all__ = [
    "Group",
    "Renderable",
    "group_steps",
    "render_steps",
]

#: Fewest repeats worth collapsing. Three of anything is still readable.
MIN_REPEATS = 4

#: Longest repeating unit searched for: fetch, install and prune is three.
MAX_PERIOD = 4

_GLUE = "\x00"
_SIZE = re.compile(
    r"(?<![\w.])(\d[\d,]*(?:\.\d+)?) (kB|KB|MB|GB|TB|KiB|MiB|GiB|TiB)\b",
)
_SIZE_CORE = re.compile(r"^(\d[\d,]*(?:\.\d+)?)[\x00 ](kB|KB|MB|GB|TB|KiB|MiB|GiB|TiB)$")
_FLAG = re.compile(r"^-{1,2}[A-Za-z]")
_NUMBER = re.compile(r"^[-+]?\d[\d.,]*$")
_UNITS = {
    "kB": 1e3,
    "KB": 1e3,
    "MB": 1e6,
    "GB": 1e9,
    "TB": 1e12,
    "KiB": 1024.0,
    "MiB": 1024.0**2,
    "GiB": 1024.0**3,
    "TiB": 1024.0**4,
}
_PREFIX_CUTS = "/=(['\""
_SUFFIX_CUTS = ".,;:)]'\""


class Renderable(Protocol):
    """What a step must show to be grouped: :class:`~hammunition.interface.plan.StepView`."""

    @property
    def description(self) -> str: ...
    @property
    def display(self) -> str: ...
    @property
    def action(self) -> str | None: ...
    @property
    def requires_root(self) -> bool: ...
    @property
    def index(self) -> int: ...


def _tokens(step: Renderable) -> list[str]:
    text = _SIZE.sub(
        lambda m: f"{m.group(1)}{_GLUE}{m.group(2)}", f"{step.description}\n{step.display}"
    )
    return re.findall(r"\S+|\s+", text)


def _kind(step: Renderable) -> tuple[object, ...] | None:
    """What may never vary inside a group: the kind of step and its privilege.

    ``None`` for a command. Only the engine's own in-process steps (a fetch, a
    convert, an install-data) group: a command is a program run on the machine,
    and ``install -m 0755 a /usr/local/b`` then ``install -m 0755 c /usr/local/d``
    are two modifications an operator reads one by one, not one modification on
    two items. Every repeated-step unit measured (D-016 amendment) is made of
    in-process steps.
    """
    if step.action is None:
        return None
    return (step.action, step.requires_root)


def _compatible(a: Sequence[str], b: Sequence[str]) -> bool:
    """Whether two token lists are one template with different arguments.

    Whitespace never varies, a flag (``--x``) or a URL scheme never varies (those
    change what a step does, not which item it is done to), and the words, not the
    spaces between them, must mostly agree.
    """
    if len(a) != len(b) or a[0] != b[0]:
        # The description's first word is the verb: "Fetch", "Remove" and
        # "Install" are three actions, never one action on three items.
        return False
    words = same = 0
    for x, y in zip(a, b, strict=True):
        if x.isspace() or y.isspace():
            if x != y:
                return False
            continue
        words += 1
        if x == y:
            same += 1
        elif (
            _FLAG.match(x)
            or _FLAG.match(y)
            or ("://" in x and "://" in y and x.split("://")[0][-8:] != y.split("://")[0][-8:])
        ):
            return False
    return same >= 2 and same * 2 >= words


def _cut_prefix(prefix: str) -> str:
    """The part of a common prefix that ends at a separator, so a name is kept whole."""
    for index in range(len(prefix) - 1, -1, -1):
        if prefix[index] in _PREFIX_CUTS:
            return prefix[: index + 1]
    return ""


def _cut_suffix(suffix: str) -> str:
    for index, char in enumerate(suffix):
        if char in _SUFFIX_CUTS:
            return suffix[index:]
    return ""


def _common(values: Sequence[str]) -> tuple[str, str]:
    """The prefix and suffix every value shares, cut at separators."""
    if all(_NUMBER.match(v) for v in values) or all(_SIZE_CORE.match(v) for v in values):
        return "", ""
    first = values[0]
    limit = min(len(v) for v in values)
    p = 0
    while p < limit and all(v[p] == first[p] for v in values):
        p += 1
    prefix = _cut_prefix(first[:p])
    s = 0
    limit -= len(prefix)
    while s < limit and all(v[len(v) - 1 - s] == first[len(first) - 1 - s] for v in values):
        s += 1
    suffix = _cut_suffix(first[len(first) - s :]) if s else ""
    return prefix, suffix


@dataclass(frozen=True)
class Slot:
    """One token position that varies, and how the column that fills it is named."""

    phase: int
    index: int
    prefix: str
    suffix: str
    column: int


@dataclass(frozen=True)
class Group:
    """A run of repeated steps: *period* steps per item, *items* items."""

    period: int
    columns: tuple[str, ...]
    """Placeholder names, in the order the columns are listed."""
    items: tuple[tuple[str, ...], ...]
    """Per item, one value for each column."""
    templates: tuple[tuple[str, ...], ...]
    """Per phase, the tokens with ``\\x01N\\x01`` standing where column N goes."""
    steps: tuple[Renderable, ...]
    """The steps the group stands for, in order, kept so the group can be proved."""

    def expand(self) -> list[tuple[str, str]]:
        """Every step rebuilt as (description, display) from template and values."""
        rebuilt: list[tuple[str, str]] = []
        for values in self.items:

            def put(match: re.Match[str], values: tuple[str, ...] = values) -> str:
                return values[int(match.group(1))]

            for template in self.templates:
                text = "".join(re.sub(r"\x01(\d+)\x01", put, t) for t in template)
                description, _, display = text.replace(_GLUE, " ").partition("\n")
                rebuilt.append((description, display))
        return rebuilt

    def total_bytes(self) -> dict[str, float]:
        """The sum of every size column, by its name."""
        totals: dict[str, float] = {}
        for index, name in enumerate(self.columns):
            parsed = [_SIZE_CORE.match(item[index]) for item in self.items]
            if parsed and all(parsed):
                totals[name] = sum(
                    float(m.group(1).replace(",", "")) * _UNITS[m.group(2)] for m in parsed if m
                )
        return totals


def _placeholder_name(
    tokens: Sequence[str],
    index: int,
    varying: dict[int, int],
    names: list[str],
    sizes: bool,
    numeric: bool,
) -> str:
    if sizes:
        base = "size"
    else:
        base = "num" if numeric else "item"
        before = index - 2  # the token before the whitespace before this one
        if before >= 0 and before not in varying:
            match = re.fullmatch(r"-{0,2}([A-Za-z][A-Za-z_-]{0,19}):?", tokens[before])
            word = match.group(1).lower().replace("-", "_") if match else ""
            if word and word not in {"about", "and", "then", "the", "as", "in", "for", "of"}:
                base = word
        elif before >= 0 and before in varying:
            previous = names[varying[before]]
            stem = re.sub(r"\d+$", "", previous)
            number = int(previous[len(stem) :] or 1) + 1
            base = f"{stem}{number}"
    name = base
    n = 2
    while name in names:
        name = f"{base}{n}"
        n += 1
    return name


def _build(steps: Sequence[Renderable], period: int, repeats: int) -> Group | None:
    block = [_tokens(s) for s in steps[:period]]
    per_phase: list[list[list[str]]] = [[] for _ in range(period)]
    for i in range(repeats):
        for phase in range(period):
            per_phase[phase].append(_tokens(steps[i * period + phase]))
    columns: list[str] = []
    vectors: dict[tuple[str, ...], int] = {}
    templates: list[list[str]] = []
    slots: list[Slot] = []
    for phase in range(period):
        rows = per_phase[phase]
        template: list[str] = []
        varying: dict[int, int] = {}
        for index in range(len(block[phase])):
            values = [row[index] for row in rows]
            if all(v == values[0] for v in values):
                template.append(values[0])
                continue
            prefix, suffix = _common(values)
            cores = tuple(v[len(prefix) : len(v) - len(suffix)] for v in values)
            if cores not in vectors:
                sizes = all(_SIZE_CORE.match(c) for c in cores)
                numeric = all(_NUMBER.match(c) for c in cores)
                vectors[cores] = len(columns)
                columns.append(
                    _placeholder_name(block[phase], index, varying, columns, sizes, numeric)
                )
            column = vectors[cores]
            varying[index] = column
            slots.append(Slot(phase, index, prefix, suffix, column))
            template.append(f"{prefix}\x01{column}\x01{suffix}")
        templates.append(template)
    items = tuple(tuple(c[i].replace(_GLUE, " ") for c in vectors) for i in range(repeats))
    group = Group(
        period=period,
        columns=tuple(columns),
        items=items,
        templates=tuple(tuple(t) for t in templates),
        steps=tuple(steps[: period * repeats]),
    )
    if not columns:
        return None  # identical steps: nothing varies, nothing to list
    # Proof, not trust: only a group that rebuilds every step exactly is kept.
    original = [(s.description, s.display) for s in group.steps]
    if group.expand() != original:
        return None
    return group


def _run_length(steps: Sequence[Renderable], start: int, period: int) -> int:
    """How many whole blocks from *start* repeat the block there."""
    if start + period > len(steps):
        return 0
    block = steps[start : start + period]
    if any(_kind(s) is None for s in block):
        return 0
    tokens = [_tokens(s) for s in block]
    kinds = [_kind(s) for s in block]
    count = 1
    while start + (count + 1) * period <= len(steps):
        ok = True
        for phase in range(period):
            candidate = steps[start + count * period + phase]
            if _kind(candidate) != kinds[phase] or not _compatible(
                tokens[phase], _tokens(candidate)
            ):
                ok = False
                break
        if not ok:
            break
        count += 1
    return count


def group_steps(steps: Sequence[Renderable]) -> list[Renderable | Group]:
    """*steps* with every run of repeated same-shape steps replaced by a group."""
    out: list[Renderable | Group] = []
    i = 0
    while i < len(steps):
        taken = False
        for period in range(1, MAX_PERIOD + 1):
            repeats = _run_length(steps, i, period)
            if repeats >= MIN_REPEATS:
                group = _build(steps[i:], period, repeats)
                if group is not None:
                    out.append(group)
                    i += period * repeats
                    taken = True
                    break
        if not taken:
            out.append(steps[i])
            i += 1
    return out


def _fill(template: Sequence[str], columns: Sequence[str]) -> str:
    text = "".join(
        re.sub(r"\x01(\d+)\x01", lambda m: f"<{columns[int(m.group(1))]}>", t) for t in template
    )
    return text.replace(_GLUE, " ")


def _human(size: float) -> str:
    if size >= 100e6:
        return f"{size / 1e9:.2f} GB"
    if size >= 1e6:
        return f"{size / 1e6:.1f} MB"
    return f"{size / 1e3:.0f} KB"


def _render_group(group: Group, step_count: int) -> list[str]:
    repeats = len(group.items)
    noun = "item"
    lines = [
        f"  Steps {group.steps[0].index}-{group.steps[-1].index} of {step_count}:",
        f"  Repeated {repeats} times, once for each {noun} listed below "
        f"({group.period} step{'s' if group.period != 1 else ''} each, in this order); "
        f"--full prints every one:",
    ]
    for template in group.templates:
        text = _fill(template, group.columns)
        description, _, display = text.partition("\n")
        lines.append(f"  # {description}")
        lines.append(f"  $ {display}")
    lines.append(f"  First {noun} written out in full:")
    for phase in range(group.period):
        step = group.steps[phase]
        lines.append(f"  # {step.index}: {step.description}")
        lines.append(f"  $ {step.display}")
    lines.append(
        f"  The {repeats} items, one per line ({' '.join(f'<{c}>' for c in group.columns)}):"
    )
    for values in group.items:
        lines.append("    " + "  ".join(v.replace(_GLUE, " ") for v in values))
    total = f"  Total: {repeats} {noun}s"
    sizes = group.total_bytes()
    if sizes:
        total += "; " + ", ".join(f"{name} about {_human(v)}" for name, v in sizes.items())
    lines.append(total)
    return lines


def render_steps(steps: Sequence[Renderable], *, full: bool = False) -> list[str]:
    """The Commands body: every step as today, or runs of repeats collapsed."""
    lines: list[str] = []
    items: Sequence[Renderable | Group] = steps if full else group_steps(steps)
    for item in items:
        if isinstance(item, Group):
            lines.extend(_render_group(item, len(steps)))
        else:
            lines.append(f"  # {item.index}: {item.description}")
            lines.append(f"  $ {item.display}")
    return lines
