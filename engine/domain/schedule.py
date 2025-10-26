from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List


@dataclass
class Assignment:
    employee_id: str
    date: date
    shift_key: str
    effective_hours: int
    source: str
    recolored_from_night: bool = False


Schedule = Dict[date, List[Assignment]]

__all__ = ["Assignment", "Schedule"]
