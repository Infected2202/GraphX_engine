from __future__ import annotations

from typing import Any, Dict, List, Optional

from services import db


def list_calendar_days() -> List[Dict[str, Any]]:
    rows = db.query_all("SELECT date, day_type, norm_minutes FROM calendar_days ORDER BY date")
    return [
        {
            "date": row["date"],
            "day_type": row["day_type"],
            "norm_minutes": row["norm_minutes"],
        }
        for row in rows
    ]


def upsert_calendar_day(date_str: str, day_type: str, norm_minutes: Optional[int]) -> None:
    db.execute(
        "INSERT INTO calendar_days(date, day_type, norm_minutes) VALUES (?, ?, ?) "
        "ON CONFLICT(date) DO UPDATE SET day_type=excluded.day_type, norm_minutes=excluded.norm_minutes",
        (date_str, day_type, norm_minutes),
    )


def delete_calendar_day(date_str: str) -> int:
    return db.execute("DELETE FROM calendar_days WHERE date = ?", (date_str,))


def list_vacations(emp_id: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = "SELECT id, emp_id, start_date, end_date, kind FROM vacations"
    params: list[Any] = []
    if emp_id:
        sql += " WHERE emp_id = ?"
        params.append(emp_id)
    sql += " ORDER BY start_date"
    rows = db.query_all(sql, params)
    return [
        {
            "id": int(row["id"]),
            "emp_id": row["emp_id"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "kind": row["kind"],
        }
        for row in rows
    ]


def add_vacation(payload: Dict[str, Any]) -> int:
    conn = db.get_db()
    cursor = conn.execute(
        "INSERT INTO vacations(emp_id, start_date, end_date, kind) VALUES (?, ?, ?, ?)",
        (
            payload["emp_id"],
            payload["start_date"],
            payload["end_date"],
            payload.get("kind", "paid"),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def delete_vacation(vacation_id: int) -> int:
    return db.execute("DELETE FROM vacations WHERE id = ?", (vacation_id,))
