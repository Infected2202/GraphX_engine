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

    # Доп. пост-правка: если перед отпуском выпала ночная смена — удалить её (OFF).
    # Применяем ко всем сотрудникам и для обоих типов отпуска (VAC8/VAC0).
    # Удаляем NA/NB и их укороченные/неполные варианты (N8*/N4*).
    from datetime import timedelta
    NIGHT_CODES = {"NA", "NB", "N8A", "N8B", "N4A", "N4B"}
    OFF_KEY = "off"
    off_st = shift_types.get(OFF_KEY)
    if not off_st:
        return
    # Индексируем расписание для быстрого доступа: (date, emp_id) -> assignment
    by_key = {}
    for d, rows in schedule.items():
        for a in rows:
            by_key[(d, a.employee_id)] = a
    for d, rows in schedule.items():
        for a in rows:
            code = shift_types[a.shift_key].code.upper()
            if code in {"VAC8", "VAC0"}:
                prev = d - timedelta(days=1)
                prev_a = by_key.get((prev, a.employee_id))
                if prev_a:
                    prev_code = shift_types[prev_a.shift_key].code.upper()
                    if prev_code in NIGHT_CODES:
                        prev_a.shift_key = OFF_KEY
                        prev_a.effective_hours = off_st.hours
                        # помечаем как авто-правку, чтобы было видно в источниках
                        prev_a.source = "autofix"
                        # если структура ассайнмента поддерживает флаг «перекраска из ночной»
                        if hasattr(prev_a, "recolored_from_night"):
                            prev_a.recolored_from_night = True
