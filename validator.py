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
    gen = None,
    ignore_vacations: bool = True,
) -> List[str]:
    """
    Базовая проверка паттерна с «якорем» = 1-е число текущего месяца.
    Используем фактический токен на 1-е (с учётом N4/N8→N, VAC→O) как старт цикла D→N→O→O.
    Это учитывает carry-in и переносы.
    """
    issues: List[str] = []
    dates = sorted(schedule.keys())
    if not dates:
        return issues
    d0 = dates[0]

    actual_tok: Dict[Tuple[date, str], str] = {}
    actual_code: Dict[Tuple[date, str], str] = {}
    for d in dates:
        for a in schedule[d]:
            code = code_of(a.shift_key).upper()
            actual_code[(d, a.employee_id)] = code
            actual_tok[(d, a.employee_id)] = _tok(code)

    cycle = ["D", "N", "O", "O"]  # 0,1,2,3
    idx_of = {"D": 0, "N": 1, "O": 2}  # NB: O может быть и 2, и 3 — разрулим ниже

    def _choose_start(eid: str) -> int:
        """Выбрать стартовый индекс цикла для сотрудника на 1-е число."""
        base_tok = actual_tok.get((d0, eid), "O")
        if base_tok != "O":
            return idx_of.get(base_tok, 2)
        # base_tok == "O": ориентируемся на второй день
        if len(dates) >= 2:
            d1 = dates[1]
            next_tok = actual_tok.get((d1, eid), "O")
            if next_tok == "O":
                return 2  # O -> O … первый OFF
            if next_tok == "D":
                return 3  # O -> D … второй OFF
        # fallback: выберем старт из {2,3} с минимальным числом несовпадений за месяц
        best_start, best_mis = 2, 10 ** 9
        for s in (2, 3):
            mis = 0
            for i, d in enumerate(dates):
                exp = cycle[(s + i) % 4]
                code = actual_code.get((d, eid), "OFF")
                act = actual_tok.get((d, eid), "O")
                if ignore_vacations and code in {"VAC8", "VAC0"}:
                    continue
                if act != exp:
                    mis += 1
            if mis < best_mis:
                best_start, best_mis = s, mis
        return best_start

    for e in employees:
        start = _choose_start(e.id)
        for i, d in enumerate(dates):
            exp = cycle[(start + i) % 4]
            code = actual_code.get((d, e.id), "OFF")
            act = actual_tok.get((d, e.id), "O")
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


def phase_trace(ym, employees, schedule, code_of, gen = None, days: int = 10):
    dates = sorted(schedule.keys())[:days]
    if not dates:
        return []
    cycle = ["D", "N", "O", "O"]
    idx_of = {"D": 0, "N": 1, "O": 2}
    out = []
    for e in employees:
        act = []
        for d in dates:
            code = None
            for a in schedule[d]:
                if a.employee_id == e.id:
                    code = code_of(a.shift_key).upper()
                    break
            act.append(_tok(code or "OFF"))
        if not act:
            start = 2
        elif act[0] != "O":
            start = idx_of.get(act[0], 2)
        else:
            if len(act) >= 2 and act[1] == "D":
                start = 3
            elif len(act) >= 2 and act[1] == "O":
                start = 2
            else:
                cand = [
                    (2, sum(1 for i, t in enumerate(act) if t != cycle[(2 + i) % 4])),
                    (3, sum(1 for i, t in enumerate(act) if t != cycle[(3 + i) % 4])),
                ]
                start = min(cand, key=lambda x: x[1])[0]
        exp = [cycle[(start + i) % 4] for i in range(len(dates))]
        out.append(f"{e.id}: exp={' '.join(exp)} | act={' '.join(act)}")
    return out
