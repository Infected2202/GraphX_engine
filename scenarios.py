# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import os

from config import CONFIG as BASE_CONFIG
from generator import Generator, Assignment
import report
import pairing
import balancer
import postprocess
import validator
import coverage as cov

# ---------------------------------------------------------------------------
# Вспомогательные утилиты
# ---------------------------------------------------------------------------

def daterange(d1: date, d2: date) -> List[date]:
    out, cur = [], d1
    while cur <= d2:
        out.append(cur)
        cur += timedelta(days=1)
    return out

def deep_copy_config(cfg: dict) -> dict:
    out = {k: v for k, v in cfg.items()}
    out["months"] = [dict(m) for m in cfg["months"]]
    out["employees"] = [dict(e) for e in cfg["employees"]]
    out["shift_types"] = {k: dict(v) for k, v in cfg["shift_types"].items()}
    if "logging" in out: out["logging"] = dict(out["logging"])
    if "pair_breaking" in out: out["pair_breaking"] = dict(out["pair_breaking"])
    if "coverage" in out: out["coverage"] = dict(out["coverage"])
    return out

def filter_employees(cfg: dict, keep_ids: List[str]) -> dict:
    cfg2 = deep_copy_config(cfg)
    keep = set(keep_ids)
    cfg2["employees"] = [e for e in cfg2["employees"] if e["id"] in keep]
    return cfg2

def merge_vacations(cfg: dict, extra_vac: Dict[str, List[date]]) -> dict:
    """Добавляет даты отпусков во ВСЕ month_spec; фактическое применение отфильтруем по окну месяца ниже."""
    cfg2 = deep_copy_config(cfg)
    for ms in cfg2["months"]:
        vac = dict(ms.get("vacations", {}) or {})
        for eid, dates in (extra_vac or {}).items():
            vac.setdefault(eid, [])
            vac[eid].extend(dates)
        ms["vacations"] = vac
    return cfg2

def month_bounds(gen: Generator, ym: str) -> Tuple[date, date]:
    y, m = map(int, ym.split("-"))
    return gen.month_bounds(y, m)

def aggregate_effective_vacations(cfg_months: List[dict], current_ym: str, gen: Generator, current_emp_ids: set[str]) -> Dict[str, List[date]]:
    """Собираем ВСЕ отпуска из всех month_spec, но возвращаем только те даты, что попадают в current_ym и по существующим сотрудникам."""
    d0, d1 = month_bounds(gen, current_ym)
    eff: Dict[str, List[date]] = {}
    for ms in cfg_months:
        vac = ms.get("vacations", {}) or {}
        for eid, dates in vac.items():
            if eid not in current_emp_ids: continue
            for dt in dates:
                if d0 <= dt <= d1:
                    eff.setdefault(eid, []).append(dt)
    return {eid: sorted(set(ds)) for eid, ds in eff.items()}

def synthetic_prev_tail_and_carry_in(first_day: date, existing_ids: set[str], gen: Generator):
    """Синтетический хвост (28–31 июля) + переносы на 1-е число первого месяца; фильтруем по существующим сотрудникам."""
    prev_tail_by_emp = {
        "E01": ["OFF","DB","OFF","OFF"],
        "E02": ["OFF","OFF","OFF","DA"],
        "E03": ["DA","OFF","NA","OFF"],
        "E04": ["DA","OFF","OFF","N4A"],
        "E05": ["OFF","DA","OFF","OFF"],
        "E06": ["OFF","OFF","OFF","DB"],
        "E07": ["DB","OFF","NB","OFF"],  # без переноса
        "E08": ["DB","OFF","OFF","N4B"],
    }
    prev_tail_by_emp = {eid: tail for eid, tail in prev_tail_by_emp.items() if eid in existing_ids}
    carry_in = []
    if "E04" in existing_ids:
        carry_in.append(Assignment("E04", first_day, "n8_a", gen.shift_types["n8_a"].hours, source="template"))
    if "E08" in existing_ids:
        carry_in.append(Assignment("E08", first_day, "n8_b", gen.shift_types["n8_b"].hours, source="template"))
    return prev_tail_by_emp, carry_in

def extract_tail(schedule, employees, gen: Generator) -> Dict[str, List[str]]:
    dates = sorted(schedule.keys())
    tail_dates = dates[-4:] if len(dates) >= 4 else dates
    prev_tail_by_emp: Dict[str, List[str]] = {}
    for e in employees:
        codes = []
        for d in tail_dates:
            for r in schedule[d]:
                if r.employee_id == e.id:
                    codes.append(gen.code_of(r.shift_key))
                    break
        prev_tail_by_emp[e.id] = codes
    return prev_tail_by_emp

# ---------------------------------------------------------------------------
# Сценарии
# ---------------------------------------------------------------------------

def scenarios_def() -> List[dict]:
    """Набор быстрых сценариев: мощности 4–8, отпуска на стыке, проверка балансира."""
    return [
        # База 8 сотрудников, балансер выключен (контрольная)
        {"name":"S_base_8_bal_off", "keep_ids":["E01","E02","E03","E04","E05","E06","E07","E08"], "vacations":{}, "pair_breaking_enabled":False},
        # База 8 сотрудников, балансер включен
        {"name":"S_base_8_bal_on",  "keep_ids":["E01","E02","E03","E04","E05","E06","E07","E08"], "vacations":{}, "pair_breaking_enabled":True},
        # 7 сотрудников, балансер включен
        {"name":"S_7_bal_on",       "keep_ids":["E01","E02","E03","E04","E05","E06","E07"],       "vacations":{}, "pair_breaking_enabled":True},
        # 5 сотрудников (соло-нагрузка), балансер включен
        {"name":"S_5_solo_bal_on",  "keep_ids":["E01","E02","E03","E04","E05"],                  "vacations":{}, "pair_breaking_enabled":True},
        # Отпуск E08 (конец августа + начало сентября), балансер включен
        {"name":"S_vac_E08_cross",  "keep_ids":["E01","E02","E03","E04","E05","E06","E07","E08"], "vacations":{"E08": daterange(date(2025,8,26), date(2025,9,3))}, "pair_breaking_enabled":True},
        # Отпуск E07 (первые числа сентября), балансер включен
        {"name":"S_vac_E07_sep",    "keep_ids":["E01","E02","E03","E04","E05","E06","E07","E08"], "vacations":{"E07": daterange(date(2025,9,1), date(2025,9,6))}, "pair_breaking_enabled":True},
    ]

# ---------------------------------------------------------------------------
# Запуск одного сценария
# ---------------------------------------------------------------------------

def run_scenario(scn: dict, out_root: Path):
    # 0) базовый конфиг + фильтрация сотрудников + добавление отпусков
    cfg0 = deep_copy_config(BASE_CONFIG)
    cfg1 = filter_employees(cfg0, scn["keep_ids"])
    cfg2 = merge_vacations(cfg1, scn.get("vacations", {}))

    # переключатель балансера
    cfg2["pair_breaking"]["enabled"] = bool(scn.get("pair_breaking_enabled", False))

    # 1) генератор, кодовая карта для отчётов
    gen = Generator(cfg2)
    code_map = {k: v.code for k, v in gen.shift_types.items()}
    report.set_code_map(code_map)

    # 2) выходная папка
    out_dir = out_root / scn["name"]
    out_dir.mkdir(parents=True, exist_ok=True)

    # 3) state: хвост + переносы + анти-соло
    prev_tail_by_emp = {}
    carry_in = []
    solo_months_counter: Dict[str,int] = {}
    prev_pairs_for_month: Optional[List[Tuple[str, str, int, int]]] = None

    # 4) по месяцам
    for idx, month_spec in enumerate(cfg2["months"]):
        ym = month_spec["month_year"]
        y, m = map(int, ym.split("-"))
        first_day = date(y, m, 1)
        current_emp_ids = {rec["id"] for rec in cfg2["employees"]}

        # синтетический хвост только для первого месяца
        if idx == 0:
            prev_tail_by_emp, carry_in = synthetic_prev_tail_and_carry_in(first_day, current_emp_ids, gen)

        # эффективные отпуска (только попавшие в этот месяц)
        eff_vacations = aggregate_effective_vacations(cfg2["months"], ym, gen, current_emp_ids)
        month_spec_eff = dict(month_spec)
        month_spec_eff["vacations"] = eff_vacations  # применим пост-цветом, но оставим в логах

        # генерация
        employees, schedule, carry_out = gen.generate_month(
            month_spec_eff,
            carry_in=carry_in,
            prev_tail_by_emp=prev_tail_by_emp
        )

        # балансировка пар (safe-mode в начале месяца)
        pairs_before = pairing.compute_pairs(schedule, gen.code_of)
        pair_score_before_calc = sum(p[2] for p in pairs_before)
        ret = balancer.apply_pair_breaking(
            schedule,
            employees,
            month_spec_eff.get("norm_hours_month", 0),
            pairs_before,
            cfg2.get("pair_breaking", {}),
            gen.code_of,
            solo_months_counter,
        )
        schedule_balanced, ops_log, _solo_after, *rest = ret
        if len(rest) >= 2:
            pair_score_before, pair_score_after = rest[:2]
        else:
            pair_score_after = sum(p[2] for p in pairing.compute_pairs(schedule_balanced, gen.code_of))
            pair_score_before = pair_score_before_calc
        print(
            f"[pairs.score] before={pair_score_before} after={pair_score_after} "
            f"Δ={pair_score_after - pair_score_before}"
        )
        if cfg2.get("pair_breaking", {}).get("enabled", False):
            schedule = schedule_balanced

        # пост-перекраска отпусков (VAC8/VAC0)
        postprocess.apply_vacations(schedule, eff_vacations, gen.shift_types)

        # валидации
        baseline_issues = validator.validate_baseline(ym, employees, schedule, gen.code_of, gen=None, ignore_vacations=True)
        smoke = validator.coverage_smoke(ym, schedule, gen.code_of, first_days=cfg2.get("pair_breaking",{}).get("window_days",6)+2)
        trace = validator.phase_trace(ym, employees, schedule, gen.code_of, gen=None, days=10)

        # отчёты
        base = f"{scn['name']}_{ym}"
        xlsx_path = out_dir / f"{base}.xlsx"
        csv_grid_path = out_dir / f"{base}_grid.csv"
        report.write_workbook(str(xlsx_path), ym, employees, schedule)
        report.write_csv_grid(str(csv_grid_path), ym, employees, schedule)

        metrics_emp_path = out_dir / f"{base}_metrics_employees.csv"
        metrics_days_path = out_dir / f"{base}_metrics_days.csv"
        report.write_metrics_employees_csv(str(metrics_emp_path), employees, schedule)
        report.write_metrics_days_csv(str(metrics_days_path), schedule)

        pairs_after = pairing.compute_pairs(schedule, gen.code_of)
        pairs_path = out_dir / f"{base}_pairs.csv"
        report.write_pairs_csv(str(pairs_path), pairs_after, employees)

        # лог
        log_lines = []
        if idx == 0 and prev_tail_by_emp:
            log_lines.append(f"[bootstrap] synthetic prev_tail for first month (employees={len(prev_tail_by_emp)})")
        if carry_in:
            ap = ", ".join([f"{a.employee_id}={gen.code_of(a.shift_key)}" for a in carry_in])
            log_lines.append(f"[carry_in] {ym}-01: {ap}")
        if cfg2.get("pair_breaking", {}).get("enabled", False):
            log_lines.append("[pair_breaking.apply]")
            if ops_log:
                log_lines.extend([f" - {x}" for x in ops_log])
            else:
                log_lines.append(" - no-ops")
            log_lines.append("[coverage.smoke.first-days]")
            for row in smoke:
                log_lines.append(f" {row[0]}: DA={row[1]} DB={row[2]} NA={row[3]} NB={row[4]}")
        if carry_out:
            co = ", ".join([f"{a.employee_id}={gen.code_of(a.shift_key)}@{a.date.isoformat()}" for a in carry_out])
            log_lines.append(f"[carry_out] to next month: {co}")
        if eff_vacations:
            vlines = []
            for eid, ds in eff_vacations.items():
                vlines.append(f"{eid}: {', '.join(sorted({d.isoformat() for d in ds}))}")
            log_lines.append("[vacations.effective]")
            log_lines.extend(vlines)
        if baseline_issues:
            log_lines.append("[validator.baseline.issues]")
            log_lines.extend([f" - {x}" for x in baseline_issues])
        if trace:
            log_lines.append("[diagnostics.phase_trace.first10]")
            log_lines.extend([f" {ln}" for ln in trace])
        log_path = out_dir / f"{base}_log.txt"
        report.write_log_txt(str(log_path), log_lines)

        pb_cfg = cfg2.get("pair_breaking", {}) or {}
        threshold_day = int(pb_cfg.get("overlap_threshold", 8))
        window_days = int(pb_cfg.get("window_days", 6))
        max_ops = int(pb_cfg.get("max_ops", 4))
        hours_budget = int(pb_cfg.get("hours_budget", 0))

        try:
            curr_days_total = max([p[2] for p in pairs_after] or [0]) or None
        except Exception:
            curr_days_total = None

        appended_log_path = report.append_pairs_to_log(
            out_dir=str(out_dir),
            ym=base,
            threshold_day=threshold_day,
            window_days=window_days,
            max_ops=max_ops,
            hours_budget=hours_budget,
            prev_pairs=prev_pairs_for_month,
            curr_pairs=pairs_after,
            curr_days_total=curr_days_total,
            ops_log=ops_log,
            pair_score_before=pair_score_before,
            pair_score_after=pair_score_after,
        )
        print(f"[report.pairs->_log] appended: {appended_log_path}")

        prev_pairs_for_month = pairs_after

        # хвост → следующий месяц
        prev_tail_by_emp = extract_tail(schedule, employees, gen)
        carry_in = carry_out

        # анти-соло счётчик: если в месяце были соло-дни — инкремент сотруднику
        solo_days = cov.solo_days_by_employee(schedule, gen.code_of)
        solo_emp_ids = {eid for eid, cnt in solo_days.items() if cnt > 0}
        for e in employees:
            if e.id in solo_emp_ids:
                solo_months_counter[e.id] = solo_months_counter.get(e.id, 0) + 1
            else:
                solo_months_counter.setdefault(e.id, 0)

    print(f"[SCENARIO DONE] {scn['name']} → {out_dir}")

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    out_root = Path(os.getcwd()) / "reports" / "scenarios"
    out_root.mkdir(parents=True, exist_ok=True)

    # Можно указать SCN=<substring> в окружении, чтобы отфильтровать сценарии
    scn_filter = os.environ.get("SCN", "").strip().lower()

    scenarios = scenarios_def()
    for scn in scenarios:
        if scn_filter and scn_filter not in scn["name"].lower():
            continue
        run_scenario(scn, out_root)

    print("Все сценарии выполнены.")
