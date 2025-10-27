from __future__ import annotations

from typing import Any, Dict

from services import db


def get_settings() -> Dict[str, Any]:
    return db.read_settings()


def save_settings(payload: Dict[str, Any]) -> None:
    db.upsert_settings(payload)
