from datetime import date
from config import CONFIG
from generator import Generator
import report
import os

if __name__ == "__main__":
    gen = Generator(CONFIG)

    # Карта кодов для отчётов
    code_map = {k: v.code for k, v in gen.shift_types.items()}
    report.set_code_map(code_map)

    carry_in = []  # переносы N8* с прошлого месяца

    for month_spec in CONFIG["months"]:
        ym = month_spec["month_year"]

        employees, schedule, carry_out = gen.generate_month(month_spec, carry_in=carry_in)

        # Сохранение XLSX-сетки и CSV-сетки
        base = f"schedule_{ym}"
        xlsx_path = os.path.join(os.getcwd(), f"{base}.xlsx")
        csv_grid_path = os.path.join(os.getcwd(), f"{base}_grid.csv")
        report.write_excel_grid(xlsx_path, ym, employees, schedule)
        report.write_csv_grid(csv_grid_path, ym, employees, schedule)
        print(f"Сохранено: {xlsx_path}, {csv_grid_path}")

        carry_in = carry_out

    print("Готово.")
