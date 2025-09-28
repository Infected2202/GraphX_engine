# -*- coding: utf-8 -*-
from typing import Dict, List
from config import CONFIG
from generator import Generator
import report
import os
import validator  # новый модуль

if __name__ == "__main__":
    gen = Generator(CONFIG)

    # Установим карту кодов для отчётов (из generator.shift_types)
    code_map = {k: v.code for k, v in gen.shift_types.items()}
    report.set_code_map(code_map)

    carry_in = []  # переносы N8* с прошлого месяца
    prev_tail_by_emp: Dict[str, List[str]] = {}  # id -> [последние до 4 кода из пред. месяца]

    for idx, month_spec in enumerate(CONFIG["months"]):
        ym = month_spec["month_year"]
        norm = month_spec["norm_hours_month"]

        # Генерация месяца с учётом хвоста
        employees, schedule, carry_out = gen.generate_month(
            month_spec,
            carry_in=carry_in,
            prev_tail_by_emp=prev_tail_by_emp,
        )

        # Валидация базового слоя (паттерн/офисы/переносы)
        issues = validator.validate_baseline(ym, employees, schedule)
        if issues:
            print(f"[VALIDATOR] Обнаружены {len(issues)} несоответств.:")
            for msg in issues:
                print(" -", msg)
        else:
            print("[VALIDATOR] OK: базовый паттерн соответствует ожиданиям")

        # Текстовый отчёт в stdout
        text = report.render_text(ym, norm, CONFIG.get("monthly_overtime_max", 0), employees, schedule)
        print("" + "="*90)
        print(text)

        # Сохранение файлов в корень проекта
        base = f"schedule_{ym}"
        xlsx_path = os.path.join(os.getcwd(), f"{base}.xlsx")
        csv_grid_path = os.path.join(os.getcwd(), f"{base}_grid.csv")
        csv_long_path = os.path.join(os.getcwd(), f"{base}.csv")
        json_path = os.path.join(os.getcwd(), f"{base}.json")

        # Excel сетка (или CSV-сетка, если нет openpyxl)
        path_written = report.write_excel_grid(xlsx_path, ym, employees, schedule)
        # Дублируем сетку ещё и в CSV на всякий случай
        report.write_csv_grid(csv_grid_path, ym, employees, schedule)
        # «Длинный» формат для анализа
        report.write_csv_long(csv_long_path, employees, schedule)
        report.write_json_long(json_path, employees, schedule)

        print(f"Файлы сохранены: {path_written if path_written else csv_grid_path}, {csv_long_path}, {json_path}")

        # Подготовить хвост (последние 4 дня текущего месяца) для следующего
        prev_tail_by_emp = {}
        dates_sorted = sorted(schedule.keys())
        tail_dates = dates_sorted[-4:] if len(dates_sorted) >= 4 else dates_sorted
        for e in employees:
            tail_codes: List[str] = []
            for d in tail_dates:
                for r in schedule[d]:
                    if r.employee_id == e.id:
                        tail_codes.append(gen.code_of(r.shift_key))
                        break
            prev_tail_by_emp[e.id] = tail_codes

        # Переносим хвосты (N8*) на следующий месяц
        carry_in = carry_out

    print("Готово.")
