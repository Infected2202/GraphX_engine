# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

DAY_CODES = {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}
NIGHT_CODES = {"NA", "NB"}
N8 = {"N8A", "N8B"}
N4 = {"N4A", "N4B"}
VAC = {"VAC8", "VAC0"}

_CODE_TO_KEY = {
    "DA": "day_a",
    "DB": "day_b",
    "NA": "night_a",
    "NB": "night_b",
    "N4A": "n4_a",
    "N4B": "n4_b",
    "OFF": "off",
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
        if code is None or code == "OFF":
            assignment.shift_key = _CODE_TO_KEY["OFF"]
            assignment.effective_hours = 0
        else:
            key = _CODE_TO_KEY.get(code)
            if key is None:
                return
            assignment.shift_key = key
            if code in {"N4A", "N4B"}:
                assignment.effective_hours = 4
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
