"""Schedule aggregate used across rules and services."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Callable, Dict, Iterable, Iterator, List, MutableMapping, Optional

from .models import Assignment
from . import shift_types

CodeLookup = Callable[[str], str]


class Schedule(MutableMapping[date, List[Assignment]]):
    """A thin mapping-like wrapper over assignments grouped by day."""

    def __init__(
        self,
        assignments: Iterable[Assignment] | None = None,
        *,
        code_lookup: Optional[CodeLookup] = None,
    ) -> None:
        self._data: Dict[date, List[Assignment]] = defaultdict(list)
        self._code_lookup = code_lookup
        if assignments:
            for a in assignments:
                self.assign(a)

    # -- MutableMapping protocol -------------------------------------------------
    def __getitem__(self, key: date) -> List[Assignment]:
        return self._data.setdefault(key, [])

    def __setitem__(self, key: date, value: List[Assignment]) -> None:
        self._data[key] = value

    def __delitem__(self, key: date) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[date]:
        return iter(sorted(self._data.keys()))

    def __len__(self) -> int:
        return len(self._data)

    # -- Core helpers -------------------------------------------------------------
    @property
    def code_lookup(self) -> Optional[CodeLookup]:
        return self._code_lookup

    def with_code_lookup(self, lookup: CodeLookup) -> "Schedule":
        self._code_lookup = lookup
        return self

    def assign(self, assignment: Assignment) -> None:
        rows = self._data.setdefault(assignment.date, [])
        for idx, row in enumerate(rows):
            if row.employee_id == assignment.employee_id:
                rows[idx] = assignment
                break
        else:
            rows.append(assignment)

    def assignments_on(self, day: date) -> List[Assignment]:
        return list(self._data.get(day, ()))

    def get_assignment(self, employee_id: str, day: date) -> Optional[Assignment]:
        for record in self._data.get(day, ()):  # pragma: no branch - tiny collections
            if record.employee_id == employee_id:
                return record
        return None

    def get_code(self, employee_id: str, day: date) -> str:
        record = self.get_assignment(employee_id, day)
        if not record:
            return shift_types.OFF_CODE
        if self._code_lookup:
            return self._code_lookup(record.shift_key).upper()
        return record.shift_key.upper()

    def hours_by_employee(self) -> Dict[str, int]:
        totals: Dict[str, int] = defaultdict(int)
        for rows in self._data.values():
            for assignment in rows:
                totals[assignment.employee_id] += int(assignment.effective_hours)
        return dict(totals)

    def iter_employees(self) -> Iterator[str]:
        seen: set[str] = set()
        for rows in self._data.values():
            for assignment in rows:
                if assignment.employee_id not in seen:
                    seen.add(assignment.employee_id)
                    yield assignment.employee_id

    def pair_overlap(self, emp_a: str, emp_b: str) -> List[date]:
        overlap: List[date] = []
        for day, rows in self._data.items():
            has_a = has_b = False
            for assignment in rows:
                if assignment.employee_id == emp_a:
                    has_a = True
                elif assignment.employee_id == emp_b:
                    has_b = True
                if has_a and has_b:
                    overlap.append(day)
                    break
        return overlap

    def token_map(self, day: date | None = None) -> Dict[str, str]:
        tokens: Dict[str, str] = {}
        for employee_id in self.iter_employees():
            code = self.get_code(employee_id, day) if day else None
            if code is None:
                continue
            tokens[employee_id] = shift_types.code_to_token(code, day)
        return tokens

    def as_dict(self) -> Dict[date, List[Assignment]]:
        return {day: list(rows) for day, rows in self._data.items()}

    # -- Mutation utilities -------------------------------------------------------
    def remove_employee(self, employee_id: str) -> None:
        for day, rows in list(self._data.items()):
            new_rows = [r for r in rows if r.employee_id != employee_id]
            if new_rows:
                self._data[day] = new_rows
            else:
                self._data.pop(day, None)

    def filter_days(self, predicate: Callable[[date], bool]) -> "Schedule":
        return Schedule(
            (
                assignment
                for day, rows in self._data.items()
                if predicate(day)
                for assignment in rows
            ),
            code_lookup=self._code_lookup,
        )

    def copy(self) -> "Schedule":
        return Schedule(
            (assignment for rows in self._data.values() for assignment in rows),
            code_lookup=self._code_lookup,
        )
