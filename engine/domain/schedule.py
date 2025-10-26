from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Assignment:
    employee_id: str
    date: date
    shift_key: str
    effective_hours: int
    source: str  # 'template' | 'autofix' | 'override'
    recolored_from_night: bool = False
