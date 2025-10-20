# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import date
import copy
import shifts_ops
import pairing
import coverage as cov

DAYC = {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}


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


def _hours_of(code: str) -> int:
    c = (code or "OFF").upper()
    if c in {"DA", "DB", "NA", "NB"}:
        return 12
    if c in {"M8A", "M8B", "E8A", "E8B", "N8A", "N8B", "VAC8"}:
        return 8
    if c in {"N4A", "N4B"}:
        return 4
    return 0


def _code_on(schedule, code_of, emp_id: str, d: date) -> str:
    for a in schedule[d]:
        if a.employee_id == emp_id:
            return code_of(a.shift_key).upper()
    return "OFF"


def _tok_for_pair(code: str, d: date) -> str:
    upper = (code or "OFF").upper()
    if d.day == 1 and upper in {"N8A", "N8B"}:
        return "O"
    if upper in {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}:
        return "D"
    if upper in {"NA", "NB", "N4A", "N4B"}:
        return "N"
    return "O"


def _emp_tok_on(schedule, code_of, emp_id: str, d: date) -> str:
    for a in schedule[d]:
        if a.employee_id == emp_id:
            return _tok_for_pair(code_of(a.shift_key).upper(), d)
    return "O"


def _last_tok_and_stage(schedule, code_of, emp_id: str) -> Tuple[str, int]:
    dates = sorted(schedule.keys())
    if not dates:
        return "O", 1
    last_tok = _emp_tok_on(schedule, code_of, emp_id, dates[-1])
    if last_tok != "O":
        return last_tok, 0
    if len(dates) >= 2 and _emp_tok_on(schedule, code_of, emp_id, dates[-2]) == "O":
        return "O", 2
    return "O", 1


def _hours_of_tok(tok: str) -> int:
    return 12 if tok in ("D", "N") else 0


def _delta_hours_pred_minus_one(schedule, code_of, emp_id: str) -> int:
    tok, stage = _last_tok_and_stage(schedule, code_of, emp_id)
    if tok == "D":
        next_tok = "N"
    elif tok == "N":
        next_tok = "O"
    else:
        next_tok = "D" if stage == 2 else "O"
    return _hours_of_tok(next_tok) - 12


def _delta_hours_pred_plus_one(schedule, code_of, emp_id: str) -> int:
    tok, _ = _last_tok_and_stage(schedule, code_of, emp_id)
    return -_hours_of_tok(tok)


def _solo_in_window(schedule, code_of, ordered_dates: List[date], window_days: int, eid: str) -> int:
    limit = min(len(ordered_dates), max(1, window_days))
    window_sched = {d: schedule[d] for d in ordered_dates[:limit]}
    return cov.solo_days_by_employee(window_sched, code_of).get(eid, 0)


def _same_office_overlap_hours(
    schedule,
    code_of,
    emp_a: str,
    emp_b: str,
    ordered_dates: List[date],
    window_days: int,
) -> int:
    limit = min(len(ordered_dates), max(1, window_days))
    hours = 0
    for day in ordered_dates[:limit]:
        code_a = _code_on(schedule, code_of, emp_a, day)
        code_b = _code_on(schedule, code_of, emp_b, day)
        if day.day == 1 and (code_a in {"N8A", "N8B"} or code_b in {"N8A", "N8B"}):
            continue
        if (
            code_a in DAYC
            and code_b in DAYC
            and code_a.endswith("A") == code_b.endswith("A")
        ):
            hours += min(_hours_of(code_a), _hours_of(code_b))
            continue
        if (
            code_a in {"NA", "NB", "N4A", "N4B"}
            and code_b in {"NA", "NB", "N4A", "N4B"}
            and code_a.endswith("A") == code_b.endswith("A")
        ):
            hours += min(_hours_of(code_a), _hours_of(code_b))
    return hours


def _same_office_overlap_month(schedule, code_of, emp_a: str, emp_b: str) -> int:
    days = sorted(schedule.keys())
    return _same_office_overlap_hours(schedule, code_of, emp_a, emp_b, days, len(days))


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

    intern_ids_cfg = set(cfg.get("intern_ids", []) or [])
    intern_ids_emp = {
        e.id
        for e in employees
        if getattr(e, "is_intern", False)
        or getattr(e, "intern", False)
        or (hasattr(e, "tags") and (e.tags or []) and "intern" in e.tags)
    }
    intern_ids = intern_ids_cfg | intern_ids_emp

    entry_pairs = pairing.pair_hours_exclusive(
        schedule,
        code_of,
        prev_pairs,
        threshold_day=threshold_day,
        skip_ids=intern_ids,
    )
    entry_score = sum(item[4] for item in entry_pairs)

    if not cfg.get("enabled", False):
        solo_after = cov.solo_days_by_employee(schedule, code_of)
        return schedule, ops_log, solo_after, entry_score, entry_score, apply_log

    window_days = int(cfg.get("window_days", 6))
    max_ops = int(cfg.get("max_ops", 4))
    hours_budget = int(cfg.get("hours_budget", 0))
    anti_align = bool(cfg.get("anti_align", True))
    norm_by_emp: Dict[str, int] = cfg.get("norm_by_employee", {}) or {}

    cur_sched = copy.deepcopy(schedule)
    ordered_dates = sorted(cur_sched.keys())

    base_pairs_hours = pairing.pair_hours_exclusive(
        cur_sched,
        code_of,
        prev_pairs,
        threshold_day=threshold_day,
        skip_ids=intern_ids,
    )
    base_score = sum(item[4] for item in base_pairs_hours)

    prev_exclusive = pairing.exclusive_matching_by_day(prev_pairs or [], threshold_day=threshold_day)
    prev_exclusive = [
        (a, b, d, n)
        for (a, b, d, n) in prev_exclusive
        if a not in intern_ids and b not in intern_ids
    ]

    fixed_pairs_cfg = cfg.get("fixed_pairs") or []
    target_pairs: List[Tuple[str, str, int, int]] = []
    if fixed_pairs_cfg:
        for pair in fixed_pairs_cfg:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            a, b = pair
            if a in intern_ids or b in intern_ids:
                continue
            target_pairs.append((a, b, 0, 0))
    else:
        target_pairs = prev_exclusive

    moved: set[str] = set()
    pred_hours_cum = 0
    pred_zero_cnt = 0
    pred_minus12_cnt = 0

    def _pair_key(a: str, b: str) -> str:
        return f"{a}~{b}" if a < b else f"{b}~{a}"

    ops = 0
    for emp_a, emp_b, _, _ in target_pairs:
        if ops >= max_ops:
            break
        def partner_of(emp: str) -> str:
            return emp_b if emp == emp_a else emp_a
        if emp_a in moved or emp_b in moved:
            apply_log.append(f"{emp_a}~{emp_b}: skip(pair-member already moved)")
            continue

        hours_now = _hours_by_employee(cur_sched, code_of)
        def_a = norm_by_emp.get(emp_a, hours_now.get(emp_a, 0)) - hours_now.get(emp_a, 0)
        def_b = norm_by_emp.get(emp_b, hours_now.get(emp_b, 0)) - hours_now.get(emp_b, 0)

        dHm_a = _delta_hours_pred_minus_one(cur_sched, code_of, emp_a)
        dHm_b = _delta_hours_pred_minus_one(cur_sched, code_of, emp_b)
        minus_emp = emp_a if (dHm_a > dHm_b) or (dHm_a == dHm_b and def_a <= def_b) else emp_b
        plus_emp = emp_b if minus_emp == emp_a else emp_a

        if minus_emp in intern_ids:
            minus_emp = plus_emp
        if minus_emp in intern_ids or plus_emp in intern_ids:
            apply_log.append(f"{emp_a}~{emp_b}: skip(intern in pair)")
            continue

        limit = min(len(ordered_dates) - 1, max(1, window_days) - 1)
        w0 = ordered_dates[0]
        w1 = ordered_dates[limit]
        window = (w0, w1)

        before_pairs = pairing.pair_hours_exclusive(
            cur_sched,
            code_of,
            prev_pairs,
            threshold_day=threshold_day,
            skip_ids=intern_ids,
        )
        before_map = {
            _pair_key(a, b): (a, b, h_d, h_n, h_t)
            for a, b, h_d, h_n, h_t in before_pairs
        }
        pair_id = _pair_key(emp_a, emp_b)

        base_solo_minus = _solo_in_window(cur_sched, code_of, ordered_dates, window_days, minus_emp)
        before_same_office = _same_office_overlap_hours(
            cur_sched, code_of, emp_a, emp_b, ordered_dates, window_days
        )
        before_same_office_month = _same_office_overlap_month(cur_sched, code_of, emp_a, emp_b)
        dHpred1 = _delta_hours_pred_minus_one(cur_sched, code_of, minus_emp)

        test_sched = None
        ok1 = False
        note1 = ""
        blocked_budget1 = False
        if (pred_hours_cum + dHpred1) < -hours_budget:
            apply_log.append(
                f"{minus_emp}: op=-1 window=[{w0.isoformat()}..{w1.isoformat()}] "
                f"Δhours_pred={dHpred1} Σpred={pred_hours_cum} budget={-hours_budget} -> REJECT(budget)"
            )
            blocked_budget1 = True
        else:
            test_sched, dh1, ok1, note1 = shifts_ops.phase_shift_minus_one_skip(
                cur_sched,
                code_of,
                minus_emp,
                window,
                partner_id=partner_of(minus_emp),
                anti_align=anti_align,
            )

        if ok1 and test_sched is not None:
            after_pairs = pairing.pair_hours_exclusive(
                test_sched,
                code_of,
                prev_pairs,
                threshold_day=threshold_day,
                skip_ids=intern_ids,
            )
            after_map = {
                _pair_key(a, b): (a, b, h_d, h_n, h_t)
                for a, b, h_d, h_n, h_t in after_pairs
            }
            before_ht = before_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            after_ht = after_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            d_pair = after_ht - before_ht
            after_solo_minus = _solo_in_window(test_sched, code_of, ordered_dates, window_days, minus_emp)
            d_solo = after_solo_minus - base_solo_minus
            after_same_office = _same_office_overlap_hours(
                test_sched, code_of, emp_a, emp_b, ordered_dates, window_days
            )
            after_same_office_month = _same_office_overlap_month(
                test_sched, code_of, emp_a, emp_b
            )
            so_ok = after_same_office <= before_same_office
            so_month_ok = after_same_office_month <= before_same_office_month
            verdict = (
                "ACCEPT" if (d_pair < 0 and d_solo <= 0 and so_ok and so_month_ok) else "REJECT"
            )
            summary = (
                f"{minus_emp}: op=-1 window=[{w0.isoformat()}..{w1.isoformat()}] "
                f"Δpair_excl={d_pair} Δsolo={d_solo} "
                f"Δsame_office={after_same_office - before_same_office} "
                f"Δsame_office_month={after_same_office_month - before_same_office_month} "
                f"Δhours_pred={dHpred1} Σpred={pred_hours_cum + dHpred1} -> {verdict}"
            )
            apply_log.append(summary)
            if verdict == "ACCEPT":
                ops_log.append(summary)
                ops_log.append(f"  tape.before: {_fmt_tape(cur_sched, code_of, minus_emp, w0, w1)}")
                ops_log.append(f"  tape.after : {_fmt_tape(test_sched, code_of, minus_emp, w0, w1)}")
                cur_sched = test_sched
                ordered_dates = sorted(cur_sched.keys())
                base_pairs_hours = after_pairs
                base_score = sum(item[4] for item in base_pairs_hours)
                ops += 1
                moved.add(minus_emp)
                pred_hours_cum += dHpred1
                if dHpred1 == 0:
                    pred_zero_cnt += 1
                elif dHpred1 == -12:
                    pred_minus12_cnt += 1
                continue
        elif not ok1 and not blocked_budget1:
            apply_log.append(f"{minus_emp}: op=-1 Δhours_pred={dHpred1} Σpred={pred_hours_cum} {note1}".strip())

        base_solo_plus = _solo_in_window(cur_sched, code_of, ordered_dates, window_days, plus_emp)
        dHpred2 = _delta_hours_pred_plus_one(cur_sched, code_of, plus_emp)

        test_sched2 = None
        ok2 = False
        note2 = ""
        blocked_budget2 = False
        if (pred_hours_cum + dHpred2) < -hours_budget:
            apply_log.append(
                f"{plus_emp}: op=+1 window=[{w0.isoformat()}..{w1.isoformat()}] "
                f"Δhours_pred={dHpred2} Σpred={pred_hours_cum} budget={-hours_budget} -> REJECT(budget)"
            )
            blocked_budget2 = True
        else:
            test_sched2, dh2, ok2, note2 = shifts_ops.phase_shift_plus_one_insert_off(
                cur_sched,
                code_of,
                plus_emp,
                window,
                partner_id=partner_of(plus_emp),
                anti_align=anti_align,
            )

        if ok2 and test_sched2 is not None:
            after_pairs = pairing.pair_hours_exclusive(
                test_sched2,
                code_of,
                prev_pairs,
                threshold_day=threshold_day,
                skip_ids=intern_ids,
            )
            after_map = {
                _pair_key(a, b): (a, b, h_d, h_n, h_t)
                for a, b, h_d, h_n, h_t in after_pairs
            }
            before_ht = before_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            after_ht = after_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            d_pair = after_ht - before_ht
            after_solo_plus = _solo_in_window(test_sched2, code_of, ordered_dates, window_days, plus_emp)
            d_solo = after_solo_plus - base_solo_plus
            after_same_office = _same_office_overlap_hours(
                test_sched2, code_of, emp_a, emp_b, ordered_dates, window_days
            )
            after_same_office_month = _same_office_overlap_month(
                test_sched2, code_of, emp_a, emp_b
            )
            so_ok = after_same_office <= before_same_office
            so_month_ok = after_same_office_month <= before_same_office_month
            verdict = "ACCEPT" if (d_solo <= 0 and so_ok and so_month_ok) else "REJECT"
            summary = (
                f"{plus_emp}: op=+1 window=[{w0.isoformat()}..{w1.isoformat()}] "
                f"Δpair_excl={d_pair} Δsolo={d_solo} "
                f"Δsame_office={after_same_office - before_same_office} "
                f"Δsame_office_month={after_same_office_month - before_same_office_month} "
                f"Δhours_pred={dHpred2} Σpred={pred_hours_cum + dHpred2} -> {verdict}"
            )
            apply_log.append(summary)
            if verdict == "ACCEPT":
                ops_log.append(summary)
                ops_log.append(f"  tape.before: {_fmt_tape(cur_sched, code_of, plus_emp, w0, w1)}")
                ops_log.append(f"  tape.after : {_fmt_tape(test_sched2, code_of, plus_emp, w0, w1)}")
                cur_sched = test_sched2
                ordered_dates = sorted(cur_sched.keys())
                base_pairs_hours = after_pairs
                base_score = sum(item[4] for item in base_pairs_hours)
                ops += 1
                moved.add(plus_emp)
                pred_hours_cum += dHpred2
                if dHpred2 == 0:
                    pred_zero_cnt += 1
                elif dHpred2 == -12:
                    pred_minus12_cnt += 1
                continue
        elif not ok2 and not blocked_budget2:
            apply_log.append(f"{plus_emp}: op=+1 Δhours_pred={dHpred2} Σpred={pred_hours_cum} {note2}".strip())

        if ops >= max_ops:
            continue

        flip_sched_d, _, ok_flip_d, note_flip_d = shifts_ops.flip_ab_on_next_token(
            cur_sched,
            code_of,
            minus_emp,
            window,
            kind="D",
            partner_id=partner_of(minus_emp),
            anti_align=anti_align,
        )
        if ok_flip_d:
            after_pairs = pairing.pair_hours_exclusive(
                flip_sched_d,
                code_of,
                prev_pairs,
                threshold_day=threshold_day,
                skip_ids=intern_ids,
            )
            after_map = {
                _pair_key(a, b): (a, b, h_d, h_n, h_t)
                for a, b, h_d, h_n, h_t in after_pairs
            }
            before_ht = before_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            after_ht = after_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            d_pair = after_ht - before_ht
            after_same_office = _same_office_overlap_hours(
                flip_sched_d, code_of, emp_a, emp_b, ordered_dates, window_days
            )
            after_same_office_month = _same_office_overlap_month(
                flip_sched_d, code_of, emp_a, emp_b
            )
            so_ok = after_same_office <= before_same_office
            so_month_ok = after_same_office_month <= before_same_office_month
            d_solo = _solo_in_window(
                flip_sched_d, code_of, ordered_dates, window_days, minus_emp
            ) - base_solo_minus
            verdict = "ACCEPT" if (d_solo <= 0 and so_ok and so_month_ok) else "REJECT"
            summary = (
                f"{minus_emp}: op=flipD window=[{w0.isoformat()}..{w1.isoformat()}] "
                f"Δpair_excl={d_pair} Δsolo={d_solo} "
                f"Δsame_office={after_same_office - before_same_office} "
                f"Δsame_office_month={after_same_office_month - before_same_office_month} "
                f"Δhours_pred=0 Σpred={pred_hours_cum} -> {verdict}"
            )
            apply_log.append(summary)
            if verdict == "ACCEPT":
                ops_log.append(summary)
                cur_sched = flip_sched_d
                ordered_dates = sorted(cur_sched.keys())
                base_pairs_hours = after_pairs
                base_score = sum(item[4] for item in base_pairs_hours)
                ops += 1
                moved.add(minus_emp)
                continue

        if ops >= max_ops:
            continue

        flip_sched_n, _, ok_flip_n, note_flip_n = shifts_ops.flip_ab_on_next_token(
            cur_sched,
            code_of,
            plus_emp,
            window,
            kind="N",
            partner_id=partner_of(plus_emp),
            anti_align=anti_align,
        )
        if ok_flip_n:
            after_pairs = pairing.pair_hours_exclusive(
                flip_sched_n,
                code_of,
                prev_pairs,
                threshold_day=threshold_day,
                skip_ids=intern_ids,
            )
            after_map = {
                _pair_key(a, b): (a, b, h_d, h_n, h_t)
                for a, b, h_d, h_n, h_t in after_pairs
            }
            before_ht = before_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            after_ht = after_map.get(pair_id, (emp_a, emp_b, 0, 0, 0))[4]
            d_pair = after_ht - before_ht
            after_same_office = _same_office_overlap_hours(
                flip_sched_n, code_of, emp_a, emp_b, ordered_dates, window_days
            )
            after_same_office_month = _same_office_overlap_month(
                flip_sched_n, code_of, emp_a, emp_b
            )
            so_ok = after_same_office <= before_same_office
            so_month_ok = after_same_office_month <= before_same_office_month
            d_solo = _solo_in_window(
                flip_sched_n, code_of, ordered_dates, window_days, plus_emp
            ) - base_solo_plus
            verdict = "ACCEPT" if (d_solo <= 0 and so_ok and so_month_ok) else "REJECT"
            summary = (
                f"{plus_emp}: op=flipN window=[{w0.isoformat()}..{w1.isoformat()}] "
                f"Δpair_excl={d_pair} Δsolo={d_solo} "
                f"Δsame_office={after_same_office - before_same_office} "
                f"Δsame_office_month={after_same_office_month - before_same_office_month} "
                f"Δhours_pred=0 Σpred={pred_hours_cum} -> {verdict}"
            )
            apply_log.append(summary)
            if verdict == "ACCEPT":
                ops_log.append(summary)
                cur_sched = flip_sched_n
                ordered_dates = sorted(cur_sched.keys())
                base_pairs_hours = after_pairs
                base_score = sum(item[4] for item in base_pairs_hours)
                ops += 1
                moved.add(plus_emp)
                continue

        if not ok_flip_d and note_flip_d:
            apply_log.append(f"{minus_emp}: op=flipD {note_flip_d}")
        if not ok_flip_n and note_flip_n:
            apply_log.append(f"{plus_emp}: op=flipN {note_flip_n}")

    solo_after = cov.solo_days_by_employee(cur_sched, code_of)

    post_notes: List[str] = []
    total_flips = 0
    for a, b, _, _ in target_pairs:
        before_so = _same_office_overlap_month(cur_sched, code_of, a, b)
        fixed_sched, flips, notes = shifts_ops.desync_pair_month(cur_sched, code_of, a, b)
        after_so = _same_office_overlap_month(fixed_sched, code_of, a, b)
        if flips > 0 and after_so <= before_so:
            cur_sched = fixed_sched
            ordered_dates = sorted(cur_sched.keys())
            total_flips += flips
            post_notes.extend([f"{a}~{b}: {msg}" for msg in notes])

    if total_flips:
        ops_log.append(f"[pair_breaking.post] desync_same_office flips={total_flips}")
        for note in post_notes:
            ops_log.append("  " + note)

    after_pairs = pairing.pair_hours_exclusive(
        cur_sched,
        code_of,
        prev_pairs,
        threshold_day=threshold_day,
        skip_ids=intern_ids,
    )
    after_score = sum(item[4] for item in after_pairs)

    ops_log.append("[pairs.after_ops.delta]")
    before_map = {
        _pair_key(a, b): ht for a, b, _, _, ht in entry_pairs
    }
    after_map = {
        _pair_key(a, b): ht for a, b, _, _, ht in after_pairs
    }
    for key in sorted(set(before_map.keys()) | set(after_map.keys())):
        b = before_map.get(key, 0)
        a = after_map.get(key, 0)
        ops_log.append(f" {key}: {b} → {a} (Δ={a - b})")
    ops_log.append(
        f"[pairs.ops.summary] accepted={ops} pred_hours: Σ={pred_hours_cum} (0={pred_zero_cnt}, -12={pred_minus12_cnt})"
    )

    return cur_sched, ops_log, solo_after, entry_score, after_score, apply_log
