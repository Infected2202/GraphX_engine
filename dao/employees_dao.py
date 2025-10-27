from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services import db


def list_employees(include_inactive: bool = False) -> List[Dict[str, Any]]:
    rows = db.query_all(
        "SELECT id, fio, emp_key, office, attrs_json, is_active FROM employees"
        + ("" if include_inactive else " WHERE is_active = 1")
        + " ORDER BY fio"
    )
    return [
        {
            "id": row["id"],
            "fio": row["fio"],
            "key": row["emp_key"],
            "office": row["office"],
            "attrs": json.loads(row["attrs_json"]) if row["attrs_json"] else {},
            "is_active": bool(row["is_active"]),
        }
        for row in rows
    ]


def get_employee(emp_id: str) -> Optional[Dict[str, Any]]:
    row = db.query_one(
        "SELECT id, fio, emp_key, office, attrs_json, is_active FROM employees WHERE id = ?",
        (emp_id,),
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "fio": row["fio"],
        "key": row["emp_key"],
        "office": row["office"],
        "attrs": json.loads(row["attrs_json"]) if row["attrs_json"] else {},
        "is_active": bool(row["is_active"]),
    }


def create_employee(payload: Dict[str, Any]) -> str:
    db.execute(
        "INSERT INTO employees(id, fio, emp_key, office, attrs_json, is_active) VALUES (?, ?, ?, ?, ?, ?)",
        (
            payload["id"],
            payload["fio"],
            payload.get("key"),
            payload.get("office"),
            json.dumps(payload.get("attrs", {}), ensure_ascii=False),
            1 if payload.get("is_active", True) else 0,
        ),
    )
    return payload["id"]


def update_employee(emp_id: str, payload: Dict[str, Any]) -> int:
    return db.execute(
        "UPDATE employees SET fio = ?, emp_key = ?, office = ?, attrs_json = ?, is_active = ? WHERE id = ?",
        (
            payload["fio"],
            payload.get("key"),
            payload.get("office"),
            json.dumps(payload.get("attrs", {}), ensure_ascii=False),
            1 if payload.get("is_active", True) else 0,
            emp_id,
        ),
    )


def delete_employee(emp_id: str) -> int:
    return db.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
