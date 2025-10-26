"""Pair balancing logic."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Tuple

from domain.schedule import Schedule

from . import pairing, shifts_ops


@dataclass
class BalanceOperation:
    employee: str
    action: str
    context: Dict[str, object]


@dataclass
class BalanceResult:
    schedule: Schedule
    operations: List[BalanceOperation]
    pair_stats_before: List[pairing.PairInfo]
    pair_stats_after: List[pairing.PairInfo]


def _night_overlap(pair: pairing.PairInfo) -> int:
    return pair.nights


def analyse_pairs(schedule: Schedule, code_lookup) -> List[pairing.PairInfo]:
    return pairing.compute_pairs(schedule, code_lookup)


def select_pair_for_shift(pairs: List[pairing.PairInfo], *, threshold: int) -> pairing.PairInfo | None:
    for pair in pairs:
        if pair.nights > threshold:
            return pair
    return None


def _shift_employee(schedule: Schedule, employee_id: str, direction: int) -> Schedule:
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")
    return shifts_ops.shift_phase(schedule, employee_id, direction)


def _choose_direction(schedule: Schedule, employee_id: str) -> int:
    totals = schedule.hours_by_employee()
    return -1 if totals.get(employee_id, 0) > 160 else 1


def apply_pair_breaking(
    schedule: Schedule,
    employees: Iterable,
    code_lookup,
    config: Dict[str, object] | None = None,
) -> BalanceResult:
    config = config or {}
    threshold = int(config.get("night_overlap_threshold", 3))

    pairs_before = analyse_pairs(schedule, code_lookup)
    target_pair = select_pair_for_shift(pairs_before, threshold=threshold)
    if not target_pair:
        return BalanceResult(schedule.copy(), [], pairs_before, pairs_before)

    emp_a, emp_b = target_pair.employees
    direction = _choose_direction(schedule, emp_b)
    balanced = _shift_employee(schedule, emp_b, direction)

    operations = [
        BalanceOperation(
            employee=emp_b,
            action="shift_phase",
            context={"direction": direction, "pair": target_pair.employees},
        )
    ]

    pairs_after = analyse_pairs(balanced, code_lookup)
    return BalanceResult(balanced, operations, pairs_before, pairs_after)
