
# -*- coding: utf-8 -*-
from typing import Dict, List
from pathlib import Path
from config import CONFIG
from generator import Generator
import report
import validator
import os

if __name__ == "__main__":
    gen = Generator(CONFIG)

    # Карта кодов для отчётов
    code_map = {k: v.code for k, v in gen.shift_types.items()}
    report.set_code_map(code_map)

    carry_in = []            # переносы N8* с прошлого месяца
    prev_tail_by_emp: Dict[str, List[str]] = {}  # id -> [последние до 4 кода из пред. месяца]

    out_dir = Path(os.getcwd()) / "reports"
    out_dir.mkdir(exist_ok=True)

    for month_spec in CONFIG["months"]:
        ym = month_spec["month_year"]

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

        # Сохранение в каталог reports/
        base = f"schedule_{ym}"
        xlsx_path = out_dir / f"{base}.xlsx"
        csv_grid_path = out_dir / f"{base}_grid.csv"
        report.write_workbook(str(xlsx_path), ym, employees, schedule)
        report.write_csv_grid(str(csv_grid_path), ym, employees, schedule)
        print(f"Сохранено: {xlsx_path}, {csv_grid_path}")

        # подготовка хвоста (последние 4 дня) для следующего месяца
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

        carry_in = carry_out
