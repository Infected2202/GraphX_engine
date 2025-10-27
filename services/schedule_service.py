from __future__ import annotations

import calendar
from collections import defaultdict
from typing import Any, Dict, Iterable, List

from dao import draft_dao, employees_dao, months_dao, schedule_dao, shift_types_dao


def get_matrix(month_ym: str) -> Dict[str, Any]:
    month_id = months_dao.ensure_month(month_ym)
    entries = schedule_dao.fetch_matrix(month_id)
    matrix: Dict[str, Dict[int, Dict[str, Any]]] = defaultdict(dict)
    for entry in entries:
        matrix[entry["emp_id"]][entry["day"]] = {
            "value": entry["value"],
            "office": entry.get("office"),
            "meta": entry.get("meta", {}),
        }
    year, month = map(int, month_ym.split("-"))
    days = calendar.monthrange(year, month)[1]
    return {
        "month": month_ym,
        "days": days,
        "employees": employees_dao.list_employees(),
        "matrix": {emp_id: dict(days_map) for emp_id, days_map in matrix.items()},
        "draft": draft_dao.list_edits(month_id),
        "shift_types": shift_types_dao.get_shift_types(),
    }


def apply_draft(month_ym: str, edits: Iterable[Dict[str, Any]]) -> int:
    month_id = months_dao.ensure_month(month_ym)
    return draft_dao.add_edits(month_id, list(edits))


def commit_draft(month_ym: str) -> int:
    month_id = months_dao.ensure_month(month_ym)
    entries = schedule_dao.fetch_matrix(month_id)
    draft_entries = draft_dao.list_edits(month_id)
    if not draft_entries:
        return 0

    matrix: Dict[tuple[str, int], Dict[str, Any]] = {
        (entry["emp_id"], entry["day"]): {
            "value": entry["value"],
            "office": entry.get("office"),
            "meta": entry.get("meta", {}),
        }
        for entry in entries
    }

    for edit in draft_entries:
        key = (edit["emp_id"], edit["day"])
        target = matrix.setdefault(key, {"value": None, "office": None, "meta": {}})
        if edit.get("new_value") is not None:
            target["value"] = edit["new_value"]
        if edit.get("new_office") is not None:
            target["office"] = edit["new_office"]
        meta = target.setdefault("meta", {})
        meta.setdefault("ops", []).append(edit["op"])

    schedule_rows: List[Dict[str, Any]] = []
    for (emp_id, day), payload in sorted(matrix.items(), key=lambda x: (x[0][0], x[0][1])):
        if not payload.get("value"):
            continue
        schedule_rows.append(
            {
                "emp_id": emp_id,
                "day": day,
                "value": payload["value"],
                "office": payload.get("office"),
                "meta": payload.get("meta", {}),
            }
        )

    schedule_dao.replace_month_schedule(month_id, schedule_rows)
    draft_dao.clear_edits(month_id)
    return len(draft_entries)
