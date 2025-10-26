"""Rotation utilities for recurring shift patterns."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Iterator, Sequence


def cycle_days(start: date, count: int) -> Iterator[date]:
    day = start
    for _ in range(count):
        yield day
        day += timedelta(days=1)


def rotate_pattern(pattern: Sequence[str], offset: int) -> Sequence[str]:
    if not pattern:
        return pattern
    offset = offset % len(pattern)
    return tuple(pattern[offset:]) + tuple(pattern[:offset])


def sequence_for_month(start: date, days: int, pattern: Sequence[str], *, shift: int = 0) -> Iterable[tuple[date, str]]:
    rotated = rotate_pattern(pattern, shift)
    pattern_len = len(rotated) or 1
    for idx, day in enumerate(cycle_days(start, days)):
        yield day, rotated[idx % pattern_len]
