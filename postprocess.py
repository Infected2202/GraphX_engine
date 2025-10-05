# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date
from typing import Dict, List

# Перекраска отпусков после построения базового паттерна:
# - будние дни → VAC8 (8ч)
# - выходные → VAC0 (0ч)
# Целиком поверх уже сгенерированного расписания (не влияет на паттерн и ротацию).

def apply_vacations(schedule, vacations: Dict[str, List[date]], shift_types):
    if not vacations:
        return
    for d, rows in schedule.items():
        for i, a in enumerate(rows):
            vac_days = vacations.get(a.employee_id)
            if not vac_days or d not in vac_days:
                continue
            key = "vac_wd8" if d.weekday() < 5 else "vac_we0"
            st = shift_types[key]
            a.shift_key = key
            a.effective_hours = st.hours
            a.source = "override" if a.source == "template" else a.source
