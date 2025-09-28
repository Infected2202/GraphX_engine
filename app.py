
# -*- coding: utf-8 -*-
from typing import Dict, List
from datetime import date
from pathlib import Path
from config import CONFIG
from generator import Generator, Assignment
import report
import validator
import os

if __name__ == "__main__":
    gen = Generator(CONFIG)

    # Карта кодов для отчётов
    code_map = {k: v.code for k, v in gen.shift_types.items()}
    report.set_code_map(code_map)

    carry_in = []           # переносы N8* на 1-е число
    prev_tail_by_emp: Dict[str, List[str]] = {}   # синтетический хвост для первого месяца

    out_dir = Path(os.getcwd()) / "reports"
    out_dir.mkdir(exist_ok=True)

    for idx, month_spec in enumerate(CONFIG["months"]):
        ym = month_spec["month_year"]
        # Номер месяца и 1-е число (для carry-in)
        y, m = map(int, ym.split("-"))
        first_day = date(y, m, 1)

        # --- СИНТЕТИЧЕСКИЙ ХВОСТ ТОЛЬКО ДЛЯ ПЕРВОГО МЕСЯЦА ---
        if idx == 0:
            # 28,29,30,31 июля 2025 — коды в хронологическом порядке.
            # NB: у E07 на 31-е НЕТ ночи (исправлено), переносов делаем ТОЛЬКО для E04/E08.
            prev_tail_by_emp = {
                "E01": ["OFF", "DB", "OFF", "OFF"],   # → 1 авг DAY(A)
                "E02": ["OFF", "OFF", "OFF", "DA"],   # → 1 авг NIGHT(B)
                "E03": ["DA", "OFF", "NA", "OFF"],    # → 1 авг OFF (после ночи день раньше)
                "E04": ["DA", "OFF", "OFF", "N4A"],   # → перенос N8A на 1 авг
                "E05": ["OFF", "DA", "OFF", "OFF"],   # → 1 авг DAY(B)
                "E06": ["OFF", "OFF", "OFF", "DB"],   # → 1 авг NIGHT(A)
                "E07": ["DB", "OFF", "NB", "OFF"],    # → 1 авг OFF (без переноса)
                "E08": ["DB", "OFF", "OFF", "N4B"],   # → перенос N8B на 1 авг
            }
            # Готовим carry-in N8* на 1-е число только для тех, у кого 31-го стоит N4*
            carry_in = [
                Assignment("E04", first_day, "n8_a", gen.shift_types["n8_a"].hours, source="template"),
                Assignment("E08", first_day, "n8_b", gen.shift_types["n8_b"].hours, source="template"),
            ]

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
