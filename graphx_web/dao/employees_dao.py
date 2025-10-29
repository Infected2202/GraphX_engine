"""Data access helpers for employees."""

from __future__ import annotations

from typing import List

from . import db


def list_active_employees() -> List[dict]:
    """Return active employees sorted by display order."""
    connection = db.get_db()
    rows = connection.execute(
        """
        SELECT id, fio, key, office
        FROM employees
        WHERE is_active = 1
        ORDER BY fio COLLATE NOCASE
        """
    ).fetchall()
    return [dict(row) for row in rows]
