"""Data access for schedule cells."""

from __future__ import annotations

from typing import List, Optional

from . import db


class MonthNotFoundError(Exception):
    """Raised when the requested month is missing."""


def get_month_id(ym: str) -> Optional[int]:
    connection = db.get_db()
    row = connection.execute("SELECT id FROM months WHERE ym = ?", (ym,)).fetchone()
    return int(row["id"]) if row else None


def list_months() -> List[str]:
    connection = db.get_db()
    rows = connection.execute("SELECT ym FROM months ORDER BY ym").fetchall()
    return [row["ym"] for row in rows]


def load_month_cells(month_id: int) -> List[dict]:
    connection = db.get_db()
    rows = connection.execute(
        """
        SELECT emp_id, day, value, office, meta_json
        FROM schedule_cells
        WHERE month_id = ?
        ORDER BY emp_id, day
        """,
        (month_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def ensure_month_exists(ym: str) -> int:
    month_id = get_month_id(ym)
    if month_id is None:
        raise MonthNotFoundError(f"Month {ym} is not present in the database")
    return month_id
