"""Affirmative consent gates.  D-021."""

from .gate import (
    ConsentDeclined,
    ConsentRecord,
    ConsentUnavailable,
    Decision,
    render_disclosure,
    resolve_consent,
)

__all__ = [
    "ConsentDeclined",
    "ConsentRecord",
    "ConsentUnavailable",
    "Decision",
    "render_disclosure",
    "resolve_consent",
]
