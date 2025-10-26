# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Tuple, Optional
from datetime import date
import copy

from engine.services import rotor

# --- Code groups ---
N8 = {"N8A", "N8B"}
N4 = {"N4A", "N4B"}
DAY12 = {"DA", "DB"}
DAY8 = {"M8A", "M8B", "E8A", "E8B"}
NIGHT12 = {"NA", "NB"}
NIGHT8 = {"N8A", "N8B"}
NIGHT4 = {"N4A", "N4B"}
VAC = {"VAC8", "VAC0"}

def _tok_for_pair(code: str, d: date) -> str:
    c = (code or "OFF").upper()
    if d.day == 1 and c in NIGHT8:
        return "O"
    if c in DAY12 or c in DAY8:
        return "D"
    if c in NIGHT12 or c in NIGHT4:
        return "N"
    return "O"


def _code(code_of, k):
    return code_of(k).upper()


def _emp_seq(schedule, code_of, emp_id: str) -> Tuple[List[date], List[Tuple[date, object, str]]]:
    """Возвращает (dates, seq[(date, assignment, CODE)]) только для нужного сотрудника."""
    dates: List[date] = []
    seq: List[Tuple[date, object, str]] = []
    for d in sorted(schedule.keys()):
        for a in schedule[d]:
            if a.employee_id != emp_id:
                continue
            c = _code(code_of, a.shift_key)
            dates.append(d)
            seq.append((d, a, c))
            break
    return dates, seq


def _fix_last_day_n4(codes: List[str]) -> None:
    if not codes:
        return
    last = codes[-1]
    if last in {"NA", "NB"}:
        codes[-1] = "N4A" if last.endswith("A") else "N4B"


def _key_for_code(code: str) -> str:
    c = (code or "").upper()
    return {
        "DA": "day_a",
        "DB": "day_b",
        "NA": "night_a",
        "NB": "night_b",
        "M8A": "m8_a",
        "M8B": "m8_b",
        "E8A": "e8_a",
        "E8B": "e8_b",
        "N4A": "n4_a",
        "N4B": "n4_b",
        "N8A": "n8_a",
        "N8B": "n8_b",
        "VAC8": "vac_wd8",
        "VAC0": "vac_we0",
        "OFF": "off",
    }.get(c, "off")


def _emp_code_on(schedule, code_of, emp_id: str, d: date) -> str:
    for a in schedule[d]:
        if a.employee_id == emp_id:
            return code_of(a.shift_key).upper()
    return "OFF"


def _swap_ab_code(code: str) -> str:
    c = (code or "").upper()
    if c == "DA":
        return "DB"
    if c == "DB":
        return "DA"
    if c == "M8A":
        return "M8B"
    if c == "M8B":
        return "M8A"
    if c == "E8A":
        return "E8B"
    if c == "E8B":
        return "E8A"
    if c == "NA":
        return "NB"
    if c == "NB":
        return "NA"
    if c == "N4A":
        return "N4B"
    if c == "N4B":
        return "N4A"
    return c


def _emp_tok_on(schedule, code_of, emp_id: str, d: date) -> str:
    return _tok_for_pair(_emp_code_on(schedule, code_of, emp_id, d), d)


def _hours_for_code(code: str) -> int:
    c = (code or "").upper()
    if c in DAY12 or c in NIGHT12:
        return 12
    if c in DAY8 or c in NIGHT8:
        return 8
    if c in NIGHT4:
        return 4
    if c == "VAC8":
        return 8
    return 0


def _rot(codes: List[str], i0: int, i1: int, direction: int) -> List[str]:
    new_codes = codes[:]
    if direction == +1:
        head = new_codes[i0]
        new_codes[i0:i1] = new_codes[i0 + 1 : i1 + 1]
        new_codes[i1] = head
    else:
        tail = new_codes[i1]
        new_codes[i0 + 1 : i1 + 1] = new_codes[i0:i1]
        new_codes[i0] = tail
    return new_codes


def shift_phase(schedule, code_of, emp_id: str, direction: int, window: Tuple[date, date]):
    """
    Сдвиг окна в начале месяца на ±1 с реальным обновлением shift_key.
    Запреты:
     - не трогаем N8* на 1-е,
     - не создаём N8 внутри месяца,
     - не создаём N4 вне последнего дня месяца.
    """

    assert direction in (-1, +1)
    dates, seq = _emp_seq(schedule, code_of, emp_id)
    if not seq:
        return schedule, 0, False, "no-rows"

    start = 0
    if seq and seq[0][2] in N8:
        start = 1

    d0, d1 = window
    n = len(dates)
    if start >= n:
        return schedule, 0, False, "window-empty"

    try:
        i0 = dates.index(d0)
    except ValueError:
        i0 = start
    try:
        i1 = dates.index(d1)
    except ValueError:
        i1 = max(start, min(n - 1, start + 5))
    i0 = max(i0, start)
    i1 = max(i1, start)
    i0 = min(i0, n - 1)
    i1 = min(i1, n - 1)
    if i0 >= i1:
        return schedule, 0, False, f"window-too-narrow({i0},{i1})"

    codes = [c for (_, _, c) in seq]
    new_codes = _rot(codes, i0, i1, direction)

    for k in range(i0, i1 + 1):
        if new_codes[k] in N8 and k != 0:
            new_codes[k] = "NA" if new_codes[k].endswith("A") else "NB"

    _fix_last_day_n4(new_codes)

    new_sched = copy.deepcopy(schedule)
    new_hours = 0
    old_hours = 0
    for idx, d in enumerate(dates):
        if idx == 0 and codes[0] in N8:
            continue
        old_c = codes[idx]
        new_c = new_codes[idx]
        if old_c == new_c:
            continue
        _, orig_assn, _ = seq[idx]
        if orig_assn and orig_assn.employee_id == emp_id:
            old_hours += int(getattr(orig_assn, "effective_hours", 0))
        for a in new_sched[d]:
            if a.employee_id != emp_id:
                continue
            a.shift_key = _key_for_code(new_c)
            a.source = "autofix"
            val = _hours_for_code(new_c)
            a.effective_hours = val
            new_hours += val
            break

    hours_delta = new_hours - old_hours
    return new_sched, hours_delta, True, f"rot({direction})[{dates[i0]}..{dates[i1]}]:Δh={hours_delta}"


# -------------------- Новые фазовые операторы --------------------


def _set_off(a) -> None:
    a.shift_key = "off"
    a.effective_hours = 0
    a.source = "phase_shift"


def flip_ab_on_day(schedule, code_of, emp_id: str, d: date):
    """Локальный флип A↔B на конкретный день без изменения D/N/O.

    N8 на 1-е число остаётся неизменным (OFF-фаза), остальные коды, включая N4*,
    допускают перестановку офисов. Часы приводим к стандарту выбранного кода.
    """

    new_sched = copy.deepcopy(schedule)
    for a in new_sched[d]:
        if a.employee_id != emp_id:
            continue
        before = code_of(a.shift_key).upper()
        if d.day == 1 and before in {"N8A", "N8B"}:
            return schedule, False, "flip_ab_on_day: protected code"
        after = _swap_ab_code(before)
        if after == before:
            return schedule, False, "flip_ab_on_day: noop"
        a.shift_key = _key_for_code(after)
        if after in {"DA", "DB", "NA", "NB"}:
            a.effective_hours = 12
        elif after in {"M8A", "M8B", "E8A", "E8B", "N8A", "N8B"}:
            a.effective_hours = 8
        elif after in {"N4A", "N4B"}:
            a.effective_hours = 4
        else:
            a.effective_hours = 0
        a.source = "pair_desync"
        return new_sched, True, f"flip_ab_on_day[{emp_id}] {before}->{after} {d.isoformat()}"
    return schedule, False, "flip_ab_on_day: no row"


def phase_shift_minus_one_skip(
    schedule,
    code_of,
    emp_id: str,
    window: Tuple[date, date],
    partner_id: Optional[str] = None,
    anti_align: bool = True,
):
    """
    Сдвиг фазы -1: убираем ночную смену N в первом фрагменте D,N,O,(O) окна
    и перешиваем хвост по циклу O,O,D,N,… (двойной OFF гарантирован, тройного OFF не будет).
    """

    new_sched = copy.deepcopy(schedule)
    days = [d for d in sorted(schedule.keys()) if window[0] <= d <= window[1]]
    days_all = sorted(schedule.keys())
    total = len(days_all)
    if not days:
        return schedule, 0, False, "phase_shift_-1: empty window"

    for d in days:
        idx = days_all.index(d)
        if idx == 0 or idx >= total - 1:
            continue

        cur_code = _emp_code_on(new_sched, code_of, emp_id, d)
        if d.day == 1 and cur_code in N8:
            continue
        if d == days_all[-1] and cur_code in N4:
            continue

        t_prev = _emp_tok_on(new_sched, code_of, emp_id, days_all[idx - 1])
        t_curr = _emp_tok_on(new_sched, code_of, emp_id, days_all[idx])
        t_next = _emp_tok_on(new_sched, code_of, emp_id, days_all[idx + 1])
        if not (t_prev == "D" and t_curr == "N" and t_next == "O"):
            continue

        for a in new_sched[d]:
            if a.employee_id == emp_id:
                before = code_of(a.shift_key).upper()
                if before not in {"NA", "NB"}:
                    return schedule, 0, False, "phase_shift_-1: target is not N"
                dh = -12
                _set_off(a)
                break

        tokens = [
            "O" if (offset % 4) in (0, 1) else ("D" if (offset % 4) == 2 else "N")
            for offset in range(0, total - idx)
        ]
        rotor.stitch_into_schedule(
            new_sched,
            code_of,
            emp_id,
            days_all[idx],
            tokens,
            partner_id=partner_id,
            anti_align=anti_align,
        )

        return new_sched, dh, True, f"phase_shift_-1[{d.isoformat()}]"

    return schedule, 0, False, "phase_shift_-1: no D,N,O pattern in window"


def phase_shift_plus_one_insert_off(
    schedule,
    code_of,
    emp_id: str,
    window: Tuple[date, date],
    partner_id: Optional[str] = None,
    anti_align: bool = True,
):
    """
    Сдвиг фазы +1: вставляем дополнительный OFF в первом блоке O,O,(работа)
    и продолжаем цикл как O,O,O,D,N,…
    """

    new_sched = copy.deepcopy(schedule)
    days = [d for d in sorted(schedule.keys()) if window[0] <= d <= window[1]]
    tokens: List[Tuple[str, str, date]] = []
    for d in days:
        code = "OFF"
        for a in new_sched[d]:
            if a.employee_id == emp_id:
                code = code_of(a.shift_key).upper()
                break
        tokens.append((_tok_for_pair(code, d), code, d))

    for idx in range(len(tokens) - 2):
        t0, c0, d0 = tokens[idx]
        t1, c1, d1 = tokens[idx + 1]
        t2, c2, d2 = tokens[idx + 2]
        if t0 == "O" and t1 == "O" and t2 in ("D", "N"):
            if {c0, c1} & VAC:
                continue
            if d2.day == 1 and c2 in N8:
                continue

            for a in new_sched[d2]:
                if a.employee_id == emp_id:
                    before = code_of(a.shift_key).upper()
                    dh = -_hours_for_code(before)
                    _set_off(a)
                    break

            days_all = sorted(new_sched.keys())
            idx2 = days_all.index(d2)
            tokens = [
                "O" if (offset % 4) in (0, 3) else ("D" if (offset % 4) == 1 else "N")
                for offset in range(0, len(days_all) - idx2)
            ]
            rotor.stitch_into_schedule(
                new_sched,
                code_of,
                emp_id,
                days_all[idx2],
                tokens,
                partner_id=partner_id,
                anti_align=anti_align,
            )

            return new_sched, dh, True, f"phase_shift_+1[{d2.isoformat()}]"

    return schedule, 0, False, "phase_shift_+1: no place O,O,(work)"


def flip_ab_on_next_token(
    schedule,
    code_of,
    emp_id: str,
    window: Tuple[date, date],
    *,
    kind: str = "D",
    partner_id: Optional[str] = None,
    anti_align: bool = True,
):
    days_all = sorted(schedule.keys())
    w0, w1 = window
    days = [d for d in days_all if w0 <= d <= w1]
    if not days:
        return schedule, 0, False, "flip_ab: empty window"

    start_day: Optional[date] = None
    for d in days:
        tok = _tok_for_pair(_emp_code_on(schedule, code_of, emp_id, d), d)
        if tok == kind:
            start_day = d
            break
    if start_day is None:
        return schedule, 0, False, "flip_ab: no token"

    start_idx = days_all.index(start_day)
    tail_tokens = [
        _tok_for_pair(_emp_code_on(schedule, code_of, emp_id, day), day)
        for day in days_all[start_idx:]
    ]

    new_sched = copy.deepcopy(schedule)
    rotor.stitch_into_schedule(
        new_sched,
        code_of,
        emp_id,
        start_day,
        tail_tokens,
        partner_id=partner_id,
        anti_align=anti_align,
    )
    return new_sched, 0, True, f"flip_ab[{kind}]@{start_day.isoformat()}"


def desync_pair_month(schedule, code_of, emp_a: str, emp_b: str):
    """Пост-проход по месяцу: разводим офисы, если оба в одну смену.

    На датах, где сотрудники работают в одной фазе (D или N) и в одном офисе,
    выполняем `flip_ab_on_day` для emp_a. Хвостовые N4* считаем полноценными
    сменами и разрешаем флип; N8 на 1-е число пропускаем.
    """

    new_sched = copy.deepcopy(schedule)
    flips = 0
    notes: List[str] = []
    for d in sorted(new_sched.keys()):
        ca = _emp_code_on(new_sched, code_of, emp_a, d)
        cb = _emp_code_on(new_sched, code_of, emp_b, d)
        ta = _tok_for_pair(ca, d)
        tb = _tok_for_pair(cb, d)
        if ta != tb or ta == "O":
            continue
        if ca.endswith("A") != cb.endswith("A"):
            continue
        if d.day == 1 and (ca in {"N8A", "N8B"} or cb in {"N8A", "N8B"}):
            continue
        new_sched, ok, note = flip_ab_on_day(new_sched, code_of, emp_a, d)
        if ok:
            flips += 1
            notes.append(note)
    return new_sched, flips, notes


