"""SQLite repository for storing schedules."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from domain.models import Assignment
from domain.schedule import Schedule


class ScheduleRepository:
    def __init__(self, path: str | Path = "graphx.db") -> None:
        self.path = Path(path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assignments (
                    month TEXT NOT NULL,
                    day TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    shift_key TEXT NOT NULL,
                    hours INTEGER NOT NULL,
                    source TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_month(self, month: str, schedule: Schedule) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM assignments WHERE month = ?", (month,))
            rows = [
                (month, day.isoformat(), assignment.employee_id, assignment.shift_key, assignment.effective_hours, assignment.source)
                for day in schedule
                for assignment in schedule[day]
            ]
            conn.executemany(
                "INSERT INTO assignments(month, day, employee_id, shift_key, hours, source) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

    def load_month(self, month: str, *, code_lookup: Optional[Callable[[str], str]] = None) -> Schedule:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT day, employee_id, shift_key, hours, source FROM assignments WHERE month = ? ORDER BY day",
                (month,),
            )
            assignments = [
                Assignment(
                    employee_id=row[1],
                    date=date.fromisoformat(row[0]),
                    shift_key=row[2],
                    effective_hours=int(row[3]),
                    source=row[4],
                )
                for row in cursor
            ]
        schedule = Schedule(assignments, code_lookup=code_lookup)
        return schedule
