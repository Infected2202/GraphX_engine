# -*- coding: utf-8 -*-
"""
Конфигурация генерации. Все ключевые параметры вынесены сюда.
"""
from datetime import date

CONFIG = {
    # ДВА месяца: август и сентябрь 2025. Порядок важен — генерируем последовательно.
    "months": [
        {
            "month_year": "2025-08",
            "norm_hours_month": 184,
            # Отпуска (при необходимости) в виде: {"E01": [date(2025,8,12), ...]}
            "vacations": {},
        },
        {
            "month_year": "2025-09",
            "norm_hours_month": 184,
            "vacations": {},
        },
    ],

    # Политика эпохи ротации: якорь 1 января соответствующего года
    "rotation_epoch_policy": "new_year_reset",

    # Глобальные лимиты
    "monthly_overtime_max": 10,  # не более нормы + 10ч
    "yearly_overtime_max": 120,  # годовой перелимит

    # Типы смен (расширенные)
    # Коды: DA/DB/NA/NB — 12ч, M8*/E8* — 8ч, N4* — 4ч хвост на последний день месяца, N8* — 8ч хвост на 1-е число след. месяца
    "shift_types": {
        # Дневные 12ч
        "day_a":   {"code": "DA",  "office": "A", "start": "09:00", "end": "21:00", "hours": 12, "is_working": True,  "label": "Дневная 12ч — Офис A"},
        "day_b":   {"code": "DB",  "office": "B", "start": "09:00", "end": "21:00", "hours": 12, "is_working": True,  "label": "Дневная 12ч — Офис B"},
        # Ночные 12ч
        "night_a": {"code": "NA",  "office": "A", "start": "21:00", "end": "09:00", "hours": 12, "is_working": True,  "label": "Ночная 12ч — Офис A"},
        "night_b": {"code": "NB",  "office": "B", "start": "21:00", "end": "09:00", "hours": 12, "is_working": True,  "label": "Ночная 12ч — Офис B"},
        # Короткие дневные 8ч — утро/вечер
        "m8_a":    {"code": "M8A", "office": "A", "start": "09:00", "end": "18:00", "hours": 8,  "is_working": True,  "label": "Дневная 8ч (утро) — Офис A"},
        "m8_b":    {"code": "M8B", "office": "B", "start": "09:00", "end": "18:00", "hours": 8,  "is_working": True,  "label": "Дневная 8ч (утро) — Офис B"},
        "e8_a":    {"code": "E8A", "office": "A", "start": "12:00", "end": "21:00", "hours": 8,  "is_working": True,  "label": "Дневная 8ч (вечер) — Офис A"},
        "e8_b":    {"code": "E8B", "office": "B", "start": "12:00", "end": "21:00", "hours": 8,  "is_working": True,  "label": "Дневная 8ч (вечер) — Офис B"},
        # Разрез ночной
        "n4_a":    {"code": "N4A", "office": "A", "start": "21:00", "end": "00:00", "hours": 4,  "is_working": True,  "label": "Ночная 4ч (последний день) — Офис A"},
        "n4_b":    {"code": "N4B", "office": "B", "start": "21:00", "end": "00:00", "hours": 4,  "is_working": True,  "label": "Ночная 4ч (последний день) — Офис B"},
        "n8_a":    {"code": "N8A", "office": "A", "start": "00:00", "end": "09:00", "hours": 8,  "is_working": True,  "label": "Ночная 8ч (перенос на 1-е) — Офис A"},
        "n8_b":    {"code": "N8B", "office": "B", "start": "00:00", "end": "09:00", "hours": 8,  "is_working": True,  "label": "Ночная 8ч (перенос на 1-е) — Офис B"},
        # Отпуск/выходной
        "vac_wd8": {"code": "VAC8","office": None, "start": "09:00", "end": "17:00", "hours": 8,  "is_working": False, "label": "Отпуск (будний, учёт 8ч)"},
        "vac_we0": {"code": "VAC0","office": None, "start": None,    "end": None,    "hours": 0,  "is_working": False, "label": "Отпуск (выходной, 0ч)"},
        "off":     {"code": "OFF", "office": None, "start": None,    "end": None,    "hours": 0,  "is_working": False, "label": "Выходной"},
    },

    # Сотрудники (8 шт.)
    "employees": [
        {"id": "E01", "name": "Сотрудник 1", "is_trainee": False, "mentor_id": None, "ytd_overtime": 0},
        {"id": "E02", "name": "Сотрудник 2", "is_trainee": False, "mentor_id": None, "ytd_overtime": 0},
        {"id": "E03", "name": "Сотрудник 3", "is_trainee": False, "mentor_id": None, "ytd_overtime": 0},
        {"id": "E04", "name": "Сотрудник 4", "is_trainee": False, "mentor_id": None, "ytd_overtime": 0},
        {"id": "E05", "name": "Сотрудник 5", "is_trainee": False, "mentor_id": None, "ytd_overtime": 0},
        {"id": "E06", "name": "Сотрудник 6", "is_trainee": False, "mentor_id": None, "ytd_overtime": 0},
        {"id": "E07", "name": "Сотрудник 7", "is_trainee": False, "mentor_id": None, "ytd_overtime": 0},
        {"id": "E08", "name": "Сотрудник 8", "is_trainee": False, "mentor_id": None, "ytd_overtime": 0},
    ],

    # Покрытие дневных по умолчанию НЕ форсируем (чтобы не ломать паттерн на отладке)
    "coverage": {
        "require_day_a": 0,
        "require_day_b": 0,
        "trainees_count_towards_coverage": False,
    },

    # Перекраска (вариант L) выключена по умолчанию — сначала проверим паттерн
    "recolor": {
        "enabled": False,
        "max_per_employee": 2,
    },

    # Логирование артефактов: метрики/пары/события
    "logging": {
        "enabled": True,
        "format": "text",   # "text" | "jsonl" (jsonl подключим позже)
        "pairs_top": 20     # сколько верхних пар писать в лог
    },

    # Разрыв «жёстких» пар (в этом PR — включаем безопасный режим)
    "pair_breaking": {
        "enabled": False,        # включается в сценариях
        "overlap_threshold": 8,  # считать пару проблемной при >= 8 совместных дневных
        "hours_budget": 12,      # допустимый |Δчасы| на сотрудника без M8/E8
        "window_days": 6,        # окно в начале месяца, в пределах которого пробуем сдвиги
        "max_ops": 4,            # максимум применённых операций на месяц (чтобы не «перекрутить»)
        "anti_align": True,      # стремиться разъезжать офисы при шитье хвоста
        "post_desync_all": True, # пост-проход по сильным парам текущего месяца
        "fixed_pairs": [],       # опционально: жёстко заданные пары [["E01","E02"], ...]
        "intern_ids": [],        # опционально: стажёры/исключения
        "norm_by_employee": {},  # опционально: целевая норма часов
    },
}
