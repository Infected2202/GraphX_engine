"""Bridge between the legacy generator and the web database."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple, cast

from engine.domain.employee import Employee
from engine.domain.schedule import Assignment
from engine.infrastructure.config import CONFIG as BASE_CONFIG
from engine.infrastructure.production_calendar import ProductionCalendar
from engine.services.generator import Generator

from ..dao import employees_dao, schedule_dao


@dataclass(slots=True)
class GeneratedCell:
    """A single schedule cell prepared for persistence."""

    emp_id: int
    day: int
    value: str
    office: Optional[str]
    meta: Dict[str, object]


@dataclass(slots=True)
class GeneratedSchedule:
    """Structured result of the generation pipeline."""

    ym: str
    month_id: int
    day_count: int
    employee_count: int
    cells: List[GeneratedCell]

    @property
    def cell_count(self) -> int:
        return len(self.cells)


@dataclass(slots=True)
class GenerationStats:
    """Lightweight statistics returned to API clients."""

    ym: str
    employees: int
    days: int
    cells: int


class GenerationError(RuntimeError):
    """Raised when the adapter cannot produce a schedule."""


def generate_schedule(ym: str) -> GeneratedSchedule:
    """Generate a schedule matrix for the requested month without persisting it."""

    month_id = schedule_dao.ensure_month_exists(ym)
    employees = employees_dao.list_active_employees()
    if not employees:
        raise GenerationError("Нет активных сотрудников для генерации расписания")

    calendar = ProductionCalendar.load_default()
    generator = _build_generator(employees, calendar)

    prev_tail = _load_prev_tail(ym, {row["id"]: row["key"] for row in employees})

    month_spec = {"month_year": ym, "norm_hours_month": _norm_hours(calendar, ym)}
    generated = _run_generator(generator, month_spec, prev_tail)

    cells = _build_cells(generator, generated, employees)

    return GeneratedSchedule(
        ym=ym,
        month_id=month_id,
        day_count=len(generated.schedule),
        employee_count=len(generated.employees),
        cells=cells,
    )


def generate_and_store(ym: str) -> GenerationStats:
    """Generate a schedule and persist it to the database."""

    schedule = generate_schedule(ym)
    serialized = [serialize_cell(cell) for cell in schedule.cells]
    schedule_dao.replace_month_cells(schedule.month_id, serialized)
    return GenerationStats(
        ym=schedule.ym,
        employees=schedule.employee_count,
        days=schedule.day_count,
        cells=schedule.cell_count,
    )


@dataclass(slots=True)
class _RawGeneration:
    employees: List[Employee]
    schedule: Dict[date, List[Assignment]]


def _build_generator(employees: List[dict], calendar: ProductionCalendar) -> Generator:
    config = copy.deepcopy(BASE_CONFIG)
    config["employees"] = [
        {
            "id": row["key"],
            "name": row["fio"],
            "is_trainee": False,
            "mentor_id": None,
            "ytd_overtime": 0,
        }
        for row in employees
    ]
    config["months"] = []
    return Generator(config, calendar=calendar)


def _load_prev_tail(ym: str, emp_key_map: Dict[int, str]) -> Dict[str, List[str]]:
    prev_ym = _previous_month(ym)
    prev_month_id = schedule_dao.get_month_id(prev_ym)
    if prev_month_id is None:
        return {}

    rows = schedule_dao.load_month_cells(prev_month_id)
    if not rows:
        return {}

    last_days = _tail_days(rows)
    tail: Dict[str, List[Tuple[int, str]]] = {}
    for row in rows:
        day = int(row["day"])
        value = row.get("value")
        if day not in last_days or not value:
            continue
        emp_id = int(row["emp_id"])
        emp_key = emp_key_map.get(emp_id)
        if not emp_key:
            continue
        tail.setdefault(emp_key, []).append((day, value))

    return {
        emp_key: [value for _, value in sorted(entries, key=lambda item: item[0])]
        for emp_key, entries in tail.items()
    }


def _tail_days(rows: Iterable[dict]) -> List[int]:
    unique_days = sorted({int(row["day"]) for row in rows})
    return unique_days[-4:]


def _previous_month(ym: str) -> str:
    year_str, month_str = ym.split("-")
    year = int(year_str)
    month = int(month_str)
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _norm_hours(calendar: ProductionCalendar, ym: str) -> int:
    year_str, month_str = ym.split("-")
    value = calendar.norm_hours(int(year_str), int(month_str))
    return int(value) if value is not None else 0


def _run_generator(
    generator: Generator,
    month_spec: Dict[str, object],
    prev_tail_by_emp: Dict[str, List[str]],
) -> _RawGeneration:
    employees, schedule, _carry_out = generator.generate_month(
        month_spec,
        prev_tail_by_emp=prev_tail_by_emp,
        carry_in=None,
    )
    norm_hours = cast(int, month_spec.get("norm_hours_month", 0))
    ym = cast(str, month_spec["month_year"])
    generator.enforce_hours_caps(employees, schedule, norm_hours, ym)
    return _RawGeneration(employees=employees, schedule=schedule)


def _build_cells(
    generator: Generator,
    generated: _RawGeneration,
    employees: List[dict],
) -> List[GeneratedCell]:
    emp_id_by_key = {row["key"]: int(row["id"]) for row in employees}
    cells: List[GeneratedCell] = []

    for current_date, assignments in sorted(generated.schedule.items()):
        day = int(current_date.day)
        for assignment in assignments:
            emp_id = emp_id_by_key.get(assignment.employee_id)
            if emp_id is None:
                continue
            code = generator.code_of(assignment.shift_key)
            office = Generator._office_from_code(code)
            meta: Dict[str, object] = {"source": assignment.source}
            cells.append(
                GeneratedCell(
                    emp_id=emp_id,
                    day=day,
                    value=code,
                    office=office,
                    meta=meta,
                )
            )

    return cells


def serialize_cell(cell: GeneratedCell) -> Tuple[int, int, str, Optional[str], str]:
    """Prepare a generated cell for database insertion."""

    meta_json = json.dumps(cell.meta, ensure_ascii=False)
    return cell.emp_id, cell.day, cell.value, cell.office, meta_json
