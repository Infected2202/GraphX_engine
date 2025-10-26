"""Derive statistics from schedules."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Dict, Iterable, Mapping

from domain.schedule import Schedule
from domain import shift_types


def coverage_by_day(schedule: Schedule) -> Dict[date, Counter]:
    coverage: Dict[date, Counter] = {}
    for day in schedule:
        counter = Counter()
        for assignment in schedule[day]:
            code = schedule.get_code(assignment.employee_id, day)
            counter[shift_types.code_to_token(code, day)] += 1
        coverage[day] = counter
    return coverage


def hours_by_employee(schedule: Schedule) -> Dict[str, int]:
    return schedule.hours_by_employee()


def solo_days(schedule: Schedule) -> Dict[str, int]:
    solos: Dict[str, int] = defaultdict(int)
    for day in schedule:
        employees = [assignment.employee_id for assignment in schedule[day]]
        if len(employees) == 1:
            solos[employees[0]] += 1
    return dict(solos)
