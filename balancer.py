# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import date
import copy
import shifts_ops
import pairing
import coverage as cov


def _fmt_tape(schedule, code_of, eid: str, w0: date, w1: date) -> str:
    """Лента по окну дат с токенами и отметкой carry-in N8."""

    days = [d for d in sorted(schedule.keys()) if w0 <= d <= w1]
    tape: List[str] = []
    for d in days:
        code = "OFF"
        for a in schedule[d]:
            if a.employee_id == eid:
                code = code_of(a.shift_key).upper()
                break
        tok = "O"
        if code in {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}:
            tok = f"D({code[-1]})"
        elif code in {"NA", "NB", "N4A", "N4B"}:
            tok = f"N({code[-1]})"
        elif code in {"N8A", "N8B"}:
            tok = "N8(OFF)" if d.day == 1 else "N8"
        tape.append(f"{d.day:02d} {tok}")
    return ", ".join(tape)


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


def _slice_schedule(schedule, w0: date, w1: date):
    """Срез расписания на окно дат [w0..w1]."""
    return {d: rows[:] for d, rows in schedule.items() if w0 <= d <= w1}


def _coverage_ok_in_window(schedule, code_of, w0: date, w1: date) -> int:
    """Число дат в окне, где DA+DB ≥ 2 (M8/E8 считаем дневными)."""
    cnt = 0
    for d, rows in schedule.items():
        if not (w0 <= d <= w1):
            continue
        da = db = 0
        for a in rows:
            c = code_of(a.shift_key).upper()
            if c in ("DA", "M8A", "E8A"):
                da += 1
            if c in ("DB", "M8B", "E8B"):
                db += 1
        if (da + db) >= 2:
            cnt += 1
    return cnt


def apply_pair_breaking(
    schedule,
    employees,
    norm_hours_month: int,
    pairs,
    cfg,
    code_of,
    solo_months_counter: Dict[str, int],
) -> Tuple[object, List[str], List[Tuple[str, int]], int, int, List[str]]:
    """
    Жадный разрыв пар в начале месяца. Приём операции строгий: Δpair < 0, Δsolo ≤ 0 (и в окне),
    Δcoverage_ok ≥ 0, |Δhours| ≤ hours_budget.

    Возвращает расписание после правок, лог операций, финальные соло-метрики и pair_score до/после.
    """
    ops_log: List[str] = []
    apply_log: List[str] = []
    entry_score = _pair_score(pairs)
    if not cfg.get("enabled", False):
        final_solo = sorted(cov.solo_days_by_employee(schedule, code_of).items(), key=lambda kv: kv[0])
        return schedule, ops_log, final_solo, entry_score, entry_score, apply_log

    window_days = int(cfg.get("window_days", 6))
    max_ops = int(cfg.get("max_ops", 4))
    threshold = int(cfg.get("overlap_threshold", 8))
    hours_budget = int(cfg.get("hours_budget", 0))

    dates = sorted(schedule.keys())
    # базовые метрики до правок
    base_pairs = pairs
    base_score = entry_score
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
        base_cov_ok = _coverage_ok_in_window(cur_sched, code_of, w0, w1)
        base_slice = _slice_schedule(cur_sched, w0, w1)
        base_solo_win = sum(cov.solo_days_by_employee(base_slice, code_of).values())
        for direction in (+1, -1):
            test_sched, dh, ok, note = shifts_ops.shift_phase(cur_sched, code_of, eid, direction, (w0, w1))
            if not ok:
                apply_log.append(f"{eid}: {note} → reject")
                continue
            # проверим метрики на окне: стало ли лучше по парам и «соло»
            test_pairs = pairing.compute_pairs(test_sched, code_of)
            test_score = _pair_score(test_pairs)
            test_solo = cov.solo_days_by_employee(test_sched, code_of)
            test_cov_ok = _coverage_ok_in_window(test_sched, code_of, w0, w1)
            test_slice = _slice_schedule(test_sched, w0, w1)
            test_solo_win = sum(cov.solo_days_by_employee(test_slice, code_of).values())
            d_pair = test_score - base_score
            d_solo = test_solo.get(eid, 0) - base_solo.get(eid, 0)
            d_solo_win = test_solo_win - base_solo_win
            d_cov = test_cov_ok - base_cov_ok
            cond1 = d_pair < 0
            cond2 = (eid not in base_solo) or (d_solo <= 0 and d_solo_win <= 0)
            cond3 = d_cov >= 0
            cond4 = abs(dh) <= hours_budget
            verdict = "ACCEPT" if (cond1 and cond2 and cond3 and cond4) else "REJECT"
            summary = (
                f"{eid}: dir={'+' if direction > 0 else '-'} "
                f"window=[{w0.isoformat()}..{w1.isoformat()}] "
                f"Δpair={d_pair} Δsolo={d_solo}|win={d_solo_win} Δcov={d_cov} Δh={dh} -> {verdict}"
            )
            apply_log.append(summary)
            if verdict == "ACCEPT":
                ops_log.append(summary)
                before_tape = _fmt_tape(cur_sched, code_of, eid, w0, w1)
                after_tape = _fmt_tape(test_sched, code_of, eid, w0, w1)
                ops_log.append(f"  tape.before: {before_tape}")
                ops_log.append(f"  tape.after : {after_tape}")
                cur_sched = test_sched
                base_pairs = test_pairs
                base_score = test_score
                base_solo = test_solo
                base_cov_ok = test_cov_ok
                base_solo_win = test_solo_win
                ops += 1
                improved = True
                break
        if not improved:
            apply_log.append(f"{eid}: skip(no-accept)")

    # финальные соло-метрики
    final_solo = sorted(cov.solo_days_by_employee(cur_sched, code_of).items(), key=lambda kv: kv[0])
    final_pairs = pairing.compute_pairs(cur_sched, code_of)
    final_score = _pair_score(final_pairs)
    return cur_sched, ops_log, final_solo, entry_score, final_score, apply_log
