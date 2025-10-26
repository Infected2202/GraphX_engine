"""Domain dataclasses for GraphX scheduling."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional


@dataclass(frozen=True)
class ShiftType:
    key: str
    code: str
    office: Optional[str]
    start: Optional[str]
    end: Optional[str]
    hours: int
    is_working: bool
    label: str


@dataclass
class Employee:
    id: str
    name: str
    is_trainee: bool = False
    mentor_id: Optional[str] = None
    ytd_overtime: int = 0
    seed4: int = 0


@dataclass
class Assignment:
    employee_id: str
    date: date
    shift_key: str
    effective_hours: int
    source: str
    recolored_from_night: bool = False


@dataclass
class MonthlyNorm:
    month: str
    hours_target: int
    hours_actual: Dict[str, int] = field(default_factory=dict)
    operations: list[Dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
