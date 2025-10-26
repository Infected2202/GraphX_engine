# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from glob import glob
import json

from engine.domain.schedule import Assignment
from engine.infrastructure.config import CONFIG as BASE_CONFIG
from engine.infrastructure.production_calendar import ProductionCalendar
from engine.presentation import report
from engine.services import analytics
from engine.services import balancing
from engine.services import postprocess
from engine.services import validation
from engine.services.generator import Generator

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
    months_copy: List[dict] = []
    for m in cfg.get("months", []):
        m_copy = dict(m)
        if "vacations" in m_copy and m_copy["vacations"]:
            m_copy["vacations"] = {eid: list(ds) for eid, ds in m_copy["vacations"].items()}
        months_copy.append(m_copy)
    out["months"] = months_copy
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

def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Unsupported vacation date value: {value!r}")


def _expand_vacation_entry(entry) -> List[date]:
    if entry is None:
        return []
    if isinstance(entry, (list, tuple, set)):
        out: List[date] = []
        for item in entry:
            out.extend(_expand_vacation_entry(item))
        return out
    if isinstance(entry, dict):
        start_raw = entry.get("start") or entry.get("from")
        end_raw = entry.get("end") or entry.get("to") or start_raw
        if not start_raw:
            return []
        start = _as_date(start_raw)
        end = _as_date(end_raw)
        if end < start:
            start, end = end, start
        return daterange(start, end)
    return [_as_date(entry)]


def normalize_vacations_map(raw_map: Dict[str, object] | None) -> Dict[str, List[date]]:
    if not raw_map:
        return {}
    norm: Dict[str, List[date]] = {}
    for eid, spec in raw_map.items():
        days = _expand_vacation_entry(spec)
        if not days:
            continue
        norm[eid] = sorted(set(days))
    return norm


def merge_vacations(cfg: dict, extra_vac: Dict[str, object]) -> dict:
    """Добавляет даты отпусков во ВСЕ month_spec; фактическое применение отфильтруем по окну месяца ниже."""
    cfg2 = deep_copy_config(cfg)
    extra_norm = normalize_vacations_map(extra_vac)
    for ms in cfg2["months"]:
        vac = {eid: list(ds) for eid, ds in (ms.get("vacations", {}) or {}).items()}
        for eid, dates in extra_norm.items():
            vac.setdefault(eid, [])
            vac[eid].extend(dates)
        ms["vacations"] = {eid: sorted(set(ds)) for eid, ds in vac.items() if ds}
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

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

def _ensure_defaults(scn: dict) -> dict:
    """
    Мягко подставляет дефолты, если чего-то нет в JSON.
    Без добавления новых, неиспользуемых ключей.
    """
    scn = dict(scn or {})
    scn.setdefault("employees", [])
    scn.setdefault("config", {})
    cfg = scn["config"]
    cfg.setdefault("use_preset_vacations", True)
    pb = cfg.setdefault("pair_breaking", {})
    pb.setdefault("enabled", True)
    pb.setdefault("window_days", 6)
    pb.setdefault("overlap_threshold", 6)
    pb.setdefault("max_ops", 4)
    pb.setdefault("hours_budget", 12)
    pb.setdefault("post_desync_include_current", True)
    cfg.setdefault("months", [])
    return scn

def load_scenarios_from_dir(dir_path: Path) -> List[dict]:
    """
    Загружает все .json из каталога как сценарии.
    Игнорирует битые файлы, пишет причину в stdout.
    """
    out: List[dict] = []
    for p in sorted(glob(str(dir_path / "*.json"))):
        try:
            with open(p, "r", encoding="utf-8") as f:
                scn = json.load(f)
                out.append(_ensure_defaults(scn))
        except Exception as e:
            print(f"[scenarios] skip {p}: {e}")
    return out

def build_config_from_scenario(base_cfg: dict, scn: dict) -> Tuple[dict, List[str]]:
    """
    Формирует конфиг генератора из JSON-сценария.
    Возвращает пару (конфиг, список стажёров).
    """
    cfg = deep_copy_config(base_cfg)
    scn_cfg = scn.get("config", {}) or {}

    # сотрудники
    employees_spec = scn.get("employees") or scn_cfg.get("employees") or []
    base_emp_map = {e["id"]: dict(e) for e in cfg.get("employees", [])}
    intern_ids: List[str] = []
    if employees_spec:
        new_employees: List[dict] = []
        for rec in employees_spec:
            eid = rec.get("id")
            if not eid:
                continue
            base_emp = base_emp_map.get(eid, {
                "id": eid,
                "name": rec.get("name", eid),
                "is_trainee": False,
                "mentor_id": None,
                "ytd_overtime": 0,
            })
            emp = dict(base_emp)
            if "name" in rec:
                emp["name"] = rec["name"]
            if "mentor_id" in rec:
                emp["mentor_id"] = rec["mentor_id"]
            if "ytd_overtime" in rec:
                emp["ytd_overtime"] = rec["ytd_overtime"]
            if "is_trainee" in rec:
                emp["is_trainee"] = bool(rec["is_trainee"])
            if "intern" in rec:
                emp["is_trainee"] = bool(rec["intern"])
            new_employees.append(emp)
            if emp.get("is_trainee"):
                intern_ids.append(eid)
        cfg["employees"] = new_employees
    else:
        intern_ids = [e.get("id") for e in cfg.get("employees", []) if e.get("is_trainee")]

    # pair breaking overrides
    pair_breaking_cfg = dict(cfg.get("pair_breaking", {}) or {})
    for k, v in (scn_cfg.get("pair_breaking", {}) or {}).items():
        pair_breaking_cfg[k] = v
    cfg["pair_breaking"] = pair_breaking_cfg

    # months
    months_spec = scn_cfg.get("months") or []
    if months_spec:
        base_months = {m["month_year"]: dict(m) for m in cfg.get("months", []) if m.get("month_year")}
        new_months: List[dict] = []
        for ms in months_spec:
            ym = ms.get("month_year") or ms.get("ym")
            if not ym:
                continue
            if ym in base_months:
                month_cfg = dict(base_months[ym])
            else:
                month_cfg = {"month_year": ym}
            month_cfg["month_year"] = ym
            if "norm_hours_month" in ms:
                month_cfg["norm_hours_month"] = ms["norm_hours_month"]
            elif ym not in base_months:
                month_cfg.pop("norm_hours_month", None)
            if "vacations" in ms:
                existing = {eid: list(ds) for eid, ds in (month_cfg.get("vacations", {}) or {}).items()}
                parsed = normalize_vacations_map(ms.get("vacations"))
                for eid, dates in parsed.items():
                    existing.setdefault(eid, [])
                    existing[eid].extend(dates)
                month_cfg["vacations"] = {eid: sorted(set(ds)) for eid, ds in existing.items() if ds}
            elif not scn_cfg.get("use_preset_vacations", True):
                month_cfg["vacations"] = {}
            new_months.append(month_cfg)
        cfg["months"] = new_months
    elif not scn_cfg.get("use_preset_vacations", True):
        for month_cfg in cfg.get("months", []):
            month_cfg["vacations"] = {}

    # Дополнительные отпуска из JSON-структуры (legacy совместимость)
    extra_vacations = scn.get("vacations") or scn_cfg.get("vacations") or {}
    if extra_vacations:
        cfg = merge_vacations(cfg, extra_vacations)

    return cfg, intern_ids

# ---------------------------------------------------------------------------
# Запуск одного сценария
# ---------------------------------------------------------------------------

def run_scenario(scn: dict, out_root: Path):
    # 0) базовый конфиг + JSON-переопределения
    cfg2, intern_ids = build_config_from_scenario(BASE_CONFIG, scn)

    # Совместимость со старыми сценариями: keep_ids / vacations / переключатель балансера
    if scn.get("keep_ids"):
        cfg2 = filter_employees(cfg2, scn["keep_ids"])
    if scn.get("vacations") and not scn.get("config", {}).get("vacations"):
        cfg2 = merge_vacations(cfg2, scn.get("vacations", {}))
    if "pair_breaking_enabled" in scn:
        cfg2.setdefault("pair_breaking", {})["enabled"] = bool(scn.get("pair_breaking_enabled", False))

    if intern_ids:
        merged_interns = set(scn.get("intern_ids", []) or [])
        merged_interns.update(intern_ids)
        scn["intern_ids"] = sorted(merged_interns)

    # 1) генератор, кодовая карта для отчётов
    calendar = ProductionCalendar.load_default()
    gen = Generator(cfg2, calendar=calendar)
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

        # baseline-validator до балансировки
        baseline_issues = validation.validate_baseline(ym, employees, schedule, gen.code_of, gen=None, ignore_vacations=True)

        # балансировка пар (safe-mode в начале месяца)
        pairs_before = analytics.compute_pairs(schedule, gen.code_of)
        pb_cfg = dict(cfg2.get("pair_breaking", {}) or {})
        prev_pairs_hint = scn.get("prev_pairs_for_month") or scn.get("prev_pairs") or prev_pairs_for_month or []
        pb_cfg.setdefault("prev_pairs", prev_pairs_hint)
        if "intern_ids" in scn:
            pb_cfg["intern_ids"] = scn["intern_ids"]
        schedule_balanced, ops_log, _solo_after, pair_score_before, pair_score_after, apply_log = balancing.apply_pair_breaking(
            schedule,
            employees,
            gen.code_of,
            pb_cfg,
        )
        print(
            f"[pairs.score] before={pair_score_before} after={pair_score_after} "
            f"Δ={pair_score_after - pair_score_before}"
        )
        if cfg2.get("pair_breaking", {}).get("enabled", False):
            schedule = schedule_balanced

        # пост-перекраска отпусков (VAC8/VAC0)
        postprocess.apply_vacations(schedule, eff_vacations, gen.shift_types)

        # пересчёт carry_out после всех сдвигов
        if schedule:
            last_day = max(schedule.keys())
            next_year = last_day.year + (1 if last_day.month == 12 else 0)
            next_month = 1 if last_day.month == 12 else last_day.month + 1
            new_carry_out: List[Assignment] = []
            for entry in schedule[last_day]:
                code = gen.code_of(entry.shift_key).upper()
                if code in {"N4A", "N4B"}:
                    key = "n8_a" if code.endswith("A") else "n8_b"
                    st = gen.shift_types[key]
                    new_carry_out.append(
                        Assignment(
                            entry.employee_id,
                            date(next_year, next_month, 1),
                            key,
                            st.hours,
                            source="autofix",
                        )
                    )
            carry_out = new_carry_out

        # -------- СЛОЙ СОКРАЩЕНИЙ (ПОСЛЕДНИМ) --------
        raw_norm = month_spec.get("norm_hours_month")
        norm = int(raw_norm) if raw_norm is not None else int(calendar.norm_hours(y, m) or 0)
        gen.enforce_hours_caps(employees, schedule, norm, ym)

        # валидации и диагностика (уже после сокращений)
        smoke = validation.coverage_smoke(ym, schedule, gen.code_of, first_days=cfg2.get("pair_breaking",{}).get("window_days",6)+2)
        trace = validation.phase_trace(ym, employees, schedule, gen.code_of, gen=None, days=10)

        # отчёты
        base = f"{scn['name']}_{ym}"
        xlsx_path = out_dir / f"{base}.xlsx"
        csv_grid_path = out_dir / f"{base}_grid.csv"
        report.write_workbook(str(xlsx_path), ym, employees, schedule, calendar=calendar)
        report.write_csv_grid(str(csv_grid_path), ym, employees, schedule)

        metrics_emp_path = out_dir / f"{base}_metrics_employees.csv"
        metrics_days_path = out_dir / f"{base}_metrics_days.csv"
        report.write_metrics_employees_csv(str(metrics_emp_path), employees, schedule)
        report.write_metrics_days_csv(str(metrics_days_path), schedule)

        norm_info = gen.last_norms_info() or {}
        norms_path = out_dir / f"{base}_norms.txt"
        _, norm_warnings, _ = report.write_norms_report(
            str(norms_path),
            ym,
            employees,
            schedule,
            norm_info,
        )

        pairs_after = analytics.compute_pairs(schedule, gen.code_of)
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
            if apply_log:
                log_lines.extend([f" - {x}" for x in apply_log])
            else:
                log_lines.append(" - no-ops")
            if ops_log:
                log_lines.append("[pair_breaking.ops]")
                log_lines.extend([f" - {x}" for x in ops_log])
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
            log_lines.append("[validation.baseline.issues]")
            log_lines.extend([f" - {x}" for x in baseline_issues])
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
            apply_log=apply_log if apply_log else ops_log[:],
            ops_log=ops_log,
            pair_score_before=pair_score_before,
            pair_score_after=pair_score_after,
        )
        print(f"[report.pairs->_log] appended: {appended_log_path}")

        prev_pairs_for_month = pairs_after
        scn["prev_pairs_for_month"] = prev_pairs_for_month

        # хвост → следующий месяц
        prev_tail_by_emp = extract_tail(schedule, employees, gen)
        carry_in = carry_out

        # анти-соло счётчик: если в месяце были соло-дни — инкремент сотруднику
        solo_days = analytics.solo_days_by_employee(schedule, gen.code_of)
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
def main():
    """
    Новая точка входа: запускаем все сценарии из ./scenarios/*.json.
    Никаких закодированных сценариев в модуле не остаётся.
    """
    base_dir = Path(__file__).parent
    scn_dir = SCENARIOS_DIR
    out_root = base_dir / "reports"
    out_root.mkdir(exist_ok=True)

    scenarios = load_scenarios_from_dir(scn_dir)
    if not scenarios:
        print(f"[scenarios] no JSON scenarios found in {scn_dir}")
        return

    for scn in scenarios:
        print(f"[scenarios] run: {scn.get('name','<unnamed>')}")
        # Вызов вашей существующей оркестрации: базовый генератор + балансировка + отчёты
        run_scenario(scn, out_root)


if __name__ == "__main__":
    main()
