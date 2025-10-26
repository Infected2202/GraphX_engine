"""Simple shift shortening logic."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from domain.models import Assignment
from domain.schedule import Schedule
from domain import shift_types


@dataclass
class ShorteningOperation:
    employee_id: str
    date: str
    from_hours: int
    to_hours: int


def shorten(schedule: Schedule, *, max_hours: int) -> List[ShorteningOperation]:
    operations: List[ShorteningOperation] = []
    for day in list(schedule.keys()):
        rows = schedule[day]
        for idx, assignment in enumerate(rows):
            hours = shift_types.hours_for_code(schedule.get_code(assignment.employee_id, day))
            if hours <= max_hours:
                continue
            new_assignment = Assignment(
                employee_id=assignment.employee_id,
                date=assignment.date,
                shift_key=assignment.shift_key,
                effective_hours=max_hours,
                source="shorten",
                recolored_from_night=assignment.recolored_from_night,
            )
            rows[idx] = new_assignment
            operations.append(
                ShorteningOperation(
                    employee_id=assignment.employee_id,
                    date=day.isoformat(),
                    from_hours=hours,
                    to_hours=max_hours,
                )
            )
    return operations
