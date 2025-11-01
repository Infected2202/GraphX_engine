"""High level helpers for schedule presentation."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from ..dao import employees_dao, schedule_dao


@dataclass(slots=True)
class CellView:
    value: str
    office: Optional[str]
    css_class: str
    display: str


@dataclass(slots=True)
class EmployeeView:
    id: int
    fio: str
    key: str
    office: Optional[str]


@dataclass(slots=True)
class MonthView:
    ym: str
    days: List[int]
    employees: List[EmployeeView]
    cells: Dict[int, Dict[int, Optional[CellView]]]


class InvalidMonthFormatError(ValueError):
    """Raised when month query parameter is malformed."""


def parse_month(value: Optional[str]) -> str:
    """Validate and normalise a YYYY-MM value."""
    if not value:
        raise InvalidMonthFormatError("Month value is required")
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError as exc:  # pragma: no cover - defensive
        raise InvalidMonthFormatError("Month must be in YYYY-MM format") from exc
    return parsed.strftime("%Y-%m")


def available_months() -> List[str]:
    """Return available months sorted ascending."""
    return schedule_dao.list_months()


def ensure_month_available(ym: str) -> None:
    schedule_dao.ensure_month_exists(ym)


def build_month_view(ym: str) -> MonthView:
    month_id = schedule_dao.ensure_month_exists(ym)
    employees = [
        EmployeeView(
            id=row["id"],
            fio=row["fio"],
            key=row["key"],
            office=row.get("office"),
        )
        for row in employees_dao.list_active_employees()
    ]

    days_in_month = _days_for_month(ym)
    cells = _prepare_cells(
        days_in_month,
        [employee.id for employee in employees],
        schedule_dao.load_month_cells(month_id),
    )
    return MonthView(ym=ym, days=days_in_month, employees=employees, cells=cells)


def _days_for_month(ym: str) -> List[int]:
    year, month = (int(part) for part in ym.split("-"))
    _, num_days = calendar.monthrange(year, month)
    return list(range(1, num_days + 1))


def _prepare_cells(
    days: Iterable[int],
    employee_ids: Iterable[int],
    rows: Iterable[dict],
) -> Dict[int, Dict[int, Optional[CellView]]]:
    result: Dict[int, Dict[int, Optional[CellView]]] = {
        employee_id: {day: None for day in days} for employee_id in employee_ids
    }

    for row in rows:
        emp_id = int(row["emp_id"])
        day = int(row["day"])
        value = row.get("value")
        office = row.get("office")
        if value is None:
            continue
        css_parts = ["cell", f"cell-{value.lower()}"]
        if office:
            css_parts.append(f"office-{office.lower()}")
        display = value if office is None else f"{value} ({office})"
        result.setdefault(emp_id, {day: None for day in days})[day] = CellView(
            value=value,
            office=office,
            css_class=" ".join(css_parts),
            display=display,
        )

    return result
