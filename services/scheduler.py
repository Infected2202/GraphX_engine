"""High level orchestration for schedule generation."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Tuple

from domain.models import Assignment, Employee, ShiftType
from domain.schedule import Schedule

from rules import balancer, rotor, shortener
from rules.pairing import PairInfo
from services import postprocess


@dataclass
class GenerationStats:
    month: str
    shorten_operations: List[shortener.ShorteningOperation]
    balance_operations: List[balancer.BalanceOperation]
    pair_stats_before: List[PairInfo]
    pair_stats_after: List[PairInfo]


class SchedulerService:
    def __init__(self, config: Dict):
        self.config = config
        self.shift_types: Dict[str, ShiftType] = {
            key: ShiftType(
                key=key,
                code=spec["code"],
                office=spec.get("office"),
                start=spec.get("start"),
                end=spec.get("end"),
                hours=int(spec["hours"]),
                is_working=bool(spec.get("is_working", True)),
                label=spec.get("label", key),
            )
            for key, spec in config["shift_types"].items()
        }

    # ------------------------------------------------------------------
    def code_of(self, shift_key: str) -> str:
        return self.shift_types[shift_key].code

    def _pattern_for(self, month_config: Dict) -> List[str]:
        pattern = month_config.get("pattern")
        if pattern:
            return list(pattern)
        return list(self.config.get("default_pattern", []))

    def _month_meta(self, ym: str) -> Tuple[int, int, int]:
        year, month = (int(part) for part in ym.split("-"))
        _, days = calendar.monthrange(year, month)
        return year, month, days

    def _build_schedule(self, ym: str, employees: Iterable[Employee], month_config: Dict) -> Schedule:
        year, month, days_in_month = self._month_meta(ym)
        pattern = self._pattern_for(month_config)
        rotation = month_config.get("rotation", {})
        schedule = Schedule(code_lookup=self.code_of)
        start = date(year, month, 1)
        if not pattern:
            pattern = ["off"]
        for index, employee in enumerate(employees):
            offset = int(rotation.get(employee.id, index))
            for day, shift_key in rotor.sequence_for_month(start, days_in_month, pattern, shift=offset):
                shift_type = self.shift_types[shift_key]
                schedule.assign(
                    Assignment(
                        employee_id=employee.id,
                        date=day,
                        shift_key=shift_key,
                        effective_hours=shift_type.hours,
                        source="auto",
                    )
                )
        return schedule

    # ------------------------------------------------------------------
    def generate_month(self, month_config: Dict, employees: Iterable[Employee]) -> Tuple[Schedule, GenerationStats]:
        ym = month_config["month"]
        schedule = self._build_schedule(ym, employees, month_config)

        postprocess.apply_vacations(schedule, month_config.get("vacations", {}), self.shift_types)

        shorten_cfg = self.config.get("shortener", {})
        max_hours = int(month_config.get("max_hours", shorten_cfg.get("max_hours", 12)))
        shorten_ops = shortener.shorten(schedule, max_hours=max_hours)

        balance_cfg = {**self.config.get("balancer", {}), **month_config.get("balancer", {})}
        balance_result = balancer.apply_pair_breaking(schedule, employees, self.code_of, balance_cfg)
        schedule = balance_result.schedule

        stats = GenerationStats(
            month=ym,
            shorten_operations=shorten_ops,
            balance_operations=balance_result.operations,
            pair_stats_before=balance_result.pair_stats_before,
            pair_stats_after=balance_result.pair_stats_after,
        )
        return schedule, stats


__all__ = ["SchedulerService", "GenerationStats"]
