# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple, Set
from datetime import date

# schedule: Dict[date, List[Assignment]]
# Assignment: employee_id, shift_key
# compute_pairs(schedule, code_of) — уже существует и возвращает [(e1,e2,day_ov,night_ov), ...]


def _tok(code: str) -> str:
    c = (code or "").upper()
    if c in {"DA","DB","M8A","M8B","E8A","E8B"}: return "D"
    if c in {"NA","NB","N4A","N4B","N8A","N8B"}: return "N"
    return "O"


def compute_pairs(schedule: Dict[date, List], code_of) -> List[Tuple[str,str,int,int]]:
    """Возвращает список (emp1, emp2, overlap_day, overlap_night)."""
    # Соберём список сотрудников
    emp_ids = set()
    for rows in schedule.values():
        for a in rows:
            emp_ids.add(a.employee_id)
    emp_ids = sorted(emp_ids)
    idx = {e:i for i,e in enumerate(emp_ids)}
    n = len(emp_ids)
    od = [[0]*n for _ in range(n)]
    on = [[0]*n for _ in range(n)]

    for d, rows in schedule.items():
        toks = ["O"] * n
        for a in rows:
            code = code_of(a.shift_key)
            toks[idx[a.employee_id]] = _tok(code)
        # инкремент по парам
        for i in range(n):
            for j in range(i+1, n):
                if toks[i] == "D" and toks[j] == "D":
                    od[i][j] += 1
                elif toks[i] == "N" and toks[j] == "N":
                    on[i][j] += 1
    out: List[Tuple[str,str,int,int]] = []
    for i in range(n):
        for j in range(i+1, n):
            out.append((emp_ids[i], emp_ids[j], od[i][j], on[i][j]))
    # сортируем по overlap_day убыв., затем по overlap_night
    out.sort(key=lambda t: (t[2], t[3]), reverse=True)
    return out


def exclusive_matching_by_day(
    pairs: List[Tuple[str, str, int, int]],
    threshold_day: int = 0,
) -> List[Tuple[str, str, int, int]]:
    """
    Жадный эксклюзивный matching: выбираем непересекающиеся пары по дневным пересечениям.
    """

    cand = [p for p in pairs if p[2] >= threshold_day]
    cand.sort(key=lambda x: (x[2], x[3]), reverse=True)
    used: Set[str] = set()
    res: List[Tuple[str, str, int, int]] = []
    for e1, e2, d, n in cand:
        if e1 in used or e2 in used:
            continue
        used.add(e1)
        used.add(e2)
        res.append((e1, e2, d, n))
    return res

# -------------------- Новое: часовая метрика пар --------------------

DAY12 = {"DA", "DB"}
DAY8 = {"M8A", "M8B", "E8A", "E8B"}
NIGHT12 = {"NA", "NB"}
NIGHT8 = {"N8A", "N8B"}
NIGHT4 = {"N4A", "N4B"}
VAC = {"VAC8", "VAC0"}


def _tok_for_pair(code: str, d: date) -> str:
    """Вернуть токен пары (D/N/O), учитывая, что N8 на 1-е считаем OFF."""

    c = (code or "OFF").upper()
    if d.day == 1 and c in NIGHT8:
        return "O"
    if c in DAY12 or c in DAY8:
        return "D"
    if c in NIGHT12 or c in NIGHT4:
        return "N"
    return "O"


def _hours_of(code: str) -> int:
    c = (code or "OFF").upper()
    if c in DAY12 or c in NIGHT12:
        return 12
    if c in DAY8 or c in NIGHT8:
        return 8
    if c in NIGHT4:
        return 4
    if c == "VAC8":
        return 8
    return 0


def pair_hours_for_pair(schedule, code_of, a: str, b: str) -> Tuple[int, int, int]:
    """Возвращает (hours_day, hours_night, hours_total) совпадений пары a~b."""

    hours_d = hours_n = 0
    for d in sorted(schedule.keys()):
        code_a = code_b = "OFF"
        found_a = found_b = False
        for row in schedule[d]:
            if not found_a and row.employee_id == a:
                code_a = code_of(row.shift_key).upper()
                found_a = True
            elif not found_b and row.employee_id == b:
                code_b = code_of(row.shift_key).upper()
                found_b = True
            if found_a and found_b:
                break
        tok_a = _tok_for_pair(code_a, d)
        tok_b = _tok_for_pair(code_b, d)
        if tok_a == "D" and tok_b == "D":
            hours_d += min(_hours_of(code_a), _hours_of(code_b))
        elif tok_a == "N" and tok_b == "N":
            hours_n += min(_hours_of(code_a), _hours_of(code_b))
    return hours_d, hours_n, hours_d + hours_n


def pair_hours_exclusive(
    schedule,
    code_of,
    prev_pairs: List[Tuple[str, str, int, int]] | None,
    threshold_day: int = 0,
) -> List[Tuple[str, str, int, int, int]]:
    """Эксклюзивные пары прошлого месяца и их часы совпадений в текущем месяце."""

    prev_excl = exclusive_matching_by_day(prev_pairs or [], threshold_day=threshold_day)
    out: List[Tuple[str, str, int, int, int]] = []
    for e1, e2, _, _ in prev_excl:
        h_day, h_night, h_total = pair_hours_for_pair(schedule, code_of, e1, e2)
        out.append((e1, e2, h_day, h_night, h_total))
    out.sort(key=lambda x: (x[4], x[2], x[3]), reverse=True)
    return out
