from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Employee:
    id: str
    name: str
    is_trainee: bool = False
    mentor_id: Optional[str] = None
    ytd_overtime: int = 0
    seed4: int = 0


__all__ = ["Employee"]
