# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import date

# schedule: Dict[date, List[Assignment]]
# Assignment: employee_id, shift_key


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
