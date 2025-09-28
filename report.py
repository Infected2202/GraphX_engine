from __future__ import annotations
from datetime import date
from typing import Dict, List
import csv

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

# Внутренняя таблица кодов — устанавливается из app через set_code_map()
_CODE_MAP: Dict[str, str] = {}


def set_code_map(code_map: Dict[str, str]):
    global _CODE_MAP
    _CODE_MAP = dict(code_map)


def _code_of(shift_key: str) -> str:
    return _CODE_MAP.get(shift_key, shift_key)


# Палитра под заданные правила
FILL_WHITE = PatternFill("solid", fgColor="FFFFFF")
FILL_GRAY = PatternFill("solid", fgColor="DDDDDD")

B_THIN = Border(
    left=Side(style="thin", color="DDDDDD"),
    right=Side(style="thin", color="DDDDDD"),
    top=Side(style="thin", color="DDDDDD"),
    bottom=Side(style="thin", color="DDDDDD"),
)

HEADER_FONT = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")


def _style_for(code: str):
    """Возвращает (Font, Fill) согласно ТЗ."""
    c = (code or "").upper()
    if c == "DA":
        return Font(color="000000"), FILL_WHITE
    if c == "DB":
        return Font(color="FF0000"), FILL_WHITE
    if c == "NA":
        return Font(color="000000"), FILL_GRAY
    if c == "NB":
        return Font(color="FF0000"), FILL_GRAY
    # Прочее
    return Font(color="008000"), FILL_WHITE


# ------------------- Публичные точки -------------------
def write_workbook(path: str, ym: str, employees: List, schedule: Dict[date, List]):
    """Совместимая точка: сохраняет XLSX с единственным листом-сеткой."""
    return write_excel_grid(path, ym, employees, schedule)


def write_excel_grid(path: str, ym: str, employees: List, schedule: Dict[date, List]):
    """Единственный лист Excel: сетка сотрудники×дни, ячейки оформлены по правилам."""
    wb = Workbook()
    ws = wb.active
    ws.title = ym
    _write_grid(ws, ym, employees, schedule)
    wb.save(path)
    return path


def write_csv_grid(path: str, ym: str, employees: List, schedule: Dict[date, List]):
    """CSV-сетка для простого анализа: первая колонка — сотрудник, первая строка — даты (числа)."""
    dates = sorted(schedule.keys())
    employees_sorted = sorted(employees, key=lambda e: e.id)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Сотрудник"] + [d.day for d in dates])
        for e in employees_sorted:
            row = [f"{e.id} — {e.name}"]
            for d in dates:
                code = ""
                for r in schedule[d]:
                    if r.employee_id == e.id:
                        code = _code_of(r.shift_key)
                        break
                row.append(code)
            w.writerow(row)
    return path


# ------------------- ГРИД -------------------

def _write_grid(ws, ym: str, employees: List, schedule: Dict[date, List]):
    # Заголовок: первая строка — номера дней; A1 — «Сотрудник»
    dates = sorted(schedule.keys())
    ws.cell(row=1, column=1, value="Сотрудник")
    for j, d in enumerate(dates, start=2):
        cell = ws.cell(row=1, column=j, value=d.day)
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = B_THIN

    # Тело
    employees_sorted = sorted(employees, key=lambda e: e.id)
    for i, e in enumerate(employees_sorted, start=2):
        c = ws.cell(row=i, column=1, value=f"{e.id} — {e.name}")
        c.font = HEADER_FONT
        c.alignment = LEFT
        c.border = B_THIN
        for j, d in enumerate(dates, start=2):
            code = ""
            for r in schedule[d]:
                if r.employee_id == e.id:
                    code = _code_of(r.shift_key)
                    break
            cell = ws.cell(row=i, column=j, value=code)
            cell.alignment = CENTER
            cell.border = B_THIN
            font, fill = _style_for(code)
            cell.font = font
            cell.fill = fill

    # Вёрстка
    ws.freeze_panes = "B2"
    ws.column_dimensions['A'].width = 28
    for col in range(2, 2 + len(dates)):
        ws.column_dimensions[get_column_letter(col)].width = 6
    # Фильтр не включаем, чтобы не вносить лишних артефактов формата
