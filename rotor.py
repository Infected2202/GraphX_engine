# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

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
    "OFF": "off",
}

_CODE_HOURS = {
    "DA": 12,
    "DB": 12,
    "NA": 12,
    "NB": 12,
    "OFF": 0,
}


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
        if (code in NIGHT_CODES or code in N4 or code in N8) and state.night_ab is None:
            state.night_ab = _ab_of(code)
        if state.day_ab is not None and state.night_ab is not None:
            break
    return state


def _set_assignment_code(schedule, emp_id: str, day: date, code: Optional[str]) -> None:
    for assignment in schedule[day]:
        if assignment.employee_id != emp_id:
            continue
        if code is None:
            assignment.shift_key = _CODE_TO_KEY["OFF"]
            assignment.effective_hours = _CODE_HOURS["OFF"]
        else:
            key = _CODE_TO_KEY.get(code)
            if key is None:
                return
            assignment.shift_key = key
            assignment.effective_hours = _CODE_HOURS.get(code, 0)
        assignment.source = "phase_shift"
        return


def stitch_into_schedule(schedule, code_of, emp_id: str, start_date: date, tokens: List[str]) -> None:
    days = sorted(schedule.keys())
    if start_date not in days:
        return
    start_idx = days.index(start_date)
    state = infer_state(schedule, code_of, emp_id, start_date)

    for offset, token in enumerate(tokens):
        idx = start_idx + offset
        if idx >= len(days):
            break
        day = days[idx]
        current_code = _code_on(schedule, code_of, emp_id, day)
        if current_code in VAC or current_code in N8 or current_code in N4:
            continue
        if token == "O":
            _set_assignment_code(schedule, emp_id, day, None)
        elif token == "D":
            _set_assignment_code(schedule, emp_id, day, state.next_day_code())
        elif token == "N":
            _set_assignment_code(schedule, emp_id, day, state.next_night_code())
        # непризнанные токены пропускаем
