# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import date


def _code_of(code_of_fn, shift_key: str) -> str:
    return code_of_fn(shift_key).upper()


def per_day_counts(schedule, code_of_fn):
    """Возвращает по каждой дате счётчики DA/DB/NA/NB (N4/N8 считаем ночными)."""
    out = {}
    for d, rows in schedule.items():
        c = {"DA": 0, "DB": 0, "NA": 0, "NB": 0}
        for a in rows:
            c0 = _code_of(code_of_fn, a.shift_key)
            if c0 == "DA":
                c["DA"] += 1
            elif c0 == "DB":
                c["DB"] += 1
            elif c0 in {"NA", "N4A", "N8A"}:
                c["NA"] += 1
            elif c0 in {"NB", "N4B", "N8B"}:
                c["NB"] += 1
        out[d] = c
    return out


def solo_days_by_employee(schedule, code_of_fn):
    """
    Список "соло-дней" по сотрудникам: когда (DA+DB)==1 и этот единственный D принадлежит сотруднику.
    Возвращает dict[emp_id] -> int (кол-во соло-дней).
    """
    out: Dict[str, int] = {}
    for d, rows in schedule.items():
        # ищем единственный D
        day_workers: List[str] = []
        for a in rows:
            c0 = _code_of(code_of_fn, a.shift_key)
            if c0 in ("DA", "DB", "M8A", "M8B", "E8A", "E8B"):
                day_workers.append(a.employee_id)
        if len(day_workers) == 1:
            eid = day_workers[0]
            out[eid] = out.get(eid, 0) + 1
    return out
