# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date
from typing import Dict, List, Tuple
import csv
import json

try:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    HAS_XLSX = True
except Exception:
    HAS_XLSX = False

# --------- Текстовый отчёт ---------

def render_text(ym: str, norm: int, monthly_overtime_max: int, employees: List, schedule: Dict[date, List]) -> str:
    name_of = {e.id: e.name for e in employees}
    lines: List[str] = []
    lines.append(f"ГРАФИК {ym} (норма {norm} ч, допуск +{monthly_overtime_max} ч)")
    lines.append("Дата       День | DA | DB | NA | NB | Прочее" + "-"*78)

    def fmt(lst: List[str]) -> str:
        return ", ".join(lst) if lst else "—"

    for d in sorted(schedule.keys()):
        rows = schedule[d]
        da = [name_of[r.employee_id] for r in rows if r.shift_key == 'day_a']
        db = [name_of[r.employee_id] for r in rows if r.shift_key == 'day_b']
        na = [name_of[r.employee_id] for r in rows if r.shift_key == 'night_a']
        nb = [name_of[r.employee_id] for r in rows if r.shift_key == 'night_b']
        other = []
        for r in rows:
            if r.shift_key in ('day_a','day_b','night_a','night_b'):
                continue
            code = _code_of(r.shift_key)
            other.append(f"{name_of[r.employee_id]}:{code}")
        wdn = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"][d.weekday()]
        lines.append(f"{d.isoformat()} {wdn:>2} | {fmt(da)} | {fmt(db)} | {fmt(na)} | {fmt(nb)} | {fmt(other)}")

    # Итоги
    lines.append("ИТОГИ ПО СОТРУДНИКАМ" + "-"*78)
    def sum_hours(eid: str) -> int:
        return sum(r.effective_hours for rows in schedule.values() for r in rows if r.employee_id == eid)
    def count_kind(eid: str, kinds: Tuple[str, ...]) -> int:
        return sum(1 for rows in schedule.values() for r in rows if r.employee_id == eid and r.shift_key in kinds)
    def count_recolors(eid: str) -> int:
        return sum(1 for rows in schedule.values() for r in rows if r.employee_id == eid and getattr(r, 'recolored_from_night', False))

    for e in employees:
        h = sum_hours(e.id)
        days_cnt = count_kind(e.id, ('day_a','day_b','m8_a','m8_b','e8_a','e8_b'))
        nights_cnt = count_kind(e.id, ('night_a','night_b','n4_a','n4_b','n8_a','n8_b'))
        short_cnt = count_kind(e.id, ('m8_a','m8_b','e8_a','e8_b'))
        vac8_cnt = count_kind(e.id, ('vac_wd8',))
        vac0_cnt = count_kind(e.id, ('vac_we0',))
        rec_cnt = count_recolors(e.id)
        lines.append(f"{e.name} ({e.id}): часов={h}, дней={days_cnt} (8ч={short_cnt}), ночей={nights_cnt}, отпуск8={vac8_cnt}, отпуск0={vac0_cnt}, перекрасок={rec_cnt}")

    return "".join(lines)

# Внутренняя таблица кодов — заполняется извне через set_code_map()
_CODE_MAP: Dict[str,str] = {}

def set_code_map(code_map: Dict[str,str]):
    global _CODE_MAP
    _CODE_MAP = dict(code_map)

def _code_of(shift_key: str) -> str:
    return _CODE_MAP.get(shift_key, shift_key)

# --------- Excel-сетка (сотрудники×даты) ---------

def write_excel_grid(path: str, ym: str, employees: List, schedule: Dict[date, List]):
    if not HAS_XLSX:
        # Фолбэк: CSV в том же формате «сетка»
        return write_csv_grid(path.replace('.xlsx', '.csv'), ym, employees, schedule)

    wb = Workbook()
    ws = wb.active
    ws.title = ym

    # Заголовки столбцов: даты
    dates = sorted(schedule.keys())
    ws.cell(row=1, column=1, value="Сотрудник / Дата")
    for j, d in enumerate(dates, start=2):
        ws.cell(row=1, column=j, value=d.isoformat())

    # Строки: сотрудники
    employees_sorted = sorted(employees, key=lambda e: e.id)
    for i, e in enumerate(employees_sorted, start=2):
        ws.cell(row=i, column=1, value=f"{e.name} ({e.id})")
        for j, d in enumerate(dates, start=2):
            rows = schedule[d]
            # Ищем назначение для этого сотрудника в этот день
            code = ""
            for r in rows:
                if r.employee_id == e.id:
                    code = _code_of(r.shift_key)
                    break
            ws.cell(row=i, column=j, value=code)

    # Немного ширины столбцов
    ws.column_dimensions['A'].width = 28
    for col in range(2, 2 + len(dates)):
        ws.column_dimensions[get_column_letter(col)].width = 12

    wb.save(path)
    return path

# CSV-сетка (на случай отсутствия openpyxl)

def write_csv_grid(path: str, ym: str, employees: List, schedule: Dict[date, List]):
    dates = sorted(schedule.keys())
    employees_sorted = sorted(employees, key=lambda e: e.id)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        header = ["Сотрудник / Дата"] + [d.isoformat() for d in dates]
        w.writerow(header)
        for e in employees_sorted:
            row = [f"{e.name} ({e.id})"]
            for d in dates:
                code = ""
                for r in schedule[d]:
                    if r.employee_id == e.id:
                        code = _code_of(r.shift_key)
                        break
                row.append(code)
            w.writerow(row)
    return path

# --------- «Длинный» формат для анализа: CSV и JSON ---------

def write_csv_long(path: str, employees: List, schedule: Dict[date, List]):
    name_of = {e.id: e.name for e in employees}
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["date","employee_id","employee_name","shift_key","shift_code","hours","source"]) 
        for d in sorted(schedule.keys()):
            for r in schedule[d]:
                w.writerow([d.isoformat(), r.employee_id, name_of[r.employee_id], r.shift_key, _code_of(r.shift_key), r.effective_hours, r.source])
    return path

def write_json_long(path: str, employees: List, schedule: Dict[date, List]):
    name_of = {e.id: e.name for e in employees}
    data = []
    for d in sorted(schedule.keys()):
        for r in schedule[d]:
            data.append({
                "date": d.isoformat(),
                "employee_id": r.employee_id,
                "employee_name": name_of[r.employee_id],
                "shift_key": r.shift_key,
                "shift_code": _code_of(r.shift_key),
                "hours": r.effective_hours,
                "source": r.source,
            })
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path