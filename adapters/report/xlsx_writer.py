"""Excel report writer."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from domain.models import Employee
from domain.schedule import Schedule


HEADER_FONT = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center")


def write_grid(path: str | Path, schedule: Schedule, employees: Sequence[Employee], *, title: str | None = None) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = title or "Schedule"

    dates = list(schedule)
    ws.cell(row=1, column=1, value="Employee").font = HEADER_FONT
    for idx, day in enumerate(dates, start=2):
        cell = ws.cell(row=1, column=idx, value=day.isoformat())
        cell.font = HEADER_FONT
        cell.alignment = CENTER

    for row_idx, employee in enumerate(employees, start=2):
        ws.cell(row=row_idx, column=1, value=f"{employee.id} {employee.name}").font = HEADER_FONT
        for col_idx, day in enumerate(dates, start=2):
            cell = ws.cell(row=row_idx, column=col_idx, value=schedule.get_code(employee.id, day))
            cell.alignment = CENTER

    path = Path(path)
    wb.save(path)
    return path
