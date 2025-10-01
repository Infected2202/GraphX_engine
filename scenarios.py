# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import os

from config import CONFIG as BASE_CONFIG
from generator import Generator, Assignment
import pairing
import report


# ---------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ УТИЛИТЫ
# ---------------------------------------------------------------------------

def daterange(d1: date, d2: date) -> List[date]:
    """Включительно: [d1..d2]."""

    out = []
    cur = d1
    while cur <= d2:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def deep_copy_config(cfg: dict) -> dict:
    """Плоский deepcopy для нашего конфига (без сложных ссылок)."""

    out = {k: v for k, v in cfg.items()}
    out["months"] = [dict(m) for m in cfg["months"]]
    out["employees"] = [dict(e) for e in cfg["employees"]]
    out["shift_types"] = {k: dict(v) for k, v in cfg["shift_types"].items()}
    if "logging" in out:
        out["logging"] = dict(out["logging"])
    if "pair_breaking" in out:
        out["pair_breaking"] = dict(out["pair_breaking"])
    return out


def filter_employees(cfg: dict, keep_ids: List[str]) -> dict:
    cfg2 = deep_copy_config(cfg)
    keep = set(keep_ids)
    cfg2["employees"] = [e for e in cfg2["employees"] if e["id"] in keep]
    return cfg2


def merge_vacations(cfg: dict, extra_vac: Dict[str, List[date]]) -> dict:
    """Добавляет даты отпусков (по сотрудникам) во ВСЕ month_spec."""

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


def aggregate_effective_vacations(
    cfg_months: List[dict], current_ym: str, gen: Generator, current_emp_ids: set[str]
) -> Dict[str, List[date]]:
    """Собираем отпуска из всех month_spec, но оставляем только даты текущего окна."""

    d0, d1 = month_bounds(gen, current_ym)
    eff: Dict[str, List[date]] = {}
    for ms in cfg_months:
        vac = ms.get("vacations", {}) or {}
        for eid, dates in vac.items():
            if eid not in current_emp_ids:
                continue
            for dt in dates:
                if d0 <= dt <= d1:
                    eff.setdefault(eid, []).append(dt)
    return {eid: sorted(set(dts)) for eid, dts in eff.items()}


def synthetic_prev_tail_and_carry_in(
    first_day: date, existing_ids: set[str], gen: Generator
) -> Tuple[Dict[str, List[str]], List[Assignment]]:
    """Возвращает синтетический хвост и carry-in, отфильтрованные по списку сотрудников."""

    prev_tail_by_emp = {
        "E01": ["OFF", "DB", "OFF", "OFF"],
        "E02": ["OFF", "OFF", "OFF", "DA"],
        "E03": ["DA", "OFF", "NA", "OFF"],
        "E04": ["DA", "OFF", "OFF", "N4A"],
        "E05": ["OFF", "DA", "OFF", "OFF"],
        "E06": ["OFF", "OFF", "OFF", "DB"],
        "E07": ["DB", "OFF", "NB", "OFF"],
        "E08": ["DB", "OFF", "OFF", "N4B"],
    }
    prev_tail_by_emp = {eid: tail for eid, tail in prev_tail_by_emp.items() if eid in existing_ids}

    carry_in: List[Assignment] = []
    if "E04" in existing_ids:
        carry_in.append(
            Assignment("E04", first_day, "n8_a", gen.shift_types["n8_a"].hours, source="template")
        )
    if "E08" in existing_ids:
        carry_in.append(
            Assignment("E08", first_day, "n8_b", gen.shift_types["n8_b"].hours, source="template")
        )
    return prev_tail_by_emp, carry_in


def extract_tail(schedule, employees, gen: Generator) -> Dict[str, List[str]]:
    """Берём последние 4 дня месяца и возвращаем по каждому сотруднику список кодов смен."""

    dates_sorted = sorted(schedule.keys())
    tail_dates = dates_sorted[-4:] if len(dates_sorted) >= 4 else dates_sorted
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
# СЦЕНАРИИ
# ---------------------------------------------------------------------------

def scenarios_def() -> List[dict]:
    """Набор сценариев с различной мощностью смен и отпусками."""

    return [
        {
            "name": "S_base_8",
            "keep_ids": ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08"],
            "vacations": {},
        },
        {
            "name": "S_7_no_E08",
            "keep_ids": ["E01", "E02", "E03", "E04", "E05", "E06", "E07"],
            "vacations": {},
        },
        {
            "name": "S_6_no_E07_E08",
            "keep_ids": ["E01", "E02", "E03", "E04", "E05", "E06"],
            "vacations": {},
        },
        {
            "name": "S_5_solo_pressure",
            "keep_ids": ["E01", "E02", "E03", "E04", "E05"],
            "vacations": {},
        },
        {
            "name": "S_4_minimal",
            "keep_ids": ["E01", "E02", "E03", "E04"],
            "vacations": {},
        },
        {
            "name": "S_vac_E08_aug26_sep03",
            "keep_ids": ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08"],
            "vacations": {
                "E08": daterange(date(2025, 8, 26), date(2025, 9, 3)),
            },
        },
        {
            "name": "S_vac_E07_sep01_sep06",
            "keep_ids": ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08"],
            "vacations": {
                "E07": daterange(date(2025, 9, 1), date(2025, 9, 6)),
            },
        },
        {
            "name": "S_5_with_vac_mix",
            "keep_ids": ["E01", "E02", "E03", "E04", "E05"],
            "vacations": {
                "E04": daterange(date(2025, 8, 29), date(2025, 9, 2)),
            },
        },
    ]


# ---------------------------------------------------------------------------
# ЗАПУСК ОДНОГО СЦЕНАРИЯ
# ---------------------------------------------------------------------------

def run_scenario(scn: dict, out_root: Path):
    cfg0 = deep_copy_config(BASE_CONFIG)
    cfg1 = filter_employees(cfg0, scn["keep_ids"])
    cfg2 = merge_vacations(cfg1, scn.get("vacations", {}))

    gen = Generator(cfg2)
    code_map = {k: v.code for k, v in gen.shift_types.items()}
    report.set_code_map(code_map)

    out_dir = out_root / scn["name"]
    out_dir.mkdir(parents=True, exist_ok=True)

    prev_tail_by_emp: Dict[str, List[str]] = {}
    carry_in: List[Assignment] = []

    for idx, month_spec in enumerate(cfg2["months"]):
        ym = month_spec["month_year"]
        y, m = map(int, ym.split("-"))
        first_day = date(y, m, 1)
        current_emp_ids = {rec["id"] for rec in cfg2["employees"]}

        if idx == 0:
            prev_tail_by_emp, carry_in = synthetic_prev_tail_and_carry_in(first_day, current_emp_ids, gen)

        eff_vacations = aggregate_effective_vacations(cfg2["months"], ym, gen, current_emp_ids)
        month_spec_eff = dict(month_spec)
        month_spec_eff["vacations"] = eff_vacations

        employees, schedule, carry_out = gen.generate_month(
            month_spec_eff,
            carry_in=carry_in,
            prev_tail_by_emp=prev_tail_by_emp,
        )

        base = f"{scn['name']}_{ym}"
        xlsx_path = out_dir / f"{base}.xlsx"
        csv_grid_path = out_dir / f"{base}_grid.csv"
        report.write_workbook(str(xlsx_path), ym, employees, schedule)
        report.write_csv_grid(str(csv_grid_path), ym, employees, schedule)

        metrics_emp_path = out_dir / f"{base}_metrics_employees.csv"
        metrics_days_path = out_dir / f"{base}_metrics_days.csv"
        report.write_metrics_employees_csv(str(metrics_emp_path), employees, schedule)
        report.write_metrics_days_csv(str(metrics_days_path), schedule)

        pairs = pairing.compute_pairs(schedule, gen.code_of)
        pairs_path = out_dir / f"{base}_pairs.csv"
        report.write_pairs_csv(str(pairs_path), pairs, employees)

        log_lines = []
        if idx == 0 and prev_tail_by_emp:
            log_lines.append(
                f"[bootstrap] synthetic prev_tail for first month (employees={len(prev_tail_by_emp)})"
            )
        if carry_in:
            ap = ", ".join([f"{a.employee_id}={gen.code_of(a.shift_key)}" for a in carry_in])
            log_lines.append(f"[carry_in] {ym}-01: {ap}")
        if carry_out:
            co = ", ".join(
                [f"{a.employee_id}={gen.code_of(a.shift_key)}@{a.date.isoformat()}" for a in carry_out]
            )
            log_lines.append(f"[carry_out] to next month: {co}")
        if eff_vacations:
            log_lines.append("[vacations.effective]")
            for eid, ds in eff_vacations.items():
                log_lines.append(f"{eid}: {', '.join(sorted({d.isoformat() for d in ds}))}")
        log_path = out_dir / f"{base}_log.txt"
        report.write_log_txt(str(log_path), log_lines)

        prev_tail_by_emp = extract_tail(schedule, employees, gen)
        carry_in = carry_out

    print(f"[SCN DONE] {scn['name']} → {out_dir}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    out_root = Path(os.getcwd()) / "reports" / "scenarios"
    out_root.mkdir(parents=True, exist_ok=True)

    for scn in scenarios_def():
        run_scenario(scn, out_root)

    print("Все сценарии выполнены.")
