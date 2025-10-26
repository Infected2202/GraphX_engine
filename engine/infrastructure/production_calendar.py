from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Tuple, Set, Optional
import json


@dataclass(frozen=True)
class MonthlyNorm:
    year: int
    month: int
    hours: int


class ProductionCalendar:
    """Production calendar with monthly norms and holiday rules."""

    def __init__(
        self,
        monthly_norms: Dict[Tuple[int, int], int],
        off_dates: Set[date],
        working_overrides: Set[date],
    ) -> None:
        self._monthly_norms = dict(monthly_norms)
        self._off_dates = set(off_dates)
        self._working_overrides = set(working_overrides)

    @classmethod
    def from_json(cls, path: Path | str) -> "ProductionCalendar":
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        year_default: Optional[int] = payload.get("year")
        monthly_norms: Dict[Tuple[int, int], int] = {}
        raw_norms = payload.get("monthly_norm_hours", {}) or {}
        for key, value in raw_norms.items():
            if isinstance(key, str) and "-" in key:
                year_str, month_str = key.split("-", 1)
                year = int(year_str)
                month = int(month_str)
            else:
                if year_default is None:
                    raise ValueError("Monthly norms must include year when default year is absent")
                month = int(key)
                year = int(year_default)
            monthly_norms[(year, month)] = int(value)

        off_dates = {date.fromisoformat(item) for item in payload.get("off_dates", [])}
        working_overrides = {date.fromisoformat(item) for item in payload.get("working_overrides", [])}

        return cls(monthly_norms=monthly_norms, off_dates=off_dates, working_overrides=working_overrides)

    @classmethod
    def load_default(cls) -> "ProductionCalendar":
        base_dir = Path(__file__).resolve().parent
        default_path = base_dir / "data" / "production_calendar_2025.json"
        return cls.from_json(default_path)

    def norm_hours(self, year: int, month: int) -> Optional[int]:
        return self._monthly_norms.get((year, month))

    def is_off_date(self, dt: date) -> bool:
        return dt in self._off_dates

    def is_working_override(self, dt: date) -> bool:
        return dt in self._working_overrides

    def allows_shortening(self, dt: date) -> bool:
        if self.is_working_override(dt):
            return False
        if self.is_off_date(dt):
            return True
        return dt.weekday() >= 5

    def off_dates(self) -> Set[date]:
        return set(self._off_dates)

    def working_overrides(self) -> Set[date]:
        return set(self._working_overrides)
