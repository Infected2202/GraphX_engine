from __future__ import annotations

import csv
from collections import defaultdict
from io import StringIO
from typing import Any, Dict, Tuple

from dao import employees_dao, months_dao, schedule_dao


def hours_report(month_ym: str) -> Dict[str, Any]:
    month_id = months_dao.ensure_month(month_ym)
    rows = schedule_dao.fetch_matrix(month_id)
    per_employee: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"hours": 0, "days": 0})
    per_office: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"hours": 0, "days": 0})
    for row in rows:
        hours = row.get("meta", {}).get("hours", 0)
        per_employee[row["emp_id"]]["hours"] += hours
        per_employee[row["emp_id"]]["days"] += 1
        office = row.get("office")
        if office:
            per_office[office]["hours"] += hours
            per_office[office]["days"] += 1
    return {
        "employees": dict(per_employee),
        "offices": dict(per_office),
        "meta": {"count": len(rows)},
    }


def export_hours_csv(month_ym: str) -> Tuple[StringIO, str]:
    report = hours_report(month_ym)
    employees_map = {emp["id"]: emp["fio"] for emp in employees_dao.list_employees(include_inactive=True)}
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["employee_id", "employee", "hours", "days"])
    for emp_id, data in sorted(report["employees"].items()):
        writer.writerow([emp_id, employees_map.get(emp_id, ""), data["hours"], data["days"]])
    buffer.seek(0)
    filename = f"hours_{month_ym}.csv"
    return buffer, filename
