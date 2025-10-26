from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DAY_A, DAY_B = "day_a", "day_b"
NIGHT_A, NIGHT_B = "night_a", "night_b"
M8_A, M8_B = "m8_a", "m8_b"
E8_A, E8_B = "e8_a", "e8_b"
N4_A, N4_B = "n4_a", "n4_b"
N8_A, N8_B = "n8_a", "n8_b"
VAC_WD8, VAC_WE0 = "vac_wd8", "vac_we0"
OFF = "off"


@dataclass
class ShiftType:
    key: str
    code: str
    office: Optional[str]
    start: Optional[str]
    end: Optional[str]
    hours: int
    is_working: bool
    label: str


__all__ = [
    "ShiftType",
    "DAY_A",
    "DAY_B",
    "NIGHT_A",
    "NIGHT_B",
    "M8_A",
    "M8_B",
    "E8_A",
    "E8_B",
    "N4_A",
    "N4_B",
    "N8_A",
    "N8_B",
    "VAC_WD8",
    "VAC_WE0",
    "OFF",
]
