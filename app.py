# -*- coding: utf-8 -*-
from datetime import date
from config import CONFIG
from generator import Generator, Assignment
import report
import os

if __name__ == "__main__":
    gen = Generator(CONFIG)

    # Установим карту кодов для отчётов (из generator.shift_types)
    code_map = {k: v.code for k, v in gen.shift_types.items()}
    report.set_code_map(code_map)

    carry_in = []  # переносы N8* с прошлого месяца

    for month_spec in CONFIG["months"]:
        ym = month_spec["month_year"]
        norm = month_spec["norm_hours_month"]

        employees, schedule, carry_out = gen.generate_month(month_spec, carry_in=carry_in)

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

        # Переносим хвосты на следующий месяц
        carry_in = carry_out

    print("Готово.")