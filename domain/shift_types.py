"""Canonical shift type helpers for GraphX."""
from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, Optional, Set

__all__ = [
    "DAY12",
    "DAY8",
    "NIGHT12",
    "NIGHT8",
    "NIGHT4",
    "VACATION_CODES",
    "OFF_CODE",
    "ALL_CODES",
    "code_to_token",
    "hours_for_code",
    "office_for_code",
]


DAY12: Set[str] = {"DA", "DB"}
DAY8: Set[str] = {"M8A", "M8B", "E8A", "E8B"}
NIGHT12: Set[str] = {"NA", "NB"}
NIGHT8: Set[str] = {"N8A", "N8B"}
NIGHT4: Set[str] = {"N4A", "N4B"}
VACATION_CODES: Set[str] = {"VAC8", "VAC0"}
OFF_CODE = "OFF"

_ALL_HOURS: Dict[str, int] = {
    **{code: 12 for code in DAY12 | NIGHT12},
    **{code: 8 for code in DAY8 | NIGHT8},
    **{code: 4 for code in NIGHT4},
    "VAC8": 8,
    "VAC0": 0,
    OFF_CODE: 0,
}

ALL_CODES: Set[str] = set(_ALL_HOURS.keys())


def _normalize(code: Optional[str]) -> str:
    return (code or OFF_CODE).upper()


def code_to_token(code: Optional[str], day: Optional[date] = None) -> str:
    """Return the high level token (D/N/O) for a shift *code*.

    Night short codes (N8*) on the first day of the month count as OFF so that
    pair metrics treat them as carry-overs. The behaviour mirrors the legacy
    implementation that lived in several modules.
    """

    normalized = _normalize(code)
    if day and day.day == 1 and normalized in NIGHT8:
        return "O"
    if normalized in DAY12 or normalized in DAY8:
        return "D"
    if normalized in NIGHT12 or normalized in NIGHT4 or normalized in NIGHT8:
        return "N"
    return "O"


def hours_for_code(code: Optional[str]) -> int:
    """Return scheduled hours for a shift *code*. Unknown codes default to 0."""

    return _ALL_HOURS.get(_normalize(code), 0)


def office_for_code(code: Optional[str]) -> Optional[str]:
    """Infer office suffix (``A``/``B``) from a code."""

    normalized = _normalize(code)
    if normalized in VACATION_CODES or normalized == OFF_CODE:
        return None
    if normalized.endswith("A"):
        return "A"
    if normalized.endswith("B"):
        return "B"
    return None


def is_working_code(code: Optional[str]) -> bool:
    normalized = _normalize(code)
    return normalized not in VACATION_CODES and normalized != OFF_CODE


def iter_working_codes() -> Iterable[str]:
    return (code for code in ALL_CODES if is_working_code(code))
