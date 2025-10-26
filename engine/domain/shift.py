from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Shift keys (match configuration keys)
DAY_A = "day_a"
DAY_B = "day_b"
NIGHT_A = "night_a"
NIGHT_B = "night_b"
M8_A = "m8_a"
M8_B = "m8_b"
E8_A = "e8_a"
E8_B = "e8_b"
N4_A = "n4_a"
N4_B = "n4_b"
N8_A = "n8_a"
N8_B = "n8_b"
VAC_WD8 = "vac_wd8"
VAC_WE0 = "vac_we0"
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
