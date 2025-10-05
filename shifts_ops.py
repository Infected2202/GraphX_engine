# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Tuple
from datetime import date
import copy

# --- Code groups ---
N8 = {"N8A", "N8B"}
N4 = {"N4A", "N4B"}
DAY = {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}
NIGHT12 = {"NA", "NB"}
NIGHT_ANY = {"NA", "NB", "N4A", "N4B", "N8A", "N8B"}


def _code(code_of, k):
    return code_of(k).upper()


def _emp_seq(schedule, code_of, emp_id: str) -> Tuple[List[date], List[Tuple[date, str, str]]]:
    """Возвращает (dates, seq[(date, shift_key, CODE)]) только для нужного сотрудника."""
    dates: List[date] = []
    seq: List[Tuple[date, str, str]] = []
    for d in sorted(schedule.keys()):
        for a in schedule[d]:
            if a.employee_id != emp_id:
                continue
            c = _code(code_of, a.shift_key)
            dates.append(d)
            seq.append((d, a.shift_key, c))
            break
    return dates, seq


def _fix_last_day_n4(codes: List[str]) -> None:
    if not codes:
        return
    last = codes[-1]
    if last in {"NA", "NB"}:
        codes[-1] = "N4A" if last.endswith("A") else "N4B"


def _tok_from_code(c: str) -> str:
    c = (c or "").upper()
    if c in DAY:
        return "D"
    if c in NIGHT_ANY:
        return "N"
    return "O"


def _with_office(code: str, office: str | None) -> str:
    c = (code or "").upper()
    if office not in {"A", "B"}:
        return c
    if c.endswith(("A", "B")):
        return c[:-1] + office
    return c


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


def shift_phase(schedule, code_of, emp_id: str, direction: int, window: Tuple[date, date]):
    """Сдвиг фаз без ломки паттерна: переставляем офисы, но сохраняем тип смены."""

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
    toks = [_tok_from_code(c) for c in codes]
    work_idx = [k for k in range(len(dates)) if i0 <= k <= i1 and toks[k] in {"D", "N"}]
    if work_idx and codes[0] in N8 and work_idx[0] == 0:
        work_idx = work_idx[1:]
    if len(work_idx) <= 1:
        return schedule, 0, False, f"window-too-narrow({i0},{i1})"

    offices = [codes[k][-1] if codes[k].endswith(("A", "B")) else None for k in work_idx]
    if direction == +1:
        new_offices = offices[1:] + offices[:1]
    else:
        new_offices = offices[-1:] + offices[:-1]

    new_codes = codes[:]
    for pos, k in enumerate(work_idx):
        new_codes[k] = _with_office(new_codes[k], new_offices[pos])

    _fix_last_day_n4(new_codes)

    new_sched = copy.deepcopy(schedule)
    old_hours = 0
    new_hours = 0
    for idx, d in enumerate(dates):
        if idx == 0 and codes[0] in N8:
            continue
        old_c = codes[idx]
        new_c = new_codes[idx]
        if old_c == new_c:
            continue
        for a in new_sched[d]:
            if a.employee_id != emp_id:
                continue
            orig_hours = int(getattr(a, "effective_hours", 0))
            old_hours += orig_hours
            a.shift_key = _key_for_code(new_c)
            a.source = "autofix"
            if new_c in {"DA", "DB", "NA", "NB"}:
                new_val = 12
            elif new_c in {"M8A", "M8B", "E8A", "E8B", "N8A", "N8B"}:
                new_val = 8
            elif new_c in {"N4A", "N4B"}:
                new_val = 4
            else:
                new_val = 0
            a.effective_hours = new_val
            new_hours += new_val
            break

    hours_delta = new_hours - old_hours
    return new_sched, hours_delta, True, f"ab-rot({direction})[{dates[i0]}..{dates[i1]}]"
