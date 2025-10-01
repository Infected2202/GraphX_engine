# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
from datetime import date, timedelta

# В этом PR — только каркас. Реальную логику сдвига подключим позже.
# Контракт на будущее:
#   shift_phase(schedule, emp_id, direction, window) -> (schedule', hours_delta, ok, note)


def shift_phase(schedule, emp_id: str, direction: int, window: Tuple[date,date]):
    """
    Каркас: пока ничего не меняем, только возвращаем флаг ok=False.
    direction: +1 или -1
    window: (d0, d1) — рабочее окно внутри месяца
    """
    return schedule, 0, False, "not-implemented"
