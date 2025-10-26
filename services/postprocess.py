"""Post-processing utilities for generated schedules."""
from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, Mapping

from domain.models import Assignment, ShiftType
from domain.schedule import Schedule


def _coerce_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _vacation_shift(shift_types: Mapping[str, ShiftType]) -> ShiftType | None:
    for shift in shift_types.values():
        if shift.code.upper().startswith("VAC"):
            return shift
    return None


def apply_vacations(schedule: Schedule, vacations: Mapping[str, Iterable], shift_types: Mapping[str, ShiftType]) -> None:
    shift = _vacation_shift(shift_types)
    if not shift:
        return
    for employee_id, days in vacations.items():
        for value in days:
            day = _coerce_date(value)
            schedule.assign(
                Assignment(
                    employee_id=employee_id,
                    date=day,
                    shift_key=shift.key,
                    effective_hours=shift.hours,
                    source="vacation",
                )
            )


def enforce_hours(schedule: Schedule, *, max_hours: int) -> None:
    for day in schedule:
        for assignment in schedule[day]:
            if assignment.effective_hours > max_hours:
                assignment.effective_hours = max_hours
