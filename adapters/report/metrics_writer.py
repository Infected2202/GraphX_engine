"""Metrics exporters for CSV reports."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Sequence

from domain.models import Employee
from domain.schedule import Schedule
from domain import shift_types


def write_employee_metrics(path: str | Path, schedule: Schedule, employees: Sequence[Employee]) -> Path:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["employee_id", "employee", "hours", "days", "nights", "offs"])
        for employee in employees:
            hours = 0
            days = nights = offs = 0
            for day in schedule:
                assignment = schedule.get_assignment(employee.id, day)
                if not assignment:
                    continue
                code = schedule.get_code(employee.id, day)
                token = shift_types.code_to_token(code, day)
                hours += assignment.effective_hours
                if token == "D":
                    days += 1
                elif token == "N":
                    nights += 1
                else:
                    offs += 1
            writer.writerow([employee.id, employee.name, hours, days, nights, offs])
    return path


def write_day_metrics(path: str | Path, schedule: Schedule) -> Path:
    path = Path(path)
    dates = list(schedule)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "D", "N", "O"])
        for day in dates:
            counter = Counter()
            for assignment in schedule[day]:
                code = schedule.get_code(assignment.employee_id, day)
                counter[shift_types.code_to_token(code, day)] += 1
            writer.writerow([day.isoformat(), counter.get("D", 0), counter.get("N", 0), counter.get("O", 0)])
    return path
