from __future__ import annotations

from typing import Optional

from services import db


def ensure_month(ym: str) -> int:
    return db.ensure_month(ym)


def get_month_id(ym: str) -> Optional[int]:
    row = db.query_one("SELECT id FROM months WHERE ym = ?", (ym,))
    if row:
        return int(row["id"])
    return None
