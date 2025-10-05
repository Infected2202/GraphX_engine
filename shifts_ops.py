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

# Reverse map: code -> shift_key used in generator/config
CODE_TO_KEY = {
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
}


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


def _rotate_slice(codes: List[str], i0: int, i1: int, direction: int) -> List[str]:
    new_codes = codes[:]
    if direction == +1:
        # right-rotate на 1 в пределах [i0..i1]
        tail = codes[i1]
        new_codes[i0 + 1 : i1 + 1] = codes[i0:i1]
        new_codes[i0] = tail
    else:
        # left-rotate на 1 в пределах [i0..i1]
        head = codes[i0]
        new_codes[i0:i1] = codes[i0 + 1 : i1 + 1]
        new_codes[i1] = head
    return new_codes


def shift_phase(schedule, code_of, emp_id: str, direction: int, window: Tuple[date, date]):
    """Сдвиг фаз сотрудника в начале месяца с реальной перезаписью shift_key в окне.
    Инварианты:
      - N8* на 1-е число не трогаем;
      - не создаём N8 внутри месяца;
      - две записи сотруднику в один день не допускаются.
    Возвращает: (schedule', delta_hours, ok, note)
    """

    assert direction in (-1, +1)
    dates, seq = _emp_seq(schedule, code_of, emp_id)
    if not seq:
        return schedule, 0, False, "no-rows"

    # защитный старт: если на 1-е у сотрудника N8* — окно со 2-го
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
    old_hours = 0
    for k in range(i0, i1 + 1):
        d, _, _ = seq[k]
        for a in schedule[d]:
            if a.employee_id == emp_id:
                old_hours += int(getattr(a, "effective_hours", 0))
                break

    new_codes = _rotate_slice(codes, i0, i1, direction)
    for k in range(i0, i1 + 1):
        if new_codes[k] in N8 and k != 0:
            new_codes[k] = "NA" if new_codes[k].endswith("A") else "NB"

    new_sched = copy.deepcopy(schedule)
    new_hours = 0
    for k in range(i0, i1 + 1):
        d, _, _ = seq[k]
        new_c = new_codes[k]
        new_key = CODE_TO_KEY.get(new_c)
        if new_key is None:
            if new_c in ("OFF", "VAC8", "VAC0"):
                new_key = CODE_TO_KEY.get(new_c)
            else:
                return schedule, 0, False, f"unknown-code({new_c})"
        for a in new_sched[d]:
            if a.employee_id != emp_id:
                continue
            orig_hours = int(getattr(a, "effective_hours", 0))
            if k == 0 and codes[0] in N8:
                new_hours += orig_hours
                break
            a.shift_key = new_key
            if new_c in ("DA", "DB", "NA", "NB"):
                a.effective_hours = 12
            elif new_c in ("M8A", "M8B", "E8A", "E8B"):
                a.effective_hours = 8
            elif new_c in ("N4A", "N4B"):
                a.effective_hours = 4
            elif new_c in ("N8A", "N8B"):
                a.effective_hours = 8
            elif new_c == "VAC8":
                a.effective_hours = 8
            else:
                a.effective_hours = 0
            a.source = a.source if a.source != "template" else "autofix"
            new_hours += int(getattr(a, "effective_hours", 0))
            break

    hours_delta = new_hours - old_hours
    return new_sched, hours_delta, True, f"rot({direction})[{dates[i0]}..{dates[i1]}]:Δh={hours_delta}"
