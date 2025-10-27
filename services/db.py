from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from flask import current_app, g

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "migrations" / "schema.sql"
SEED_PATH = Path(__file__).resolve().parent.parent / "seeds" / "seed.sql"


class DatabaseError(RuntimeError):
    """Raised when the SQLite layer encounters an unexpected error."""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = current_app.config["DATABASE"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db  # type: ignore[return-value]


def close_db(_: Any) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def executescript(script: str) -> None:
    db = get_db()
    try:
        db.executescript(script)
    except sqlite3.Error as exc:
        raise DatabaseError(str(exc)) from exc


def initialize_schema() -> None:
    script = SCHEMA_PATH.read_text(encoding="utf-8")
    executescript(script)


def seed_database() -> None:
    db = get_db()
    cursor = db.execute("SELECT COUNT(1) FROM employees")
    row = cursor.fetchone()
    if row and row[0]:
        return
    script = SEED_PATH.read_text(encoding="utf-8")
    executescript(script)


def query_one(sql: str, params: Sequence[Any] | None = None) -> sqlite3.Row | None:
    db = get_db()
    cur = db.execute(sql, params or [])
    try:
        return cur.fetchone()
    finally:
        cur.close()


def query_all(sql: str, params: Sequence[Any] | None = None) -> list[sqlite3.Row]:
    db = get_db()
    cur = db.execute(sql, params or [])
    try:
        return cur.fetchall()
    finally:
        cur.close()


def execute(sql: str, params: Sequence[Any] | None = None) -> int:
    db = get_db()
    cur = db.execute(sql, params or [])
    db.commit()
    return cur.rowcount


def executemany(sql: str, seq_of_params: Iterable[Sequence[Any]]) -> None:
    db = get_db()
    db.executemany(sql, seq_of_params)
    db.commit()


def ensure_month(ym: str) -> int:
    db = get_db()
    row = query_one("SELECT id FROM months WHERE ym = ?", (ym,))
    if row:
        return int(row["id"])
    cur = db.execute("INSERT INTO months(ym) VALUES (?)", (ym,))
    db.commit()
    return int(cur.lastrowid)


def upsert_settings(payload: dict[str, Any]) -> None:
    db = get_db()
    json_blob = json.dumps(payload, ensure_ascii=False)
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO settings(id, payload_json, updated_at) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at",
        (json_blob, now),
    )
    db.commit()


def read_settings() -> dict[str, Any]:
    row = query_one("SELECT payload_json FROM settings WHERE id = 1")
    if not row:
        return {}
    blob = row["payload_json"]
    return json.loads(blob) if blob else {}


def upsert_shift_type(key: str, payload: dict[str, Any]) -> None:
    db = get_db()
    json_blob = json.dumps(payload, ensure_ascii=False)
    db.execute(
        "INSERT INTO shift_types(key, payload_json) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET payload_json=excluded.payload_json",
        (key, json_blob),
    )
    db.commit()


def read_shift_types() -> dict[str, Any]:
    rows = query_all("SELECT key, payload_json FROM shift_types ORDER BY key")
    result: dict[str, Any] = {}
    for row in rows:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        result[str(row["key"])] = payload
    return result
