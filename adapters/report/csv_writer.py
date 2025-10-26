"""CSV report helpers."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Sequence

from domain.models import Employee
from domain.schedule import Schedule


def write_grid(path: str | Path, schedule: Schedule, employees: Sequence[Employee]) -> Path:
    path = Path(path)
    dates = list(schedule)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["employee"] + [day.isoformat() for day in dates])
        for employee in employees:
            row = [f"{employee.id} {employee.name}"]
            for day in dates:
                row.append(schedule.get_code(employee.id, day))
            writer.writerow(row)
    return path
