# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Tuple
from datetime import date
import copy

# --- Code groups ---
N8 = {"N8A", "N8B"}
N4 = {"N4A", "N4B"}
DAY12 = {"DA", "DB"}
DAY8 = {"M8A", "M8B", "E8A", "E8B"}
NIGHT12 = {"NA", "NB"}
NIGHT8 = {"N8A", "N8B"}
NIGHT4 = {"N4A", "N4B"}
VAC = {"VAC8", "VAC0"}


def _tok_for_pair(code: str, d: date) -> str:
    c = (code or "OFF").upper()
    if d.day == 1 and c in NIGHT8:
        return "O"
    if c in DAY12 or c in DAY8:
        return "D"
    if c in NIGHT12 or c in NIGHT4:
        return "N"
    return "O"


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


def _hours_for_code(code: str) -> int:
    c = (code or "").upper()
    if c in DAY12 or c in NIGHT12:
        return 12
    if c in DAY8 or c in NIGHT8:
        return 8
    if c in NIGHT4:
        return 4
    if c == "VAC8":
        return 8
    return 0


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
            val = _hours_for_code(new_c)
            a.effective_hours = val
            new_hours += val
            break

    hours_delta = new_hours - old_hours
    return new_sched, hours_delta, True, f"rot({direction})[{dates[i0]}..{dates[i1]}]:Δh={hours_delta}"


# -------------------- Новые фазовые операторы --------------------


def _day_counts_for(schedule, code_of, d: date) -> Tuple[int, int]:
    da_db = na_nb = 0
    for a in schedule[d]:
        c = code_of(a.shift_key).upper()
        if c in {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}:
            da_db += 1
        if c in {"NA", "NB"}:
            na_nb += 1
    return da_db, na_nb


def _set_off(a) -> None:
    a.shift_key = "off"
    a.effective_hours = 0
    a.source = "phase_shift"


def phase_shift_minus_one_skip(schedule, code_of, emp_id: str, window: Tuple[date, date]):
    new_sched = copy.deepcopy(schedule)
    days = [d for d in sorted(schedule.keys()) if window[0] <= d <= window[1]]
    choices: List[Tuple[str, date]] = []
    for d in days:
        assn = next((x for x in new_sched[d] if x.employee_id == emp_id), None)
        if not assn:
            continue
        code = code_of(assn.shift_key).upper()
        if d.day == 1 and code in N8:
            continue
        if d == max(days) and code in N4:
            continue
        tok = _tok_for_pair(code, d)
        if tok == "D":
            da_db, _ = _day_counts_for(new_sched, code_of, d)
            if da_db >= 3:
                choices.append(("D", d))
        elif tok == "N":
            choices.append(("N", d))
    if not choices:
        return schedule, 0, False, "phase_shift_-1: no safe day"
    choices.sort(key=lambda x: (0 if x[0] == "D" else 1, x[1]))
    _, chosen_day = choices[0]
    for a in new_sched[chosen_day]:
        if a.employee_id == emp_id:
            before = code_of(a.shift_key).upper()
            delta = -_hours_for_code(before)
            _set_off(a)
            return new_sched, delta, True, f"phase_shift_-1[{chosen_day.isoformat()}]"
    return schedule, 0, False, "phase_shift_-1: not found"


def phase_shift_plus_one_insert_off(schedule, code_of, emp_id: str, window: Tuple[date, date]):
    new_sched = copy.deepcopy(schedule)
    days = [d for d in sorted(schedule.keys()) if window[0] <= d <= window[1]]
    tokens: List[Tuple[str, str, date]] = []
    for d in days:
        code = "OFF"
        for a in new_sched[d]:
            if a.employee_id == emp_id:
                code = code_of(a.shift_key).upper()
                break
        tokens.append((_tok_for_pair(code, d), code, d))
    for idx in range(len(tokens) - 2):
        t0, c0, d0 = tokens[idx]
        t1, c1, d1 = tokens[idx + 1]
        t2, c2, d2 = tokens[idx + 2]
        if t0 == "O" and t1 == "O" and t2 in {"D", "N"}:
            if {c0, c1} & VAC:
                continue
            if d2.day == 1 and c2 in N8:
                continue
            if t2 == "D":
                da_db, _ = _day_counts_for(new_sched, code_of, d2)
                if da_db < 3:
                    continue
            for a in new_sched[d2]:
                if a.employee_id == emp_id:
                    before = code_of(a.shift_key).upper()
                    delta = -_hours_for_code(before)
                    _set_off(a)
                    return new_sched, delta, True, f"phase_shift_+1[{d2.isoformat()}]"
    return schedule, 0, False, "phase_shift_+1: no place O,O,(work)"
