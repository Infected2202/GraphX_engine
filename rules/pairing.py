"""Pair overlap helpers for schedules."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import combinations
from typing import Callable, Dict, Iterable, List, Tuple

from domain import shift_types
from domain.schedule import Schedule

CodeLookup = Callable[[str], str]


@dataclass
class PairInfo:
    employees: Tuple[str, str]
    overlap: int
    nights: int


def _is_night(code: str, day: date) -> bool:
    token = shift_types.code_to_token(code, day)
    return token == "N"



def compute_pairs(schedule: Schedule, code_lookup: CodeLookup | None = None) -> List[PairInfo]:
    lookup = code_lookup or schedule.code_lookup or (lambda key: key)
    employees = sorted(set(schedule.iter_employees()))
    pairs: List[PairInfo] = []
    for emp_a, emp_b in combinations(employees, 2):
        overlap = 0
        nights = 0
        for day in schedule:
            assignment_a = schedule.get_assignment(emp_a, day)
            assignment_b = schedule.get_assignment(emp_b, day)
            if not assignment_a or not assignment_b:
                continue
            code_a = lookup(assignment_a.shift_key)
            code_b = lookup(assignment_b.shift_key)
            token_a = shift_types.code_to_token(code_a, day)
            token_b = shift_types.code_to_token(code_b, day)
            if "O" in (token_a, token_b):
                continue
            overlap += 1
            if token_a == token_b == "N":
                nights += 1
        if overlap:
            pairs.append(PairInfo((emp_a, emp_b), overlap, nights))
    return sorted(pairs, key=lambda p: (-p.nights, -p.overlap, p.employees))


def pair_matrix(schedule: Schedule) -> Dict[Tuple[str, str], int]:
    matrix: Dict[Tuple[str, str], int] = {}
    for pair in compute_pairs(schedule, schedule.code_lookup or (lambda key: key)):
        matrix[pair.employees] = pair.overlap
    return matrix
