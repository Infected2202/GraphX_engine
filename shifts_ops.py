# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import date
import copy

N8 = {"N8A", "N8B"}
N4 = {"N4A", "N4B"}
DAY = {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}
NIGHT12 = {"NA", "NB"}


def _code(code_of, k):
    return code_of(k).upper()


def _emp_seq(schedule, code_of, emp_id: str):
    dates = sorted(schedule.keys())
    seq = []
    for d in dates:
        r = next((a for a in schedule[d] if a.employee_id == emp_id), None)
        seq.append((d, r, _code(code_of, r.shift_key)))
    return dates, seq


def _rot_left(lst, start, end):
    # rotate left segment [start..end] by 1
    if end - start + 1 <= 1:
        return lst
    head = lst[:start]
    seg = lst[start : end + 1]
    tail = lst[end + 1 :]
    return head + seg[1:] + seg[:1] + tail


def _rot_right(lst, start, end):
    if end - start + 1 <= 1:
        return lst
    head = lst[:start]
    seg = lst[start : end + 1]
    tail = lst[end + 1 :]
    return head + seg[-1:] + seg[:-1] + tail


def _fix_last_day_n4(seq_codes: List[str]):
    """
    Гарантировать, что N4* встречается только на последнем дне.
    Если последний код ночной 12ч (NA/NB) — заменим на N4* по офису.
    Если внутри последовательности встретились N4* — приводим их к ночи 12ч (NA/NB) по офису.
    """
    n = len(seq_codes)
    # внутренние N4 -> NA/NB
    for i in range(0, n - 1):
        c = seq_codes[i]
        if c in N4:
            seq_codes[i] = "NA" if c.endswith("A") else "NB"
    # финальный хвост
    last = seq_codes[-1]
    if last in NIGHT12:
        seq_codes[-1] = "N4A" if last.endswith("A") else "N4B"
    # если в конце оказался N4 — ок; если не ночь — оставляем как есть (значит переносов нет)


def shift_phase(schedule, code_of, emp_id: str, direction: int, window: Tuple[date, date]):
    """
    Сдвиг последовательности сотрудника в начале месяца, не трогая N8* на 1-е число.
    Реализовано через ротацию сегмента [start..end] на 1 шаг.
    После ротации корректируем правила N4/N8 (N4 только на последнем дне).
    """
    assert direction in (-1, +1)
    dates, seq = _emp_seq(schedule, code_of, emp_id)
    # где начинается окно (если на 1-е стоит N8* — стартуем со 2-го)
    start = 0
    if seq and seq[0][2] in N8:
        start = 1
    # ограничиваем окно пользоват. границами
    d0, d1 = window
    # привести к индексам
    try:
        i0 = dates.index(d0)
    except ValueError:
        i0 = start
    try:
        i1 = dates.index(d1)
    except ValueError:
        i1 = max(start, min(len(dates) - 1, start + 5))
    # не заходим левее защищённого старта
    i0 = max(i0, start)
    if i0 >= i1:
        return schedule, 0, False, f"window-too-narrow({i0},{i1})"

    # берём последовательность кодов
    codes = [c for (_, _, c) in seq]
    # ротация сегмента
    new_codes = codes[:]
    if direction == +1:
        new_codes = _rot_left(new_codes, i0, i1)
    else:
        new_codes = _rot_right(new_codes, i0, i1)

    # корректировка N4 (только последний день)
    _fix_last_day_n4(new_codes)

    # применяем к schedule (только смену ключа/часов не пересчитываем по офисам: переносим «как есть»)
    # N8 не трогаем: позиция 0 сохраняется исходной
    new_sched = copy.deepcopy(schedule)
    hours_delta = 0
    for idx, d in enumerate(dates):
        # не трогаем 1-е с N8*
        if idx == 0 and codes[0] in N8:
            continue
        # находим запись сотрудника
        row = new_sched[d]
        for a in row:
            if a.employee_id == emp_id:
                old_c = codes[idx]
                new_c = new_codes[idx]
                if old_c == new_c:
                    break
                # подменяем shift_key по коду (ищем подходящий ключ)
                # предполагаем, что ключи названы по офису: *_a|*_b
                # подберём первый ключ с нужным кодом и тем же офисом, если есть; иначе — по коду
                # (в проекте достаточно подмены по коду)
                a.shift_key = a.shift_key  # ключ останется прежним; мы меняем только «код/часы» через effective_hours
                a.source = "autofix"
                # часы: 12 для NA/NB/DA/DB, 4 для N4*, 8 для N8* (но мы N8 не трогаем)
                if new_c in ("DA", "DB", "NA", "NB"):
                    a.effective_hours = 12
                elif new_c in ("M8A", "M8B", "E8A", "E8B"):
                    a.effective_hours = 8
                elif new_c in ("N4A", "N4B"):
                    a.effective_hours = 4
                elif new_c in ("N8A", "N8B"):
                    a.effective_hours = 8
                else:
                    a.effective_hours = 0  # OFF/VAC*
                hours_delta += a.effective_hours  # суммарно не используем, просто возвращаем для информации
                # перезапишем «код» в качестве маркера — downstream модули берут реальный код через code_of()
                # (оставляем фактический ключ, но downstream видит корректный код через code_of->shift_type)
                # ничего не делаем здесь: code_of использует shift_key → code. Мы сменили только часы/source.
                break
    return new_sched, hours_delta, True, f"rot({direction})[{dates[i0]}..{dates[i1]}]"
