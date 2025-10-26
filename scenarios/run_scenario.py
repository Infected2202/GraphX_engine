"""Run legacy scenario files with the refactored engine."""
from __future__ import annotations

import argparse
import copy
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.config_loader import load_config
from adapters.repository import ScheduleRepository
from adapters.report import csv_writer, metrics_writer, xlsx_writer
from domain.models import Employee
from services.scheduler import SchedulerService


DEFAULT_SHIFT_TYPES: Dict[str, Dict[str, object]] = {
    "day_a": {"code": "DA", "office": "A", "hours": 12, "is_working": True, "label": "Day A"},
    "day_b": {"code": "DB", "office": "B", "hours": 12, "is_working": True, "label": "Day B"},
    "night_a": {"code": "NA", "office": "A", "hours": 12, "is_working": True, "label": "Night A"},
    "night_b": {"code": "NB", "office": "B", "hours": 12, "is_working": True, "label": "Night B"},
    "n4_a": {"code": "N4A", "office": "A", "hours": 4, "is_working": True, "label": "Night 4 A"},
    "n4_b": {"code": "N4B", "office": "B", "hours": 4, "is_working": True, "label": "Night 4 B"},
    "n8_a": {"code": "N8A", "office": "A", "hours": 8, "is_working": True, "label": "Night 8 A"},
    "n8_b": {"code": "N8B", "office": "B", "hours": 8, "is_working": True, "label": "Night 8 B"},
    "off": {"code": "OFF", "office": None, "hours": 0, "is_working": False, "label": "Off"},
    "vac_wd8": {"code": "VAC8", "office": None, "hours": 8, "is_working": False, "label": "Vacation"},
    "vac_we0": {"code": "VAC0", "office": None, "hours": 0, "is_working": False, "label": "Vacation 0"},
}

DEFAULT_EMPLOYEES = [
    {"id": f"E0{i}", "name": f"Сотрудник {i}"} for i in range(1, 9)
]

DEFAULT_CONFIG = {
    "shift_types": DEFAULT_SHIFT_TYPES,
    "default_pattern": ["day_a", "night_a", "off", "off", "day_b", "night_b", "off", "off"],
    "shortener": {"max_hours": 11},
    "balancer": {"night_overlap_threshold": 4, "enabled": True},
}


def _load_employees(raw: Iterable[Dict[str, object]]) -> List[Employee]:
    employees: List[Employee] = []
    for spec in raw:
        employees.append(
            Employee(
                id=str(spec["id"]),
                name=str(spec.get("name", spec["id"])),
                is_trainee=bool(spec.get("is_trainee", spec.get("intern", False))),
                mentor_id=spec.get("mentor_id"),
                ytd_overtime=int(spec.get("ytd_overtime", 0)),
            )
        )
    return employees


def _coerce_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _expand_vacation_entry(entry) -> List[date]:
    if entry is None:
        return []
    if isinstance(entry, (list, tuple, set)):
        dates: List[date] = []
        for item in entry:
            dates.extend(_expand_vacation_entry(item))
        return dates
    if isinstance(entry, dict):
        start_raw = entry.get("start") or entry.get("from")
        end_raw = entry.get("end") or entry.get("to") or start_raw
        if not start_raw:
            return []
        start = _coerce_date(start_raw)
        end = _coerce_date(end_raw)
        if end < start:
            start, end = end, start
        out: List[date] = []
        cur = start
        while cur <= end:
            out.append(cur)
            cur += timedelta(days=1)
        return out
    return [_coerce_date(entry)]


def _normalize_vacations_map(raw: Dict[str, object] | None) -> Dict[str, List[str]]:
    if not raw:
        return {}
    normalized: Dict[str, List[str]] = {}
    for employee_id, entry in raw.items():
        dates = {_date.isoformat() for _date in _expand_vacation_entry(entry)}
        if dates:
            normalized[employee_id] = sorted(dates)
    return normalized


def _base_config() -> Dict[str, object]:
    return copy.deepcopy(DEFAULT_CONFIG)


def _scenario_config(scenario: Dict[str, object]) -> Dict[str, object]:
    config = _base_config()
    overrides = scenario.get("config", {}) or {}

    if overrides.get("pair_breaking"):
        pair_cfg = overrides["pair_breaking"]
        config["balancer"].update(
            {
                "enabled": pair_cfg.get("enabled", config["balancer"].get("enabled", True)),
                "night_overlap_threshold": pair_cfg.get(
                    "overlap_threshold", config["balancer"].get("night_overlap_threshold", 4)
                ),
            }
        )

    if overrides.get("shortener"):
        config["shortener"].update(overrides["shortener"])

    if overrides.get("default_pattern"):
        config["default_pattern"] = list(overrides["default_pattern"])

    if overrides.get("shift_types"):
        config["shift_types"].update(overrides["shift_types"])

    return config


def _scenario_employees(scenario: Dict[str, object]) -> List[Employee]:
    raw = scenario.get("employees")
    if not raw:
        raw = (scenario.get("config", {}) or {}).get("employees")
    if not raw:
        raw = DEFAULT_EMPLOYEES
    return _load_employees(raw)


def _scenario_months(scenario: Dict[str, object]) -> List[Dict[str, object]]:
    overrides = scenario.get("config", {}) or {}
    months_spec = overrides.get("months") or []
    extra_vac = _normalize_vacations_map(overrides.get("vacations") or scenario.get("vacations"))

    months: List[Dict[str, object]] = []
    for month_spec in months_spec:
        month = month_spec.get("month") or month_spec.get("ym") or month_spec.get("month_year")
        if not month:
            continue
        vacations = _normalize_vacations_map(month_spec.get("vacations"))
        if extra_vac:
            for emp_id, days in extra_vac.items():
                merged = set(vacations.get(emp_id, [])) | set(days)
                vacations[emp_id] = sorted(merged)
        month_cfg = {"month": month, "vacations": vacations}
        if month_spec.get("pair_breaking"):
            month_cfg["balancer"] = {
                "enabled": month_spec["pair_breaking"].get("enabled", True),
                "night_overlap_threshold": month_spec["pair_breaking"].get("overlap_threshold", 4),
            }
        if month_spec.get("max_hours") is not None:
            month_cfg["max_hours"] = month_spec["max_hours"]
        months.append(month_cfg)
    return months


def _discover_scenarios(paths: Iterable[str] | None) -> List[Path]:
    if paths:
        return [Path(p) for p in paths]
    root = Path(__file__).parent
    return sorted(p for p in root.glob("*.json") if p.is_file())


def run(path: Path, *, output_root: Path) -> None:
    scenario = load_config(path)
    config = _scenario_config(scenario)
    employees = _scenario_employees(scenario)
    months = _scenario_months(scenario)
    if not months:
        raise RuntimeError(f"Scenario {path} does not define any months")

    service = SchedulerService(config)

    scenario_name = scenario.get("name") or path.stem
    scenario_output = output_root / scenario_name
    scenario_output.mkdir(parents=True, exist_ok=True)
    repository_path = scenario_output / f"{scenario_name}.db"
    repository = ScheduleRepository(repository_path)

    for month_config in months:
        schedule, stats = service.generate_month(month_config, employees)
        month = month_config["month"]
        repository.save_month(month, schedule)

        csv_writer.write_grid(scenario_output / f"{month}_grid.csv", schedule, employees)
        metrics_writer.write_employee_metrics(
            scenario_output / f"{month}_metrics_employees.csv", schedule, employees
        )
        metrics_writer.write_day_metrics(
            scenario_output / f"{month}_metrics_days.csv", schedule
        )
        try:
            xlsx_writer.write_grid(
                scenario_output / f"{month}.xlsx", schedule, employees, title=f"{scenario_name} {month}"
            )
        except xlsx_writer.XLSXExportUnavailable as exc:
            print(f"[warning] {exc}")


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run legacy GraphX scenarios")
    parser.add_argument("paths", nargs="*", help="Specific scenario files to run")
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=PROJECT_ROOT / "reports",
        help="Directory where reports will be written",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    scenario_paths = _discover_scenarios(args.paths)
    if not scenario_paths:
        raise SystemExit("No scenarios found")

    for path in scenario_paths:
        print(f"[run] scenario {path}")
        run(path, output_root=output_root)


if __name__ == "__main__":
    main()
