# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Tuple
from datetime import date
import copy

# --- Code groups ---
N8 = {"N8A", "N8B"}
N4 = {"N4A", "N4B"}
DAY = {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}


def _code(code_of, k):
    return code_of(k).upper()


def _emp_seq(schedule, code_of, emp_id: str) -> Tuple[List[date], List[Tuple[date, object, str]]]:
    """Возвращает (dates, seq[(date, assignment, CODE)]) только для нужного сотрудника."""
    dates: List[date] = []
    seq: List[Tuple[date, object, str]] = []
    for d in sorted(schedule.keys()):
        for a in schedule[d]:
            if a.employee_id != emp_id:
                continue
            c = _code(code_of, a.shift_key)
            dates.append(d)
            seq.append((d, a, c))
            break
    return dates, seq


def _fix_last_day_n4(codes: List[str]) -> None:
    if not codes:
        return
    last = codes[-1]
    if last in {"NA", "NB"}:
        codes[-1] = "N4A" if last.endswith("A") else "N4B"


def _key_for_code(code: str) -> str:
    c = (code or "").upper()
    return {
        "DA": "day_a",
        "DB": "day_b",
        "NA": "night_a",
        "NB": "night_b",
        "M8A": "m8_a",
        "M8B": "m8_b",
        "E8A": "e8_a",
        "E8B": "e8_b",
        "N4A": "n4_a",
        "N4B": "n4_b",
        "N8A": "n8_a",
        "N8B": "n8_b",
        "VAC8": "vac_wd8",
        "VAC0": "vac_we0",
        "OFF": "off",
    }.get(c, "off")


def _rot(codes: List[str], i0: int, i1: int, direction: int) -> List[str]:
    new_codes = codes[:]
    if direction == +1:
        head = new_codes[i0]
        new_codes[i0:i1] = new_codes[i0 + 1 : i1 + 1]
        new_codes[i1] = head
    else:
        tail = new_codes[i1]
        new_codes[i0 + 1 : i1 + 1] = new_codes[i0:i1]
        new_codes[i0] = tail
    return new_codes


def shift_phase(schedule, code_of, emp_id: str, direction: int, window: Tuple[date, date]):
    """
    Сдвиг окна в начале месяца на ±1 с реальным обновлением shift_key.
    Запреты:
     - не трогаем N8* на 1-е,
     - не создаём N8 внутри месяца,
     - не создаём N4 вне последнего дня месяца.
    """

    assert direction in (-1, +1)
    dates, seq = _emp_seq(schedule, code_of, emp_id)
    if not seq:
        return schedule, 0, False, "no-rows"

    start = 0
    if seq and seq[0][2] in N8:
        start = 1

    d0, d1 = window
    n = len(dates)
    if start >= n:
        return schedule, 0, False, "window-empty"

    try:
        i0 = dates.index(d0)
    except ValueError:
        i0 = start
    try:
        i1 = dates.index(d1)
    except ValueError:
        i1 = max(start, min(n - 1, start + 5))
    i0 = max(i0, start)
    i1 = max(i1, start)
    i0 = min(i0, n - 1)
    i1 = min(i1, n - 1)
    if i0 >= i1:
        return schedule, 0, False, f"window-too-narrow({i0},{i1})"

    codes = [c for (_, _, c) in seq]
    new_codes = _rot(codes, i0, i1, direction)

    for k in range(i0, i1 + 1):
        if new_codes[k] in N8 and k != 0:
            new_codes[k] = "NA" if new_codes[k].endswith("A") else "NB"

    _fix_last_day_n4(new_codes)

    new_sched = copy.deepcopy(schedule)
    new_hours = 0
    old_hours = 0
    for idx, d in enumerate(dates):
        if idx == 0 and codes[0] in N8:
            continue
        old_c = codes[idx]
        new_c = new_codes[idx]
        if old_c == new_c:
            continue
        _, orig_assn, _ = seq[idx]
        if orig_assn and orig_assn.employee_id == emp_id:
            old_hours += int(getattr(orig_assn, "effective_hours", 0))
        for a in new_sched[d]:
            if a.employee_id != emp_id:
                continue
            a.shift_key = _key_for_code(new_c)
            a.source = "autofix"
            if new_c in {"DA", "DB", "NA", "NB"}:
                val = 12
            elif new_c in {"M8A", "M8B", "E8A", "E8B", "N8A", "N8B"}:
                val = 8
            elif new_c in {"N4A", "N4B"}:
                val = 4
            else:
                val = 0
            a.effective_hours = val
            new_hours += val
            break

    hours_delta = new_hours - old_hours
    return new_sched, hours_delta, True, f"rot({direction})[{dates[i0]}..{dates[i1]}]:Δh={hours_delta}"
