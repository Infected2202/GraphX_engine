from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from services import db


def add_edits(month_id: int, edits: Iterable[Dict[str, Any]]) -> int:
    payload = [
        (
            month_id,
            edit["emp_id"],
            edit["day"],
            edit.get("new_value"),
            edit.get("new_office"),
            edit.get("op", "set"),
            json.dumps(edit, ensure_ascii=False),
        )
        for edit in edits
    ]
    if not payload:
        return 0
    db.executemany(
        "INSERT INTO draft_edits(month_id, emp_id, day, new_value, new_office, op, meta_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        payload,
    )
    return len(payload)


def list_edits(month_id: int) -> List[Dict[str, Any]]:
    rows = db.query_all(
        "SELECT id, emp_id, day, new_value, new_office, op, created_at FROM draft_edits WHERE month_id = ? ORDER BY id",
        (month_id,),
    )
    return [
        {
            "id": int(row["id"]),
            "emp_id": row["emp_id"],
            "day": int(row["day"]),
            "new_value": row["new_value"],
            "new_office": row["new_office"],
            "op": row["op"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def clear_edits(month_id: int) -> None:
    db.execute("DELETE FROM draft_edits WHERE month_id = ?", (month_id,))
