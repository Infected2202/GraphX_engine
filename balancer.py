# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import date
import shifts_ops


def apply_pair_breaking(schedule, employees, norm_hours_month: int, pairs, cfg) -> Tuple[object, List[str]]:
    """
    Каркас: возвращаем исходный график без изменений + пустой список операций.
    Далее будет жадный алгоритм с вызовами shifts_ops.shift_phase().
    """
    ops_log: List[str] = []
    if not cfg.get("enabled", False):
        return schedule, ops_log
    # Здесь (в следующей итерации) будет попытка разрыва top-пар
    return schedule, ops_log
