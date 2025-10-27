from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from services import db


def fetch_matrix(month_id: int) -> List[Dict[str, Any]]:
    rows = db.query_all(
        "SELECT emp_id, day, value, office, meta_json FROM schedule_cells WHERE month_id = ? ORDER BY emp_id, day",
        (month_id,),
    )
    return [
        {
            "emp_id": row["emp_id"],
            "day": int(row["day"]),
            "value": row["value"],
            "office": row["office"],
            "meta": json.loads(row["meta_json"]) if row["meta_json"] else {},
        }
        for row in rows
    ]


def replace_month_schedule(month_id: int, entries: Iterable[Dict[str, Any]]) -> None:
    db.execute("DELETE FROM schedule_cells WHERE month_id = ?", (month_id,))
    payload = [
        (
            month_id,
            entry["emp_id"],
            entry["day"],
            entry["value"],
            entry.get("office"),
            json.dumps(entry.get("meta", {}), ensure_ascii=False),
        )
        for entry in entries
    ]
    if payload:
        db.executemany(
            "INSERT INTO schedule_cells(month_id, emp_id, day, value, office, meta_json) VALUES (?, ?, ?, ?, ?, ?)",
            payload,
        )
