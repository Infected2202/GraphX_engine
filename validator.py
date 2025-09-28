# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List
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
    c = (code or "").upper()
    if c in {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}:
        return "D"
    if c in {"NA", "NB", "N4A", "N4B", "N8A", "N8B"}:
        return "N"
    return "O"  # OFF/VAC*


def _office(code: str) -> str | None:
    c = (code or "").upper()
    if c.endswith("A"):
        return "A"
    if c.endswith("B"):
        return "B"
    return None


def validate_baseline(ym: str, employees: List, schedule: Dict[date, List]) -> List[str]:
    issues: List[str] = []
    dates = sorted(schedule.keys())
    name_of = {e.id: e.name for e in employees}

    # 1) Ровно одна запись на сотрудника в сутки
    for d in dates:
        seen = {}
        for a in schedule[d]:
            if a.employee_id in seen:
                issues.append(f"{ym} {d}: дубль назначения для {name_of[a.employee_id]}")
            seen[a.employee_id] = True

    # 2) Локальная проверка переходов цикла D→N→O→O (N4/N8 считаем как N).
    #    Это устойчиво к «старту» на любом месте цикла и к N8 на 1-е число.
    for e in employees:
        toks = []
        codes = []
        for d in dates:
            a = next(r for r in schedule[d] if r.employee_id == e.id)
            c = _code_of(a.shift_key)
            codes.append(c)
            toks.append(_tok(c))

        # проверяем локальные переходы (без глобального выравнивания)
        def next_expected(prev_t: str, off_seen: int) -> str:
            # off_seen: 0 — ни одного O подряд; 1 — один O был
            if prev_t == "D":
                return "N"
            if prev_t == "N":
                return "O"
            if prev_t == "O":
                return "O" if off_seen == 0 else "D"
            return "D"

        off_seen = 0
        prev_t = toks[0]
        # допускаем любой стартовый токен, в т.ч. N (например, N8 на 1-е число)
        if prev_t == "O":
            off_seen = 1
        for i in range(1, len(toks)):
            exp = next_expected(prev_t, off_seen)
            t = toks[i]
            if t != exp:
                issues.append(
                    f"{ym}: {name_of[e.id]} — нарушен цикл на дате {dates[i]} (ожидалось {exp}, есть {t})"
                )
                break
            # обновляем состояние
            if t == "O":
                off_seen = min(1, off_seen + 1)
            else:
                off_seen = 0
            prev_t = t

        # 3) Офисы: дневной офис чередуется A/B, ночь — противоположна дневной в том же цикле.
        day_offices = []
        night_offices = []
        for i, (d, code, t) in enumerate(zip(dates, codes, toks)):
            if t == "D":
                day_offices.append(_office(code))
            elif t == "N":
                night_offices.append(_office(code))
        # проверка чередования day A/B
        for i in range(1, len(day_offices)):
            if day_offices[i] == day_offices[i - 1] and day_offices[i] is not None:
                issues.append(f"{ym}: {name_of[e.id]} — дневные офисы не чередуются около цикла #{i}")
                break
        # проверка «ночь ↔ противоположный офис» — по локальным парам (ищем D затем ближайший N)
        day_off = None
        for d, code, t in zip(dates, codes, toks):
            if t == "D":
                day_off = _office(code)
            elif t == "N" and day_off is not None:
                n_off = _office(code)
                if n_off == day_off:
                    issues.append(f"{ym}: {name_of[e.id]} — ночь не противоположна дневной (дата {d})")
                day_off = None
    return issues
