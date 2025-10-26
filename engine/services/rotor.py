# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple
import copy

DAY_CODES = {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}
NIGHT_CODES = {"NA", "NB"}
N8 = {"N8A", "N8B"}
N4 = {"N4A", "N4B"}
VAC = {"VAC8", "VAC0"}

DAY12 = {"DA", "DB"}
DAY8 = {"M8A", "M8B", "E8A", "E8B"}
NIGHT12 = {"NA", "NB"}
NIGHT8 = N8
NIGHT4 = {"N4A", "N4B"}

_CODE_TO_INFO = {
    "DA": ("day_a", 12),
    "DB": ("day_b", 12),
    "NA": ("night_a", 12),
    "NB": ("night_b", 12),
    "M8A": ("m8_a", 8),
    "M8B": ("m8_b", 8),
    "E8A": ("e8_a", 8),
    "E8B": ("e8_b", 8),
    "N4A": ("n4_a", 4),
    "N4B": ("n4_b", 4),
    "N8A": ("n8_a", 8),
    "N8B": ("n8_b", 8),
    "VAC8": ("vac_wd8", 8),
    "VAC0": ("vac_we0", 0),
    "OFF": ("off", 0),
}


def _is_day(code: str) -> bool:
    return code in DAY_CODES


def _is_night(code: str) -> bool:
    return code in NIGHT_CODES or code in N4 or code in N8


def _code_on(schedule, code_of, emp_id: str, day: date) -> str:
    for assignment in schedule[day]:
        if assignment.employee_id == emp_id:
            return code_of(assignment.shift_key).upper()
    return "OFF"


def _ab_of(code: str) -> Optional[str]:
    if not code:
        return None
    upper = code.upper()
    if upper.endswith("A"):
        return "A"
    if upper.endswith("B"):
        return "B"
    return None


def _partner_kind_ab(code: str) -> Optional[Tuple[str, str]]:
    """Возвращает ('D'|'N', 'A'|'B') для кода напарника, иначе None."""
    upper = (code or "OFF").upper()
    if upper in DAY_CODES:
        return "D", _ab_of(upper)
    if upper in NIGHT_CODES or upper in N4:
        return "N", _ab_of(upper)
    return None


@dataclass
class RotorState:
    day_ab: Optional[str] = None
    night_ab: Optional[str] = None

    def next_day_code(self) -> str:
        if self.day_ab is None:
            self.day_ab = "A"
        else:
            self.day_ab = "B" if self.day_ab == "A" else "A"
        return "DA" if self.day_ab == "A" else "DB"

    def next_night_code(self) -> str:
        if self.night_ab is None:
            self.night_ab = "A"
        else:
            self.night_ab = "B" if self.night_ab == "A" else "A"
        return "NA" if self.night_ab == "A" else "NB"


def infer_state(schedule, code_of, emp_id: str, start_date: date) -> RotorState:
    days = sorted(schedule.keys())
    state = RotorState()
    if not days:
        return state

    first_day = days[0]
    if first_day == start_date:
        first_code = _code_on(schedule, code_of, emp_id, first_day)
        if first_code in N8:
            state.night_ab = _ab_of(first_code)

    for day in reversed(days):
        if day >= start_date:
            continue
        code = _code_on(schedule, code_of, emp_id, day)
        if code in DAY_CODES and state.day_ab is None:
            state.day_ab = _ab_of(code)
        if _is_night(code) and state.night_ab is None:
            state.night_ab = _ab_of(code)
        if state.day_ab is not None and state.night_ab is not None:
            break
    return state


def _set_code(schedule, emp_id: str, day: date, code: Optional[str]) -> None:
    for assignment in schedule[day]:
        if assignment.employee_id != emp_id:
            continue
        target_code = (code or "OFF").upper()
        info = _CODE_TO_INFO.get(target_code)
        if info is None:
            return
        key, hours = info
        assignment.shift_key = key
        assignment.effective_hours = hours
        assignment.source = "phase_shift"
        return


def stitch_into_schedule(
    schedule,
    code_of,
    emp_id: str,
    start_date: date,
    tokens: List[str],
    partner_id: Optional[str] = None,
    anti_align: bool = True,
) -> None:
    """Перекрашивает хвост по ленте токенов, с учётом чередования офисов."""

    days = sorted(schedule.keys())
    if start_date not in days:
        return
    start_idx = days.index(start_date)
    state = infer_state(schedule, code_of, emp_id, start_date)

    if anti_align and partner_id:
        primed_day_partner = False
        primed_night_partner = False
        for offset, token in enumerate(tokens):
            if primed_day_partner and primed_night_partner:
                break
            idx = start_idx + offset
            if idx >= len(days):
                break
            if token not in ("D", "N"):
                continue
            day = days[idx]
            partner_code = _code_on(schedule, code_of, partner_id, day).upper()
            kind_ab = _partner_kind_ab(partner_code)
            if not kind_ab:
                continue
            kind, partner_ab = kind_ab
            if partner_ab not in ("A", "B"):
                continue
            desired = "B" if partner_ab == "A" else "A"
            pre = "B" if desired == "A" else "A"
            if kind == "D" and not primed_day_partner:
                state.day_ab = pre
                primed_day_partner = True
            elif kind == "N" and not primed_night_partner:
                state.night_ab = pre
                primed_night_partner = True

    primed_day_self = False
    primed_night_self = False
    for offset, token in enumerate(tokens):
        if primed_day_self and primed_night_self:
            break
        idx = start_idx + offset
        if idx >= len(days):
            break
        if token not in ("D", "N"):
            continue
        day = days[idx]
        current_code = _code_on(schedule, code_of, emp_id, day).upper()
        if token == "D" and not primed_day_self and _is_day(current_code):
            ab = _ab_of(current_code)
            if ab in ("A", "B") and state.day_ab is None:
                state.day_ab = "B" if ab == "A" else "A"
                primed_day_self = True
        elif token == "N" and not primed_night_self and _is_night(current_code):
            ab = _ab_of(current_code)
            if ab in ("A", "B") and state.night_ab is None:
                state.night_ab = "B" if ab == "A" else "A"
                primed_night_self = True

    for offset, token in enumerate(tokens):
        idx = start_idx + offset
        if idx >= len(days):
            break
        day = days[idx]
        current_code = _code_on(schedule, code_of, emp_id, day)
        if current_code in VAC or current_code in N8 or (current_code in N4 and token != "N"):
            continue
        if token == "O":
            _set_code(schedule, emp_id, day, None)
        elif token == "D":
            _set_code(schedule, emp_id, day, state.next_day_code())
        elif token == "N":
            code_full = state.next_night_code()
            if day == days[-1]:
                n4_code = "N4A" if code_full.endswith("A") else "N4B"
                _set_code(schedule, emp_id, day, n4_code)
            else:
                _set_code(schedule, emp_id, day, code_full)
        # иные токены игнорируем

# -------------------- Advanced shift operations --------------------

def _code(code_of, shift_key: str) -> str:
    return code_of(shift_key).upper()


def _tok_for_pair(code: str, day: date) -> str:
    upper = (code or "OFF").upper()
    if day.day == 1 and upper in NIGHT8:
        return "O"
    if upper in DAY12 or upper in DAY8:
        return "D"
    if upper in NIGHT12 or upper in NIGHT4:
        return "N"
    return "O"


def _emp_seq(schedule, code_of, emp_id: str) -> Tuple[List[date], List[Tuple[date, object, str]]]:
    dates: List[date] = []
    seq: List[Tuple[date, object, str]] = []
    for d in sorted(schedule.keys()):
        for assignment in schedule[d]:
            if assignment.employee_id != emp_id:
                continue
            code = _code(code_of, assignment.shift_key)
            dates.append(d)
            seq.append((d, assignment, code))
            break
    return dates, seq


def _fix_last_day_n4(codes: List[str]) -> None:
    if not codes:
        return
    if codes[-1] in {"NA", "NB"}:
        codes[-1] = "N4A" if codes[-1].endswith("A") else "N4B"


def _key_for_code(code: str) -> str:
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
    }.get((code or "").upper(), "off")


def _emp_code_on(schedule, code_of, emp_id: str, day: date) -> str:
    for assignment in schedule[day]:
        if assignment.employee_id == emp_id:
            return code_of(assignment.shift_key).upper()
    return "OFF"


def _swap_ab_code(code: str) -> str:
    mapping = {
        "DA": "DB",
        "DB": "DA",
        "M8A": "M8B",
        "M8B": "M8A",
        "E8A": "E8B",
        "E8B": "E8A",
        "NA": "NB",
        "NB": "NA",
        "N4A": "N4B",
        "N4B": "N4A",
    }
    return mapping.get((code or "").upper(), (code or "").upper())


def _emp_tok_on(schedule, code_of, emp_id: str, day: date) -> str:
    return _tok_for_pair(_emp_code_on(schedule, code_of, emp_id, day), day)


def _hours_for_code(code: str) -> int:
    upper = (code or "").upper()
    if upper in DAY12 or upper in NIGHT12:
        return 12
    if upper in DAY8 or upper in NIGHT8:
        return 8
    if upper in NIGHT4:
        return 4
    if upper == "VAC8":
        return 8
    return 0


def _rotate_codes(codes: List[str], i0: int, i1: int, direction: int) -> List[str]:
    updated = codes[:]
    if direction == +1:
        head = updated[i0]
        updated[i0:i1] = updated[i0 + 1 : i1 + 1]
        updated[i1] = head
    else:
        tail = updated[i1]
        updated[i0 + 1 : i1 + 1] = updated[i0:i1]
        updated[i0] = tail
    return updated


def shift_phase(schedule, code_of, emp_id: str, direction: int, window: Tuple[date, date]):
    """Сдвиг окна в начале месяца на ±1 с обновлением shift_key."""

    assert direction in (-1, +1)
    dates, seq = _emp_seq(schedule, code_of, emp_id)
    if not seq:
        return schedule, 0, False, "no-rows"

    start = 1 if seq and seq[0][2] in N8 else 0
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

    codes = [entry[2] for entry in seq]
    new_codes = _rotate_codes(codes, i0, i1, direction)

    for idx in range(i0, i1 + 1):
        if new_codes[idx] in N8 and idx != 0:
            new_codes[idx] = "NA" if new_codes[idx].endswith("A") else "NB"

    _fix_last_day_n4(new_codes)

    new_sched = copy.deepcopy(schedule)
    new_hours = 0
    old_hours = 0
    for idx, day in enumerate(dates):
        if idx == 0 and codes[0] in N8:
            continue
        old_code = codes[idx]
        new_code = new_codes[idx]
        if old_code == new_code:
            continue
        _, original_assignment, _ = seq[idx]
        if original_assignment and original_assignment.employee_id == emp_id:
            old_hours += int(getattr(original_assignment, "effective_hours", 0))
        for assignment in new_sched[day]:
            if assignment.employee_id != emp_id:
                continue
            assignment.shift_key = _key_for_code(new_code)
            value = _hours_for_code(new_code)
            assignment.effective_hours = value
            new_hours += value
            break

    hours_delta = new_hours - old_hours
    return new_sched, hours_delta, True, f"rot({direction})[{dates[i0]}..{dates[i1]}]:Δh={hours_delta}"


def _set_off(assignment) -> None:
    assignment.shift_key = "off"
    assignment.effective_hours = 0
    assignment.source = "phase_shift"


def flip_ab_on_day(schedule, code_of, emp_id: str, day: date):
    """Локальный флип A↔B на конкретный день без изменения D/N/O."""

    new_sched = copy.deepcopy(schedule)
    for assignment in new_sched[day]:
        if assignment.employee_id != emp_id:
            continue
        before = code_of(assignment.shift_key).upper()
        if day.day == 1 and before in {"N8A", "N8B"}:
            return schedule, False, "flip_ab_on_day: protected code"
        after = _swap_ab_code(before)
        if after == before:
            return schedule, False, "flip_ab_on_day: noop"
        assignment.shift_key = _key_for_code(after)
        assignment.effective_hours = _hours_for_code(after)
        assignment.source = "pair_desync"
        return new_sched, True, f"flip_ab_on_day[{emp_id}] {before}->{after} {day.isoformat()}"
    return schedule, False, "flip_ab_on_day: no row"


def phase_shift_minus_one_skip(
    schedule,
    code_of,
    emp_id: str,
    window: Tuple[date, date],
    partner_id: Optional[str] = None,
    anti_align: bool = True,
):
    """Сдвиг фазы -1 с удалением ночной смены и перешивкой хвоста."""

    new_sched = copy.deepcopy(schedule)
    days = [d for d in sorted(schedule.keys()) if window[0] <= d <= window[1]]
    days_all = sorted(schedule.keys())
    total = len(days_all)
    if not days:
        return schedule, 0, False, "phase_shift_-1: empty window"

    for day in days:
        idx = days_all.index(day)
        if idx == 0 or idx >= total - 1:
            continue

        current_code = _emp_code_on(new_sched, code_of, emp_id, day)
        if day.day == 1 and current_code in N8:
            continue
        if day == days_all[-1] and current_code in N4:
            continue

        t_prev = _emp_tok_on(new_sched, code_of, emp_id, days_all[idx - 1])
        t_curr = _emp_tok_on(new_sched, code_of, emp_id, days_all[idx])
        t_next = _emp_tok_on(new_sched, code_of, emp_id, days_all[idx + 1])
        if not (t_prev == "D" and t_curr == "N" and t_next == "O"):
            continue

        for assignment in new_sched[day]:
            if assignment.employee_id == emp_id:
                before = code_of(assignment.shift_key).upper()
                if before not in {"NA", "NB"}:
                    return schedule, 0, False, "phase_shift_-1: target is not N"
                delta_hours = -12
                _set_off(assignment)
                break
        else:
            continue

        tokens = [
            "O" if (offset % 4) in (0, 1) else ("D" if (offset % 4) == 2 else "N")
            for offset in range(0, total - idx)
        ]
        stitch_into_schedule(
            new_sched,
            code_of,
            emp_id,
            days_all[idx],
            tokens,
            partner_id=partner_id,
            anti_align=anti_align,
        )
        return new_sched, delta_hours, True, f"phase_shift_-1[{day.isoformat()}]"

    return schedule, 0, False, "phase_shift_-1: no D,N,O pattern in window"


def phase_shift_plus_one_insert_off(
    schedule,
    code_of,
    emp_id: str,
    window: Tuple[date, date],
    partner_id: Optional[str] = None,
    anti_align: bool = True,
):
    """Сдвиг фазы +1: вставляем дополнительный OFF в блоке O,O,(работа)."""

    new_sched = copy.deepcopy(schedule)
    days = [d for d in sorted(schedule.keys()) if window[0] <= d <= window[1]]
    tokens: List[Tuple[str, str, date]] = []
    for day in days:
        code = "OFF"
        for assignment in new_sched[day]:
            if assignment.employee_id == emp_id:
                code = code_of(assignment.shift_key).upper()
                break
        tokens.append((_tok_for_pair(code, day), code, day))

    for idx in range(len(tokens) - 2):
        t0, c0, d0 = tokens[idx]
        t1, c1, d1 = tokens[idx + 1]
        t2, c2, d2 = tokens[idx + 2]
        if t0 == "O" and t1 == "O" and t2 in ("D", "N"):
            if {c0, c1} & VAC:
                continue
            if d2.day == 1 and c2 in N8:
                continue

            for assignment in new_sched[d2]:
                if assignment.employee_id == emp_id:
                    before = code_of(assignment.shift_key).upper()
                    delta_hours = -_hours_for_code(before)
                    _set_off(assignment)
                    break
            else:
                continue

            days_all = sorted(new_sched.keys())
            idx2 = days_all.index(d2)
            tokens_tail = [
                "O" if (offset % 4) in (0, 3) else ("D" if (offset % 4) == 1 else "N")
                for offset in range(0, len(days_all) - idx2)
            ]
            stitch_into_schedule(
                new_sched,
                code_of,
                emp_id,
                days_all[idx2],
                tokens_tail,
                partner_id=partner_id,
                anti_align=anti_align,
            )
            return new_sched, delta_hours, True, f"phase_shift_+1[{d2.isoformat()}]"

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
    for day in days:
        token = _tok_for_pair(_emp_code_on(schedule, code_of, emp_id, day), day)
        if token == kind:
            start_day = day
            break
    if start_day is None:
        return schedule, 0, False, "flip_ab: no token"

    start_idx = days_all.index(start_day)
    tail_tokens = [
        _tok_for_pair(_emp_code_on(schedule, code_of, emp_id, day), day)
        for day in days_all[start_idx:]
    ]

    new_sched = copy.deepcopy(schedule)
    stitch_into_schedule(
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
    """Разводим офисы внутри месяца, если оба в одной фазе."""

    new_sched = copy.deepcopy(schedule)
    flips = 0
    notes: List[str] = []
    for day in sorted(new_sched.keys()):
        code_a = _emp_code_on(new_sched, code_of, emp_a, day)
        code_b = _emp_code_on(new_sched, code_of, emp_b, day)
        tok_a = _tok_for_pair(code_a, day)
        tok_b = _tok_for_pair(code_b, day)
        if tok_a != tok_b or tok_a == "O":
            continue
        if code_a.endswith("A") != code_b.endswith("A"):
            continue
        if day.day == 1 and (code_a in {"N8A", "N8B"} or code_b in {"N8A", "N8B"}):
            continue
        new_sched, ok, note = flip_ab_on_day(new_sched, code_of, emp_a, day)
        if ok:
            flips += 1
            notes.append(note)
    return new_sched, flips, notes
