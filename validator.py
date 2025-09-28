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

    # 2) Проверка цикла D→N→O→O по токенам (с N4/N8 как N)
    #    Восстанавливаем фазу из первого дня как-то просто: подгоняем сдвиг по месту.
    for e in employees:
        toks = []
        codes = []
        for d in dates:
            a = next(r for r in schedule[d] if r.employee_id == e.id)
            code = _code_of(a.shift_key)
            codes.append(code)
            toks.append(_tok(code))
        # ищем такой сдвиг s∈[0..3], чтобы максимизировать совпадения с шаблоном D,N,O,O
        target = ["D", "N", "O", "O"]
        best_s, best_match = 0, -1
        for s in range(4):
            m = sum(1 for i, t in enumerate(toks) if t == target[(i + s) % 4])
            if m > best_match:
                best_match, best_s = m, s
        # теперь проверим полное соответствие
        for i, t in enumerate(toks):
            exp = target[(i + best_s) % 4]
            if t != exp:
                issues.append(
                    f"{ym}: {name_of[e.id]} — нарушен цикл на дате {dates[i]} (ожидалось {exp}, есть {t})"
                )
                break

        # 3) Офисы: дневной офис должен чередоваться по циклам, ночной — противоположный дневному в том же цикле
        #    Восстановим «следующая дневная A/B» из первых дневных.
        #    Берём первую дневную как точку отсчёта: следующая дневная должна быть в другом офисе и т.д.
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
        # пара день/ночь в одном цикле: соберём по окнам из 4 дней
        # сдвиг по лучшему s
        cyc = 0
        day_off = None
        for i, (d, code, t) in enumerate(zip(dates, codes, toks)):
            pos = (i + best_s) % 4
            if pos == 0 and t == "D":
                day_off = _office(code)
            if pos == 1 and t == "N" and day_off is not None:
                n_off = _office(code)
                if n_off == day_off:
                    issues.append(
                        f"{ym}: {name_of[e.id]} — ночь не противоположна дневной (цикл {cyc}, дата {d})"
                    )
                cyc += 1
                day_off = None
    return issues
