"""Atomic operations for manipulating schedules."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from domain.schedule import Schedule
from domain import shift_types


def _shift_assignments(assignments: Iterable, delta: int):
    for assignment in assignments:
        yield assignment.__class__(
            employee_id=assignment.employee_id,
            date=assignment.date + delta,
            shift_key=assignment.shift_key,
            effective_hours=assignment.effective_hours,
            source=assignment.source,
            recolored_from_night=assignment.recolored_from_night,
        )


def shift_phase(schedule: Schedule, employee_id: str, delta_days: int) -> Schedule:
    new_schedule = schedule.copy()
    affected = []
    for day in list(schedule.keys()):
        assignment = schedule.get_assignment(employee_id, day)
        if assignment:
            new_schedule[day] = [a for a in new_schedule[day] if a.employee_id != employee_id]
            affected.append(assignment)
    for assignment in _shift_assignments(affected, timedelta(days=delta_days)):
        new_schedule.assign(assignment)
    return new_schedule


def flip_office(schedule: Schedule, employee_id: str) -> Schedule:
    new_schedule = schedule.copy()
    for day in list(schedule.keys()):
        assignment = schedule.get_assignment(employee_id, day)
        if not assignment:
            continue
        code = new_schedule.get_code(employee_id, day)
        if shift_types.office_for_code(code) == "A":
            suffix = "_b"
        elif shift_types.office_for_code(code) == "B":
            suffix = "_a"
        else:
            continue
        new_shift_key = assignment.shift_key[:-2] + suffix
        new_schedule.assign(
            assignment.__class__(
                employee_id=assignment.employee_id,
                date=assignment.date,
                shift_key=new_shift_key,
                effective_hours=assignment.effective_hours,
                source="autofix",
                recolored_from_night=assignment.recolored_from_night,
            )
        )
    return new_schedule
