from __future__ import annotations

import calendar
import copy
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Dict, List, Tuple

from openpyxl import Workbook

from dao import (
    calendar_dao,
    employees_dao,
    months_dao,
    reports_dao,
    schedule_dao,
    settings_dao,
)
from engine.domain.schedule import Assignment
from engine.infrastructure.config import CONFIG as BASE_CONFIG
from engine.infrastructure.production_calendar import ProductionCalendar
from engine.services.generator import Generator


def _previous_month(month_ym: str) -> str:
    year, month = map(int, month_ym.split("-"))
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _norm_hours_for_month(month_ym: str) -> int:
    entries = [row for row in calendar_dao.list_calendar_days() if row["date"].startswith(month_ym)]
    if not entries:
        year, month = map(int, month_ym.split("-"))
        return calendar.monthrange(year, month)[1] * 8
    total_minutes = sum(row.get("norm_minutes") or 0 for row in entries)
    return total_minutes // 60


def _load_settings() -> Dict[str, Any]:
    settings = settings_dao.get_settings()
    return settings or {}


def _build_config(month_ym: str) -> Dict[str, Any]:
    config = copy.deepcopy(BASE_CONFIG)
    settings = _load_settings()
    if settings:
        config.update({k: v for k, v in settings.items() if k in config})

    employees = [
        {
            "id": emp["id"],
            "name": emp["fio"],
            "is_trainee": bool(emp.get("attrs", {}).get("is_trainee", False)),
            "mentor_id": emp.get("attrs", {}).get("mentor_id"),
            "ytd_overtime": int(emp.get("attrs", {}).get("ytd_overtime", 0)),
        }
        for emp in employees_dao.list_employees(include_inactive=False)
    ]
    config["employees"] = employees

    prev_month = _previous_month(month_ym)
    config["months"] = [
        {
            "month_year": prev_month,
            "norm_hours_month": _norm_hours_for_month(prev_month),
            "vacations": {},
        },
        {
            "month_year": month_ym,
            "norm_hours_month": _norm_hours_for_month(month_ym),
            "vacations": _vacations_for_month(month_ym),
        },
    ]

    return config


def _vacations_for_month(month_ym: str) -> Dict[str, List[date]]:
    year, month = map(int, month_ym.split("-"))
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)
    vacations = defaultdict(list)
    for vac in calendar_dao.list_vacations():
        vac_start = datetime.strptime(vac["start_date"], "%Y-%m-%d").date()
        vac_end = datetime.strptime(vac["end_date"], "%Y-%m-%d").date()
        cur = max(start, vac_start)
        limit = min(end, vac_end)
        while cur <= limit:
            vacations[vac["emp_id"]].append(cur)
            cur += timedelta(days=1)
    return {k: sorted(set(v)) for k, v in vacations.items()}


def _tail_from_previous_month(generator: Generator, month_ym: str) -> Dict[str, List[str]]:
    prev_month = _previous_month(month_ym)
    month_id = months_dao.get_month_id(prev_month)
    if not month_id:
        return {}
    entries = schedule_dao.fetch_matrix(month_id)
    tail: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
    for entry in entries:
        tail[entry["emp_id"]].append((entry["day"], entry["value"]))
    result: Dict[str, List[str]] = {}
    for emp_id, items in tail.items():
        codes = [code for _, code in sorted(items, key=lambda x: x[0])][-4:]
        result[emp_id] = codes
    return result


def _assignments_from_tail(generator: Generator, month_ym: str) -> List[Assignment]:
    prev_month = _previous_month(month_ym)
    month_id = months_dao.get_month_id(prev_month)
    if not month_id:
        return []
    entries = schedule_dao.fetch_matrix(month_id)
    if not entries:
        return []
    by_emp_day = defaultdict(dict)
    for entry in entries:
        by_emp_day[entry["emp_id"]][entry["day"]] = entry
    year, month = map(int, prev_month.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    carry: List[Assignment] = []
    code_map = {v.code.upper(): key for key, v in generator.shift_types.items()}
    for emp_id, mapping in by_emp_day.items():
        record = mapping.get(last_day)
        if not record:
            continue
        code = (record.get("value") or "").upper()
        if code in {"N4A", "N4B"}:
            next_month = 1 if month == 12 else month + 1
            next_year = year + 1 if month == 12 else year
            key = code_map.get("N8A" if code.endswith("A") else "N8B")
            if key:
                shift = generator.shift_types[key]
                carry.append(
                    Assignment(
                        emp_id,
                        date(next_year, next_month, 1),
                        key,
                        shift.hours,
                        source="carry_in",
                    )
                )
    return carry


def generate_schedule(month_ym: str) -> Dict[str, Any]:
    config = _build_config(month_ym)
    production_calendar = ProductionCalendar.load_default()
    generator = Generator(config, calendar=production_calendar)
    tail = _tail_from_previous_month(generator, month_ym)
    carry = _assignments_from_tail(generator, month_ym)

    month_spec = next(ms for ms in config["months"] if ms["month_year"] == month_ym)
    employees, schedule_map, _ = generator.generate_month(month_spec, carry_in=carry, prev_tail_by_emp=tail)
    norm_hours = month_spec.get("norm_hours_month") or _norm_hours_for_month(month_ym)
    generator.enforce_hours_caps(employees, schedule_map, norm_hours, month_ym)

    code_map = {shift_key: shift.code for shift_key, shift in generator.shift_types.items()}

    rows: List[Dict[str, Any]] = []
    for day, assignments in schedule_map.items():
        for assignment in assignments:
            code = code_map.get(assignment.shift_key, assignment.shift_key).upper()
            office = "A" if code.endswith("A") else ("B" if code.endswith("B") else None)
            rows.append(
                {
                    "emp_id": assignment.employee_id,
                    "day": day.day,
                    "value": code,
                    "office": office,
                    "meta": {
                        "shift_key": assignment.shift_key,
                        "hours": assignment.effective_hours,
                        "source": assignment.source,
                    },
                }
            )

    month_id = months_dao.ensure_month(month_ym)
    schedule_dao.replace_month_schedule(month_id, rows)

    report_payload = _compute_hours_report(rows)
    reports_dao.save_report(month_id, "hours", report_payload)

    return {"rows": len(rows), "employees": len(employees)}


def _compute_hours_report(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    totals: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"hours": 0, "days": 0})
    for row in rows:
        totals[row["emp_id"]]["hours"] += row["meta"].get("hours", 0)
        totals[row["emp_id"]]["days"] += 1
    return {emp_id: data for emp_id, data in totals.items()}


def export_xlsx(month_ym: str) -> Tuple[BytesIO, str]:
    data = schedule_dao.fetch_matrix(months_dao.ensure_month(month_ym))
    employees = employees_dao.list_employees()
    year, month = map(int, month_ym.split("-"))
    days = calendar.monthrange(year, month)[1]
    grid: Dict[str, Dict[int, str]] = defaultdict(dict)
    for row in data:
        grid[row["emp_id"]][row["day"]] = row["value"]

    wb = Workbook()
    ws = wb.active
    ws.title = month_ym
    ws.append(["Employee"] + [str(i) for i in range(1, days + 1)])
    employees_sorted = sorted(employees, key=lambda e: e["id"])
    for emp in employees_sorted:
        row = [f"{emp['id']} — {emp['fio']}"]
        for day in range(1, days + 1):
            row.append(grid.get(emp["id"], {}).get(day, ""))
        ws.append(row)

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"schedule_{month_ym}.xlsx"
    return stream, filename
