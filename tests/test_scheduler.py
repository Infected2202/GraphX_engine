from datetime import date

from adapters.config_loader import load_config
from adapters.repository import ScheduleRepository
from domain.models import Employee
from services.scheduler import SchedulerService


def _employees_from_config(config):
    return [Employee(id=spec["id"], name=spec.get("name", spec["id"])) for spec in config["employees"]]


def test_generate_month_and_repository_roundtrip(tmp_path):
    config = load_config("scenarios/configs/sample.json")
    service = SchedulerService(config)
    employees = _employees_from_config(config)

    month_config = config["months"][0]
    schedule, stats = service.generate_month(month_config, employees)

    assert list(schedule), "schedule should contain days"
    assert stats.shorten_operations, "shortening should be applied"

    repo_path = tmp_path / "graphx.db"
    repo = ScheduleRepository(repo_path)
    repo.save_month(month_config["month"], schedule)
    loaded = repo.load_month(month_config["month"], code_lookup=service.code_of)
    assert list(loaded) == list(schedule)

    vacation_day = date(2024, 1, 5)
    assert any(assign.source == "vacation" for assign in schedule[vacation_day])
