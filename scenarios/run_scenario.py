"""Run a simple GraphX generation scenario."""
from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.config_loader import load_config
from adapters.repository import ScheduleRepository
from adapters.report import csv_writer, metrics_writer, xlsx_writer
from domain.models import Employee
from services.scheduler import SchedulerService


def _load_employees(raw) -> list[Employee]:
    employees = []
    for spec in raw:
        employees.append(
            Employee(
                id=spec["id"],
                name=spec.get("name", spec["id"]),
                is_trainee=spec.get("is_trainee", False),
                mentor_id=spec.get("mentor_id"),
                ytd_overtime=int(spec.get("ytd_overtime", 0)),
            )
        )
    return employees


def run(config_path: str | Path) -> None:
    config = load_config(config_path)
    employees = _load_employees(config["employees"])
    service = SchedulerService(config)
    repository = ScheduleRepository(config.get("repository", "graphx.db"))
    output_dir = Path(config.get("output_dir", "reports"))
    output_dir.mkdir(parents=True, exist_ok=True)

    for month_config in config["months"]:
        schedule, stats = service.generate_month(month_config, employees)
        month = month_config["month"]
        repository.save_month(month, schedule)

        csv_writer.write_grid(output_dir / f"{month}_grid.csv", schedule, employees)
        metrics_writer.write_employee_metrics(output_dir / f"{month}_metrics_employees.csv", schedule, employees)
        metrics_writer.write_day_metrics(output_dir / f"{month}_metrics_days.csv", schedule)
        try:
            xlsx_writer.write_grid(output_dir / f"{month}.xlsx", schedule, employees, title=month)
        except xlsx_writer.XLSXExportUnavailable as exc:
            print(f"[warning] {exc}")


if __name__ == "__main__":
    run("scenarios/configs/sample.json")
