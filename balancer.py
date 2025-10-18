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


def _hours_by_employee(schedule, code_of) -> Dict[str, int]:
    hours: Dict[str, int] = {}
    for rows in schedule.values():
        for a in rows:
            code = code_of(a.shift_key).upper()
            if code in {"DA", "DB", "NA", "NB"}:
                h = 12
            elif code in {"M8A", "M8B", "E8A", "E8B", "N8A", "N8B", "VAC8"}:
                h = 8
            elif code in {"N4A", "N4B"}:
                h = 4
            else:
                h = 0
            hours[a.employee_id] = hours.get(a.employee_id, 0) + h
    return hours


def _solo_in_window(schedule, code_of, ordered_dates: List[date], window_days: int, eid: str) -> int:
    limit = min(len(ordered_dates), max(1, window_days))
    window_sched = {d: schedule[d] for d in ordered_dates[:limit]}
    return cov.solo_days_by_employee(window_sched, code_of).get(eid, 0)


def apply_pair_breaking(
    schedule,
    employees,
    code_of,
    cfg,
) -> Tuple[object, List[str], Dict[str, int], int, int, List[str]]:
    """Балансировка по парам с фазовыми сдвигами в начале месяца."""

    ops_log: List[str] = []
    apply_log: List[str] = []

    prev_pairs = cfg.get("prev_pairs") or []
    threshold_day = int(cfg.get("overlap_threshold", 6))
    entry_pairs = pairing.pair_hours_exclusive(schedule, code_of, prev_pairs, threshold_day=threshold_day)
    entry_score = sum(item[4] for item in entry_pairs)

    if not cfg.get("enabled", False):
        solo_after = cov.solo_days_by_employee(schedule, code_of)
        return schedule, ops_log, solo_after, entry_score, entry_score, apply_log

    window_days = int(cfg.get("window_days", 6))
    max_ops = int(cfg.get("max_ops", 4))
    hours_budget = int(cfg.get("hours_budget", 0))
    norm_by_emp: Dict[str, int] = cfg.get("norm_by_employee", {}) or {}

    cur_sched = copy.deepcopy(schedule)
    ordered_dates = sorted(cur_sched.keys())
    prev_exclusive = pairing.exclusive_matching_by_day(prev_pairs or [], threshold_day=threshold_day)

    def _pair_key(a: str, b: str) -> str:
        return f"{a}~{b}" if a < b else f"{b}~{a}"

    ops = 0
    for emp_a, emp_b, _, _ in prev_exclusive:
        if ops >= max_ops:
            break

        hours_now = _hours_by_employee(cur_sched, code_of)

        def_a = norm_by_emp.get(emp_a, hours_now.get(emp_a, 0)) - hours_now.get(emp_a, 0)
        def_b = norm_by_emp.get(emp_b, hours_now.get(emp_b, 0)) - hours_now.get(emp_b, 0)

        minus_emp = emp_a if def_a <= def_b else emp_b
        plus_emp = emp_b if def_b < def_a else emp_a

        w0 = ordered_dates[0]
        w1 = ordered_dates[min(len(ordered_dates) - 1, max(1, window_days) - 1)]
        window = (w0, w1)

        before_pairs = pairing.pair_hours_exclusive(cur_sched, code_of, prev_pairs, threshold_day=threshold_day)
        before_map = {
            _pair_key(a, b): (a, b, h_d, h_n, h_t)
            for a, b, h_d, h_n, h_t in before_pairs
        }
        pair_id = _pair_key(emp_a, emp_b)

        # --- Опция (-1): пропустить смену ---
        base_solo_minus = _solo_in_window(cur_sched, code_of, ordered_dates, window_days, minus_emp)
        test_sched, dh, ok, note = shifts_ops.phase_shift_minus_one_skip(cur_sched, code_of, minus_emp, window)
        if not ok:
            apply_log.append(f"{minus_emp}: op=-1 {note}")
        else:
            after_pairs = pairing.pair_hours_exclusive(test_sched, code_of, prev_pairs, threshold_day=threshold_day)
            after_map = {
                _pair_key(a, b): (a, b, h_d, h_n, h_t)
                for a, b, h_d, h_n, h_t in after_pairs
            }
            before_ht = before_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            after_ht = after_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            d_pair = after_ht - before_ht
            after_solo_minus = _solo_in_window(test_sched, code_of, ordered_dates, window_days, minus_emp)
            d_solo = after_solo_minus - base_solo_minus
            verdict = "ACCEPT" if (d_pair < 0 and d_solo <= 0 and abs(dh) <= hours_budget) else "REJECT"
            summary = (
                f"{minus_emp}: op=-1 window=[{w0.isoformat()}..{w1.isoformat()}] "
                f"Δpair_excl={d_pair} Δsolo={d_solo} Δh={dh} -> {verdict}"
            )
            apply_log.append(summary)
            if verdict == "ACCEPT":
                ops_log.append(summary)
                ops_log.append(f"  tape.before: {_fmt_tape(cur_sched, code_of, minus_emp, w0, w1)}")
                ops_log.append(f"  tape.after : {_fmt_tape(test_sched, code_of, minus_emp, w0, w1)}")
                cur_sched = test_sched
                ordered_dates = sorted(cur_sched.keys())
                ops += 1
                continue

        # --- Опция (+1): вставка OFF ---
        base_solo_plus = _solo_in_window(cur_sched, code_of, ordered_dates, window_days, plus_emp)
        test_sched, dh2, ok2, note2 = shifts_ops.phase_shift_plus_one_insert_off(cur_sched, code_of, plus_emp, window)
        if not ok2:
            apply_log.append(f"{plus_emp}: op=+1 {note2}")
            continue

        after_pairs = pairing.pair_hours_exclusive(test_sched, code_of, prev_pairs, threshold_day=threshold_day)
        after_map = {
            _pair_key(a, b): (a, b, h_d, h_n, h_t)
            for a, b, h_d, h_n, h_t in after_pairs
        }
        before_ht = before_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
        after_ht = after_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
        d_pair = after_ht - before_ht
        after_solo_plus = _solo_in_window(test_sched, code_of, ordered_dates, window_days, plus_emp)
        d_solo = after_solo_plus - base_solo_plus
        verdict = "ACCEPT" if (d_solo <= 0 and abs(dh2) <= hours_budget) else "REJECT"
        summary = (
            f"{plus_emp}: op=+1 window=[{w0.isoformat()}..{w1.isoformat()}] "
            f"Δpair_excl={d_pair} Δsolo={d_solo} Δh={dh2} -> {verdict}"
        )
        apply_log.append(summary)
        if verdict == "ACCEPT":
            ops_log.append(summary)
            ops_log.append(f"  tape.before: {_fmt_tape(cur_sched, code_of, plus_emp, w0, w1)}")
            ops_log.append(f"  tape.after : {_fmt_tape(test_sched, code_of, plus_emp, w0, w1)}")
            cur_sched = test_sched
            ordered_dates = sorted(cur_sched.keys())
            ops += 1

    solo_after = cov.solo_days_by_employee(cur_sched, code_of)
    final_pairs = pairing.pair_hours_exclusive(cur_sched, code_of, prev_pairs, threshold_day=threshold_day)
    final_score = sum(item[4] for item in final_pairs)
    return cur_sched, ops_log, solo_after, entry_score, final_score, apply_log
