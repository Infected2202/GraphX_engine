from datetime import date
from pathlib import Path
from typing import List
import os

from engine.domain.schedule import Assignment
from engine.infrastructure.config import CONFIG
from engine.infrastructure.production_calendar import ProductionCalendar
from engine.presentation import report
from engine.services import analytics
from engine.services import balancing
from engine.services import postprocess
from engine.services import validation
from engine.services.generator import Generator

if __name__ == "__main__":
    calendar = ProductionCalendar.load_default()
    gen = Generator(CONFIG, calendar=calendar)

    # Карта кодов для отчётов
    code_map = {k: v.code for k, v in gen.shift_types.items()}
    report.set_code_map(code_map)

    carry_in = []           # переносы N8* на 1-е число
    prev_tail_by_emp = {}   # синтетический хвост для первого месяца
    # анти-соло счётчик по сотрудникам (копим между месяцами в рамках одного запуска)
    solo_months_counter = {}
    prev_pairs_for_report: list | None = None

    out_dir = Path(os.getcwd()) / "reports"
    out_dir.mkdir(exist_ok=True)

    for idx, month_spec in enumerate(CONFIG["months"]):
        ym = month_spec["month_year"]
        # Номер месяца и 1-е число (для carry-in)
        y, m = map(int, ym.split("-"))
        first_day = date(y, m, 1)
        # Границы месяца (для фильтра отпусков)
        first_day_cur = first_day
        # небольшая утилита: получить последний день месяца через генератор
        last_day_cur = list(gen.iter_month_days(y, m))[-1]
        # Множество актуальных сотрудников (на случай, если кого-то удалили из конфига)
        current_emp_ids = {rec["id"] for rec in CONFIG["employees"]}

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
            # Оставляем хвост только для существующих сотрудников
            prev_tail_by_emp = {eid: tail for eid, tail in prev_tail_by_emp.items() if eid in current_emp_ids}
            # Готовим carry-in N8* на 1-е число только для тех, кто есть в конфиге
            carry_in = []
            if "E04" in current_emp_ids:
                carry_in.append(Assignment("E04", first_day, "n8_a", gen.shift_types["n8_a"].hours, source="template"))
            if "E08" in current_emp_ids:
                carry_in.append(Assignment("E08", first_day, "n8_b", gen.shift_types["n8_b"].hours, source="template"))

        # --- Агрегируем отпуска по всем month_spec: берём только даты, попадающие в текущий месяц ---
        eff_vacations: dict[str, list[date]] = {}
        for ms in CONFIG["months"]:
            vac = ms.get("vacations", {}) or {}
            for eid, dates in vac.items():
                for dt in dates:
                    if first_day_cur <= dt <= last_day_cur:
                        eff_vacations.setdefault(eid, []).append(dt)
        # убираем дубликаты и несущ. сотрудников — на всякий случай
        eff_vacations = {eid: sorted(set(dts)) for eid, dts in eff_vacations.items() if eid in current_emp_ids}
        # Передаём в генератор модифицированный month_spec с «эффективными» отпусками
        month_spec_eff = dict(month_spec)
        month_spec_eff["vacations"] = eff_vacations

        employees, schedule, carry_out = gen.generate_month(
            month_spec_eff,
            carry_in=carry_in,
            prev_tail_by_emp=prev_tail_by_emp
        )

        # ---- Балансировка пар (safe-mode в начале месяца) ----
        pairs_before = analytics.compute_pairs(schedule, gen.code_of)
        pb_cfg = dict(CONFIG.get("pair_breaking", {}) or {})
        pb_cfg.setdefault("prev_pairs", prev_pairs_for_report or [])
        schedule_balanced, ops_log, solo_after, pair_score_before_pb, pair_score_after_pb, apply_log = balancing.apply_pair_breaking(
            schedule,
            employees,
            gen.code_of,
            pb_cfg,
        )
        if CONFIG.get("pair_breaking", {}).get("enabled", False):
            schedule = schedule_balanced

        # ---- Пост-перекраска отпусков (0/8ч, не влияет на паттерн) ----
        postprocess.apply_vacations(schedule, eff_vacations, gen.shift_types)

        # -------- СЛОЙ СОКРАЩЕНИЙ (ПОСЛЕДНИМ) --------
        raw_norm = month_spec.get("norm_hours_month")
        norm = int(raw_norm) if raw_norm is not None else int(calendar.norm_hours(y, m) or 0)
        gen.enforce_hours_caps(employees, schedule, norm, ym)
        norm_info = gen.last_norms_info() or {}

        # ---------- Сохранение в каталог reports/ ----------
        base = f"schedule_{ym}"
        xlsx_path = out_dir / f"{base}.xlsx"
        csv_grid_path = out_dir / f"{base}_grid.csv"
        report.write_workbook(str(xlsx_path), ym, employees, schedule, calendar=calendar)
        report.write_csv_grid(str(csv_grid_path), ym, employees, schedule)
        # Метрики
        metrics_emp_path = out_dir / f"{base}_metrics_employees.csv"
        metrics_days_path = out_dir / f"{base}_metrics_days.csv"
        report.write_metrics_employees_csv(str(metrics_emp_path), employees, schedule)
        report.write_metrics_days_csv(str(metrics_days_path), schedule)

        norms_path = out_dir / f"{base}_norms.txt"
        _, norm_warnings, _ = report.write_norms_report(
            str(norms_path),
            ym,
            employees,
            schedule,
            norm_info,
        )

        # ---------- Аналитика и логи ----------
        log_lines = []
        if CONFIG.get("logging", {}).get("enabled", True):
            if idx == 0:
                log_lines.append(f"[bootstrap] synthetic prev_tail applied for first month (size={len(prev_tail_by_emp)})")
            if carry_in:
                ap = ", ".join([f"{a.employee_id}={gen.code_of(a.shift_key)}" for a in carry_in])
                log_lines.append(f"[carry_in] {ym}-01: {ap}")
            if CONFIG.get("pair_breaking", {}).get("enabled", False):
                log_lines.append("[pair_breaking.apply]")
                if apply_log:
                    log_lines.extend([f" - {x}" for x in apply_log])
                else:
                    log_lines.append(" - no-ops")
                if ops_log:
                    log_lines.append("[pair_breaking.ops]")
                    log_lines.extend([f" - {x}" for x in ops_log])
                # smoke по первым дням
                smoke = validation.coverage_smoke(ym, schedule, gen.code_of, first_days=CONFIG.get("pair_breaking", {}).get("window_days", 6) + 2)
                log_lines.append("[coverage.smoke.first-days]")
                for row in smoke:
                    log_lines.append(f" {row[0]}: DA={row[1]} DB={row[2]} NA={row[3]} NB={row[4]}")
            # baseline валидация с учётом N4/N8 и игнором VAC
            baseline_issues = validation.validate_baseline(ym, employees, schedule, gen.code_of, gen=None, ignore_vacations=True)
            if baseline_issues:
                log_lines.append("[validation.baseline.issues]")
                log_lines.extend([f" - {x}" for x in baseline_issues])
            # диагностический трейс фазы (первые 10 дней)
            trace = validation.phase_trace(ym, employees, schedule, gen.code_of, gen=None, days=10)
            if trace:
                log_lines.append("[diagnostics.phase_trace.first10]")
                log_lines.extend([f" {ln}" for ln in trace])
            if norm_info:
                log_lines.append(f"[norms.report] file={norms_path.name}")
                operations = norm_info.get("operations", []) or []
                if operations:
                    log_lines.append("[norms.shortening]")
                    for op in sorted(operations, key=lambda x: (x["date"], x["employee_id"])):
                        dt = op["date"].isoformat() if hasattr(op.get("date"), "isoformat") else op.get("date")
                        log_lines.append(
                            f" {dt} {op['employee_id']}: {op['from_code']}→{op['to_code']} ({op.get('hours_delta', 0)}ч)"
                        )
                if norm_warnings:
                    log_lines.append("[norms.warnings]")
                    for msg in norm_warnings:
                        log_lines.append(f" - {msg}")

        if schedule:
            last_day = max(schedule.keys())
            next_year = last_day.year + (1 if last_day.month == 12 else 0)
            next_month = 1 if last_day.month == 12 else last_day.month + 1
            new_carry_out: List[Assignment] = []
            for entry in schedule[last_day]:
                code = gen.code_of(entry.shift_key).upper()
                if code in {"N4A", "N4B"}:
                    key = "n8_a" if code.endswith("A") else "n8_b"
                    shift = gen.shift_types[key]
                    new_carry_out.append(
                        Assignment(
                            entry.employee_id,
                            date(next_year, next_month, 1),
                            key,
                            shift.hours,
                            source="autofix",
                        )
                    )
            carry_out = new_carry_out

        # Пары (после возможного баланса)
        pairs = analytics.compute_pairs(schedule, gen.code_of)
        pair_score_after = sum(p[2] for p in pairs)
        pairs_path = out_dir / f"{base}_pairs.csv"
        report.write_pairs_csv(str(pairs_path), pairs, employees)

        pb_cfg = CONFIG.get("pair_breaking", {})
        threshold_day = int(pb_cfg.get("overlap_threshold", 8))
        window_days = int(pb_cfg.get("window_days", 6))
        max_ops = int(pb_cfg.get("max_ops", 4))
        hours_budget = int(pb_cfg.get("hours_budget", 0))

        prev_days_total = max([p[2] for p in (prev_pairs_for_report or [])], default=0)
        prev_days_total = prev_days_total or None
        curr_days_total = max([p[2] for p in pairs], default=0)
        curr_days_total = curr_days_total or None

        report_path = report.write_pairs_text_report(
            out_dir=str(out_dir),
            ym=ym,
            threshold_day=threshold_day,
            window_days=window_days,
            max_ops=max_ops,
            hours_budget=hours_budget,
            prev_pairs=prev_pairs_for_report,
            curr_pairs=pairs,
            prev_days_total=prev_days_total,
            curr_days_total=curr_days_total,
            ops_log=ops_log,
            apply_log=apply_log,
            pair_score_before=pair_score_before_pb,
            pair_score_after=pair_score_after_pb if CONFIG.get("pair_breaking", {}).get("enabled", False) else pair_score_after,
        )
        print(f"[report.pairs] written: {report_path}")
        prev_pairs_for_report = pairs

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

        # ---- Анти-соло счётчик (по месяцу) ----
        # считаем «соло-дни» в этом месяце и накапливаем «соло-месяцы»
        solo_days = analytics.solo_days_by_employee(schedule, gen.code_of)
        solo_emp_ids = {eid for eid, cnt in solo_days.items() if cnt > 0}
        for e in employees:
            if e.id in solo_emp_ids:
                solo_months_counter[e.id] = solo_months_counter.get(e.id, 0) + 1
            else:
                solo_months_counter.setdefault(e.id, 0)

    print("Готово.")
