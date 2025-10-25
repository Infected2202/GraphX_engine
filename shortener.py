# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence, Set, Tuple

from production_calendar import ProductionCalendar


@dataclass
class ShorteningConfig:
    day_shift_keys: Sequence[str]
    morning_short_by_office: Dict[str, str]
    evening_short_by_office: Dict[str, str]


class ShiftShortener:
    """Реализует слой сокращения дневных смен до 8 часов."""

    def __init__(
        self,
        calendar: Optional[ProductionCalendar],
        shift_types: Dict[str, "ShiftType"],
        code_of,
        config: ShorteningConfig,
    ) -> None:
        self.calendar = calendar
        self.shift_types = shift_types
        self.code_of = code_of
        self.config = config

    def apply(
        self,
        employees: List["Employee"],
        schedule: Dict[date, List["Assignment"]],
        norm_month: int,
        ym: str,
        monthly_allowance: int,
        yearly_cap: int,
    ) -> Dict[str, object]:
        monthly_cap = norm_month + monthly_allowance if norm_month else norm_month

        info: Dict[str, object] = {
            "month": ym,
            "norm_hours": norm_month,
            "monthly_allowance": monthly_allowance,
            "monthly_cap": monthly_cap,
            "yearly_cap": yearly_cap,
            "operations": [],
            "warnings": [],
        }

        hours_by_emp: Dict[str, int] = {}
        for rows in schedule.values():
            for assignment in rows:
                hours_by_emp[assignment.employee_id] = hours_by_emp.get(assignment.employee_id, 0) + int(
                    assignment.effective_hours
                )

        if norm_month <= 0:
            info["per_employee"] = {e.id: {"hours": hours_by_emp.get(e.id, 0)} for e in employees}
            return info

        eligible_dates: Set[date] = {dt for dt in schedule.keys() if self._date_allows_shortening(dt)}
        coverage_state = self._build_coverage_state(schedule)
        operations: List[Dict[str, object]] = []

        def yearly_ok(emp: "Employee", new_hours: int) -> bool:
            overtime = max(0, new_hours - norm_month)
            return (emp.ytd_overtime + overtime) <= yearly_cap if yearly_cap else True

        for emp in employees:
            if emp.id not in hours_by_emp:
                hours_by_emp[emp.id] = 0
            if (monthly_cap and hours_by_emp[emp.id] <= monthly_cap) and yearly_ok(emp, hours_by_emp[emp.id]):
                continue

            candidates: List[Tuple[date, "Assignment"]] = []
            for dt in sorted(schedule.keys()):
                if dt not in eligible_dates:
                    continue
                for assn in schedule[dt]:
                    if assn.employee_id == emp.id and assn.shift_key in self.config.day_shift_keys:
                        candidates.append((dt, assn))

            for dt, assn in candidates:
                while (
                    (monthly_cap and hours_by_emp[emp.id] > monthly_cap)
                    or (not yearly_ok(emp, hours_by_emp[emp.id]))
                ):
                    if assn.shift_key not in self.config.day_shift_keys:
                        break

                    # Требование: сокращаем только если в этот день минимум 2 дневных сотрудника.
                    # В частности, запрещаем сокращение, если текущий сотрудник единственный «дневной» в этот день.
                    # Считаем «дневными» DA/DB/M8/E8, но дополнительно проверяем, что есть хотя бы ещё один сотрудник,
                    # отличный от текущего, с дневным кодом.
                    other_day_workers = [
                        a for a in schedule[dt]
                        if a is not assn and self._is_day_code(self.code_of(a.shift_key))
                    ]
                    if len(other_day_workers) < 1:
                        break

                    chosen = self._choose_short_shift(assn, coverage_state[dt])
                    if not chosen:
                        break

                    new_key, new_code, new_cov = chosen
                    prev_key = assn.shift_key
                    prev_code = self.code_of(prev_key).upper()
                    prev_hours = int(assn.effective_hours)
                    st = self.shift_types[new_key]

                    assn.shift_key = new_key
                    assn.effective_hours = st.hours
                    if assn.source == "template":
                        assn.source = "autofix"

                    coverage_state[dt] = new_cov
                    delta = prev_hours - st.hours
                    hours_by_emp[emp.id] = hours_by_emp.get(emp.id, 0) - delta
                    operations.append(
                        {
                            "date": dt,
                            "employee_id": emp.id,
                            "from_code": prev_code,
                            "to_code": new_code,
                            "hours_delta": st.hours - prev_hours,
                        }
                    )

                    if ((monthly_cap and hours_by_emp[emp.id] <= monthly_cap) or not monthly_cap) and yearly_ok(
                        emp, hours_by_emp[emp.id]
                    ):
                        break

        warnings: List[str] = []
        per_employee: Dict[str, Dict[str, object]] = {}
        for emp in employees:
            total_hours = hours_by_emp.get(emp.id, 0)
            overtime = max(0, total_hours - norm_month)
            yearly_used = emp.ytd_overtime + overtime
            yearly_left = yearly_cap - yearly_used if yearly_cap else None
            per_employee[emp.id] = {
                "hours": total_hours,
                "overtime_month": overtime,
                "yearly_left": yearly_left,
            }
            exceeds_month = monthly_cap and total_hours > monthly_cap
            exceeds_year = yearly_cap and yearly_left is not None and yearly_left < 0
            if exceeds_month or exceeds_year:
                over_month = total_hours - norm_month
                if exceeds_year and not exceeds_month:
                    msg = (
                        f"{emp.id} — {emp.name}: превышен годовой лимит на {abs(yearly_left)}ч"
                        if yearly_left is not None
                        else f"{emp.id} — {emp.name}: превышен годовой лимит"
                    )
                else:
                    leftover = yearly_left if yearly_left is not None else "N/A"
                    msg = f"{emp.id} — {emp.name}: перелимит {over_month}ч; остаток по году {leftover}ч"
                warnings.append(msg)

        info["operations"] = operations
        info["warnings"] = warnings
        info["per_employee"] = per_employee
        return info

    def _date_allows_shortening(self, dt: date) -> bool:
        if self.calendar:
            return self.calendar.allows_shortening(dt)
        return dt.weekday() >= 5

    def _build_coverage_state(self, schedule: Dict[date, List["Assignment"]]) -> Dict[date, Dict[str, int]]:
        state: Dict[date, Dict[str, int]] = {}
        for dt, rows in schedule.items():
            cov = {"morning": 0, "evening": 0}
            for assn in rows:
                code = self.code_of(assn.shift_key).upper()
                contrib = self._coverage_contribution(code)
                cov["morning"] += contrib[0]
                cov["evening"] += contrib[1]
            state[dt] = cov
        return state

    @staticmethod
    def _coverage_contribution(code: str) -> Tuple[int, int]:
        c = (code or "").upper()
        if c in {"DA", "DB"}:
            return 1, 1
        if c.startswith("M8"):
            return 1, 0
        if c.startswith("E8"):
            return 0, 1
        return 0, 0

    def _choose_short_shift(
        self,
        assignment: "Assignment",
        coverage: Dict[str, int],
    ) -> Optional[Tuple[str, str, Dict[str, int]]]:
        current_code = self.code_of(assignment.shift_key).upper()
        cur_contrib = self._coverage_contribution(current_code)
        base_morning = coverage["morning"] - cur_contrib[0]
        base_evening = coverage["evening"] - cur_contrib[1]

        office = self.shift_types[assignment.shift_key].office
        options: List[str] = []
        morning = self.config.morning_short_by_office.get(office or "")
        evening = self.config.evening_short_by_office.get(office or "")
        if morning:
            options.append(morning)
        if evening:
            options.append(evening)

        for opt in options:
            new_code = self.code_of(opt).upper()
            contrib = self._coverage_contribution(new_code)
            next_morning = base_morning + contrib[0]
            next_evening = base_evening + contrib[1]
            if next_morning >= 1 and next_evening >= 1:
                return opt, new_code, {"morning": next_morning, "evening": next_evening}
        return None

    @staticmethod
    def _is_day_code(code: str) -> bool:
        c = (code or "").upper()
        return c in {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}


__all__ = ["ShiftShortener", "ShorteningConfig"]

