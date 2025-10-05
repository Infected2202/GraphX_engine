# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import date
import copy
import shifts_ops
import pairing
import coverage as cov


def _window_for_month(dates: List[date], code_of, schedule, emp_id: str, window_days: int) -> Tuple[date, date]:
    """Окно в начале месяца. Если на 1-е у сотрудника N8* — стартуем со 2-го."""
    d0 = dates[0]
    # проверим N8 на 1-е
    row0 = next(a for a in schedule[d0] if a.employee_id == emp_id)
    c0 = code_of(row0.shift_key).upper()
    start_idx = 1 if c0 in {"N8A", "N8B"} and len(dates) > 1 else 0
    i1 = min(len(dates) - 1, start_idx + max(1, window_days) - 1)
    return dates[start_idx], dates[i1]


def _pair_score(pairs) -> int:
    """Сумма overlap_day по всем парам (грубая метрика «склеенности»)."""
    return sum(p[2] for p in pairs)


def apply_pair_breaking(
    schedule,
    employees,
    norm_hours_month: int,
    pairs,
    cfg,
    code_of,
    solo_months_counter: Dict[str, int],
) -> Tuple[object, List[str], List[Tuple[str, int]]]:
    """
    Жадный разрыв пар в начале месяца. Приоритет: сотрудники с «соло»-историей.
    Возвращает: (schedule', ops_log, solo_days_after)
    """
    ops_log: List[str] = []
    if not cfg.get("enabled", False):
        return schedule, ops_log, []

    window_days = int(cfg.get("window_days", 6))
    max_ops = int(cfg.get("max_ops", 4))
    threshold = int(cfg.get("overlap_threshold", 8))

    dates = sorted(schedule.keys())
    # базовые метрики до правок
    base_pairs = pairs
    base_score = _pair_score(base_pairs)
    base_solo = cov.solo_days_by_employee(schedule, code_of)

    # кандидаты: те, кто в «жёстких» парах, плюс «соло»-сотрудники с наибольшей историей
    involved = set()
    for e1, e2, od, on in base_pairs:
        if od >= threshold:
            involved.add(e1)
            involved.add(e2)
    # добавим топ по соло-истории
    top_solo_hist = sorted(solo_months_counter.items(), key=lambda kv: kv[1], reverse=True)
    for eid, _ in top_solo_hist[:4]:
        involved.add(eid)
    # итоговый список кандидатов в детерминированном порядке
    cand = sorted(involved)

    cur_sched = copy.deepcopy(schedule)
    ops = 0
    for eid in cand:
        if ops >= max_ops:
            break
        w0, w1 = _window_for_month(dates, code_of, cur_sched, eid, window_days)
        improved = False
        for direction in (+1, -1):
            test_sched, _, ok, note = shifts_ops.shift_phase(cur_sched, code_of, eid, direction, (w0, w1))
            if not ok:
                continue
            # проверим метрики на окне: стало ли лучше по парам и «соло»
            test_pairs = pairing.compute_pairs(test_sched, code_of)
            test_score = _pair_score(test_pairs)
            test_solo = cov.solo_days_by_employee(test_sched, code_of)
            # критерии приёма:
            # 1) суммарная «склеенность» уменьшилась
            # 2) и (если сотрудник «соло») его соло-дней не стало больше
            cond1 = test_score < base_score
            cond2 = (eid not in base_solo) or (test_solo.get(eid, 0) <= base_solo.get(eid, 0))
            # и базовая целесообразность: в окне появилось 2 дневных (A/B) чаще, а не реже
            if cond1 and cond2:
                cur_sched = test_sched
                base_pairs = test_pairs
                base_score = test_score
                base_solo = test_solo
                ops += 1
                ops_log.append(f"{eid}: {note}")
                improved = True
                break
        if not improved:
            ops_log.append(f"{eid}: skip(no-improve)")

    # финальные соло-метрики
    final_solo = sorted(cov.solo_days_by_employee(cur_sched, code_of).items(), key=lambda kv: kv[0])
    return cur_sched, ops_log, final_solo
