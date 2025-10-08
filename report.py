from __future__ import annotations
from datetime import date
from typing import Dict, List, Tuple, Optional
import csv
import os
from collections import defaultdict

import pairing

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


# ------------------- Метрики -------------------
def write_metrics_days_csv(path: str, schedule: Dict[date, List]):
    """По датам: количества DA/DB/NA/NB (учитываем N4/N8 как ночные)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "DA", "DB", "NA", "NB"])
        for d in sorted(schedule.keys()):
            da = db = na = nb = 0
            for a in schedule[d]:
                code = _code_of(a.shift_key).upper()
                if code == "DA":
                    da += 1
                elif code == "DB":
                    db += 1
                elif code in {"NA", "N4A", "N8A"}:
                    na += 1
                elif code in {"NB", "N4B", "N8B"}:
                    nb += 1
            w.writerow([d.isoformat(), da, db, na, nb])
    return path


def write_metrics_employees_csv(path: str, employees: List, schedule: Dict[date, List]):
    """По сотрудникам: суммарные часы и количество D/N/O (VAC → O)."""

    def tok(code: str) -> str:
        c = (code or "").upper()
        if c in {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}:
            return "D"
        if c in {"NA", "NB", "N4A", "N4B", "N8A", "N8B"}:
            return "N"
        return "O"

    emp_name = {e.id: e.name for e in employees}
    stats = {e.id: {"hours": 0, "D": 0, "N": 0, "O": 0} for e in employees}
    known_ids = set(stats.keys())

    for d, rows in schedule.items():
        per_emp: Dict[str, Tuple[str, int]] = {}
        for a in rows:
            if a.employee_id not in known_ids:
                continue
            per_emp[a.employee_id] = (_code_of(a.shift_key), a.effective_hours)
        for eid, (code, hrs) in per_emp.items():
            stats[eid]["hours"] += int(hrs)
            stats[eid][tok(code)] += 1

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["employee_id", "employee", "hours_total", "days_D", "nights_N", "offs_O"])
        for eid in sorted(stats.keys()):
            s = stats[eid]
            w.writerow([eid, emp_name[eid], s["hours"], s["D"], s["N"], s["O"]])
    return path

# ------------------- Пары -------------------
def write_pairs_csv(path: str, pairs: List[Tuple[str,str,int,int]], employees: List):
    """pairs: [(eid1,eid2,overlap_day,overlap_night), ...]"""
    name = {e.id: e.name for e in employees}
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["emp1_id","emp1","emp2_id","emp2","overlap_day","overlap_night"])
        for e1, e2, od, on in pairs:
            w.writerow([e1, name.get(e1,""), e2, name.get(e2,""), od, on])
    return path


def write_pairs_text_report(
    out_dir: str,
    ym: str,
    *,
    threshold_day: int,
    window_days: int,
    max_ops: int,
    hours_budget: int,
    prev_pairs: Optional[List[Tuple[str, str, int, int]]],
    curr_pairs: List[Tuple[str, str, int, int]],
    prev_days_total: Optional[int],
    curr_days_total: Optional[int],
    ops_log: List[str],
    pair_score_before: int,
    pair_score_after: int,
) -> str:
    """Пишет текстовый отчёт по парам и возвращает путь к файлу."""

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{ym}_pairs.txt")

    def fmt_pairs(lst: List[Tuple[str, str, int, int]], top: int = 10) -> List[str]:
        rows: List[str] = []
        for e1, e2, d, n in lst[:top]:
            rows.append(f" {e1}~{e2} d{d}/n{n}")
        return rows

    prev_excl = pairing.exclusive_matching_by_day(prev_pairs or [], threshold_day=threshold_day)
    curr_excl = pairing.exclusive_matching_by_day(curr_pairs, threshold_day=threshold_day)

    def key_of(a: str, b: str) -> str:
        return f"{a}~{b}" if a < b else f"{b}~{a}"

    prev_set = {key_of(a, b) for a, b, _, _ in prev_excl}
    curr_set = {key_of(a, b) for a, b, _, _ in curr_excl}
    retained = sorted(prev_set & curr_set)
    broken = sorted(prev_set - curr_set)
    new = sorted(curr_set - prev_set)

    def bucket_counts(lst: List[Tuple[str, str, int, int]]) -> Dict[str, int]:
        buckets = {"0..3": 0, "4..7": 0, f"{threshold_day}..": 0}
        for _, _, d, _ in lst:
            if d <= 3:
                buckets["0..3"] += 1
            elif d <= 7:
                buckets["4..7"] += 1
            else:
                buckets[f"{threshold_day}.."] += 1
        return buckets

    curr_buckets = bucket_counts(curr_excl)

    def by_emp(lst: List[Tuple[str, str, int, int]]) -> Dict[str, Tuple[str, int]]:
        data: Dict[str, Tuple[str, int]] = {}
        for a, b, d, _ in lst:
            data[a] = (b, d)
            data[b] = (a, d)
        return data

    prev_emp = by_emp(prev_excl)
    curr_emp = by_emp(curr_excl)

    with open(path, "w", encoding="utf-8") as f:
        pct: Optional[int] = None
        if curr_days_total and curr_days_total > 0:
            pct = int(round(100.0 * threshold_day / curr_days_total))

        f.write("[pairs.config]\n")
        f.write(f"threshold_day={threshold_day}d")
        if pct is not None:
            f.write(f" (≈{pct}%)")
        f.write(
            f", window_days={window_days}, max_ops={max_ops}, hours_budget={hours_budget}\n\n"
        )

        if prev_pairs is not None:
            f.write("[pairs.prev_month]\n")
            f.write(f"pairs_strong={len(prev_excl)}\n")
            for row in fmt_pairs(prev_excl):
                f.write(row + "\n")
            f.write("\n")

        f.write("[pairs.current_month]\n")
        f.write(f"pairs_strong={len(curr_excl)}\n")
        for row in fmt_pairs(curr_excl):
            f.write(row + "\n")
        f.write(
            "day_overlap buckets: "
            f"[0..3]={curr_buckets['0..3']}, [4..7]={curr_buckets['4..7']}, "
            f"[{threshold_day}..]={curr_buckets[f'{threshold_day}..']}\n\n"
        )

        f.write("[pairs.delta]\n")
        f.write(f"retained={len(retained)}, broken={len(broken)}, new={len(new)}\n")
        if retained:
            f.write(" retained: " + ", ".join(retained) + "\n")
        if broken:
            f.write(" broken  : " + ", ".join(broken) + "\n")
        if new:
            f.write(" new     : " + ", ".join(new) + "\n")
        f.write(
            f"pair_score: {pair_score_before} → {pair_score_after} (Δ={pair_score_after - pair_score_before})\n\n"
        )

        f.write("[pairs.by_employee]\n")
        emp_ids = sorted(set(prev_emp.keys()) | set(curr_emp.keys()))
        for eid in emp_ids:
            prev_info = prev_emp.get(eid)
            curr_info = curr_emp.get(eid)
            prev_str = f"{prev_info[0]}(d{prev_info[1]})" if prev_info else "-"
            curr_str = f"{curr_info[0]}(d{curr_info[1]})" if curr_info else "-"
            f.write(f"{eid}: prev={prev_str}, curr={curr_str}\n")
        f.write("\n")

        f.write("[pair_breaking.summary]\n")
        accepted = sum(1 for line in ops_log if "-> ACCEPT" in line)
        f.write(f"ops_applied≈{accepted}\n\n")

        f.write("[pair_breaking.ops]\n")
        for line in ops_log:
            f.write(line + "\n")

    return path

# ------------------- Логи -------------------
def write_log_txt(path: str, lines: List[str]):
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln.rstrip() + "\n")
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
