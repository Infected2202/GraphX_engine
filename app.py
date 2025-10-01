from datetime import date
from pathlib import Path
from config import CONFIG
from generator import Generator, Assignment
import report
import pairing
import balancer
import os

if __name__ == "__main__":
    gen = Generator(CONFIG)

    # Карта кодов для отчётов
    code_map = {k: v.code for k, v in gen.shift_types.items()}
    report.set_code_map(code_map)

    carry_in = []           # переносы N8* на 1-е число
    prev_tail_by_emp = {}   # синтетический хвост для первого месяца

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
                "E07": ["DB", "OFF", "NB", "OFF"],    # → 1 авг OFF (без переноса)  ← фикс
                "E08": ["DB", "OFF", "OFF", "N4B"],   # → перенос N8B на 1 авг
            }
            # Готовим carry-in N8* на 1-е число только для тех, у кого 31-го стоит N4*
            carry_in = [
                Assignment("E04", first_day, "n8_a", gen.shift_types["n8_a"].hours, source="template"),
                Assignment("E08", first_day, "n8_b", gen.shift_types["n8_b"].hours, source="template"),
            ]

        employees, schedule, carry_out = gen.generate_month(
            month_spec,
            carry_in=carry_in,
            prev_tail_by_emp=prev_tail_by_emp
        )

        # ---------- Аналитика и логи ----------
        log_lines = []
        if CONFIG.get("logging", {}).get("enabled", True):
            if idx == 0:
                log_lines.append(f"[bootstrap] synthetic prev_tail applied for first month (size={len(prev_tail_by_emp)})")
            if carry_in:
                ap = ", ".join([f"{a.employee_id}={gen.code_of(a.shift_key)}" for a in carry_in])
                log_lines.append(f"[carry_in] {ym}-01: {ap}")

        # ---------- Сохранение в каталог reports/ ----------
        base = f"schedule_{ym}"
        xlsx_path = out_dir / f"{base}.xlsx"
        csv_grid_path = out_dir / f"{base}_grid.csv"
        report.write_workbook(str(xlsx_path), ym, employees, schedule)
        report.write_csv_grid(str(csv_grid_path), ym, employees, schedule)
        # Метрики
        metrics_emp_path = out_dir / f"{base}_metrics_employees.csv"
        metrics_days_path = out_dir / f"{base}_metrics_days.csv"
        report.write_metrics_employees_csv(str(metrics_emp_path), employees, schedule)
        report.write_metrics_days_csv(str(metrics_days_path), schedule)
        # Пары (подсчёт, без изменений графика)
        pairs = pairing.compute_pairs(schedule, gen.code_of)
        pairs_path = out_dir / f"{base}_pairs.csv"
        report.write_pairs_csv(str(pairs_path), pairs, employees)

        # Балансировка пар (каркас; обычно выключена)
        schedule_balanced, ops_log = balancer.apply_pair_breaking(
            schedule, employees, month_spec.get("norm_hours_month", 0), pairs, CONFIG.get("pair_breaking", {})
        )
        if ops_log:
            log_lines.append("[pair_breaking] operations:")
            log_lines.extend([f" - {x}" for x in ops_log])

        # Логи (text)
        if CONFIG.get("logging", {}).get("enabled", True):
            top_k = CONFIG.get("logging", {}).get("pairs_top", 20)
            top_show = pairs[:top_k]
            if top_show:
                log_lines.append("[pairs.top_day]")
                for (e1, e2, od, on) in top_show:
                    log_lines.append(f" {e1}~{e2}: overlap_day={od}, overlap_night={on}")
            if carry_out:
                co = ", ".join([f"{a.employee_id}={gen.code_of(a.shift_key)}@{a.date.isoformat()}" for a in carry_out])
                log_lines.append(f"[carry_out] to next month: {co}")
            log_path = out_dir / f"{base}_log.txt"
            report.write_log_txt(str(log_path), log_lines)

        print(f"Сохранено: {xlsx_path}, {csv_grid_path}, {metrics_emp_path}, {metrics_days_path}, {pairs_path}")

        # Хвост и переносы для следующего месяца
        # Берём последние 4 даты текущего месяца и собираем хвост по сотрудникам:
        dates_sorted = sorted(schedule.keys())
        tail_dates = dates_sorted[-4:] if len(dates_sorted) >= 4 else dates_sorted
        prev_tail_by_emp = {}
        for e in employees:
            codes = []
            for d in tail_dates:
                for r in schedule[d]:
                    if r.employee_id == e.id:
                        codes.append(gen.code_of(r.shift_key))
                        break
            prev_tail_by_emp[e.id] = codes
        carry_in = carry_out

    print("Готово.")
