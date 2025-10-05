# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import date

# Ожидаем интерфейс schedule: Dict[date, List[Assignment]]
# Assignment: employee_id, shift_key, effective_hours, source

def _code_of(shift_key: str) -> str:
    sk = (shift_key or "").lower()
    return {
        "day_a": "DA",
        "day_b": "DB",
        "night_a": "NA",
        "night_b": "NB",
        "m8_a": "M8A",
        "m8_b": "M8B",
        "e8_a": "E8A",
        "e8_b": "E8B",
        "n4_a": "N4A",
        "n4_b": "N4B",
        "n8_a": "N8A",
        "n8_b": "N8B",
        "vac_wd8": "VAC8",
        "vac_we0": "VAC0",
        "off": "OFF",
    }.get(sk, sk.upper())


def _tok(code: str) -> str:
    """D/N/O-токен для baseline-проверки. N4/N8 → N, VAC → O."""
    c = (code or "").upper()
    if c in {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}:
        return "D"
    if c in {"NA", "NB", "N4A", "N4B", "N8A", "N8B"}:
        return "N"
    # OFF, VAC8, VAC0 и прочее — считаем «вне цикла» (O)
    return "O"


def _office(code: str) -> str | None:
    c = (code or "").upper()
    if c.endswith("A"):
        return "A"
    if c.endswith("B"):
        return "B"
    return None


def validate_baseline(
    ym: str,
    employees,
    schedule: Dict[date, List],
    code_of,
    gen,
    ignore_vacations: bool = True,
) -> List[str]:
    """
    Базовая проверка паттерна, «якорь» = 1-е число месяца.
    N4/N8 считаем ночными. VAC считаем O (или игнорируем, если ignore_vacations=True).
    """
    issues: List[str] = []
    dates = sorted(schedule.keys())
    if not dates:
        return issues
    d0 = dates[0]
    epoch = gen.rotation_epoch_for(d0.year)

    actual: Dict[Tuple[date, str], str] = {}
    for d in dates:
        for a in schedule[d]:
            actual[(d, a.employee_id)] = code_of(a.shift_key).upper()

    for e in employees:
        for d in dates:
            ph = gen.phase_for_day(e.seed4, (d - epoch).days)
            exp = "D" if ph == 0 else ("N" if ph == 1 else "O")
            code = actual.get((d, e.id), "OFF")
            act = _tok(code)
            if ignore_vacations and code in {"VAC8", "VAC0"}:
                continue
            if act != exp:
                issues.append(
                    f"{ym}: Сотрудник {e.id} — нарушен цикл на дате {d.isoformat()} (ожидалось {exp}, есть {act})"
                )
    return issues

# Доп. «мягкая» проверка/лог по первым дням месяца (smoke): DA/DB/A/B-сплит
def coverage_smoke(ym, schedule, code_of, first_days: int = 8):
    """Сводка по первым дням месяца с учётом N4/N8 как ночных."""
    dates = sorted(schedule.keys())[:first_days]
    rows = []
    for d in dates:
        da = db = na = nb = 0
        for a in schedule[d]:
            c = code_of(a.shift_key).upper()
            if c == "DA":
                da += 1
            elif c == "DB":
                db += 1
            elif c in {"NA", "N4A", "N8A"}:
                na += 1
            elif c in {"NB", "N4B", "N8B"}:
                nb += 1
        rows.append((d.isoformat(), da, db, na, nb))
    return rows


def phase_trace(ym, employees, schedule, code_of, gen, days: int = 10):
    dates = sorted(schedule.keys())[:days]
    if not dates:
        return []
    d0 = dates[0]
    epoch = gen.rotation_epoch_for(d0.year)
    out = []
    for e in employees:
        exp = []
        act = []
        for d in dates:
            ph = gen.phase_for_day(e.seed4, (d - epoch).days)
            exp.append("D" if ph == 0 else ("N" if ph == 1 else "O"))
            code = None
            for a in schedule[d]:
                if a.employee_id == e.id:
                    code = code_of(a.shift_key).upper()
                    break
            act.append(_tok(code or "OFF"))
        out.append(f"{e.id}: exp={' '.join(exp)} | act={' '.join(act)}")
    return out
