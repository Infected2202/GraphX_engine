from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services import db


def list_reports(month_id: int) -> List[Dict[str, Any]]:
    rows = db.query_all(
        "SELECT id, name, payload_json, created_at FROM reports WHERE month_id = ? ORDER BY created_at DESC",
        (month_id,),
    )
    return [
        {
            "id": int(row["id"]),
            "name": row["name"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_report(month_id: int, name: str) -> Optional[Dict[str, Any]]:
    row = db.query_one(
        "SELECT id, name, payload_json, created_at FROM reports WHERE month_id = ? AND name = ?",
        (month_id, name),
    )
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "payload": json.loads(row["payload_json"]),
        "created_at": row["created_at"],
    }


def save_report(month_id: int, name: str, payload: Dict[str, Any]) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    db.execute(
        "INSERT INTO reports(month_id, name, payload_json) VALUES (?, ?, ?) "
        "ON CONFLICT(month_id, name) DO UPDATE SET payload_json=excluded.payload_json, created_at=datetime('now')",
        (month_id, name, blob),
    )
