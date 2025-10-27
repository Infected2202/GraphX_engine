from __future__ import annotations

from typing import Any, Dict

from services import db


def get_shift_types() -> Dict[str, Any]:
    return db.read_shift_types()


def save_shift_types(payload: Dict[str, Any]) -> None:
    for key, value in payload.items():
        db.upsert_shift_type(key, value)
