from datetime import date

from domain.models import Assignment
from domain.schedule import Schedule


def make_assignment(emp: str, day: date, key: str, hours: int) -> Assignment:
    return Assignment(employee_id=emp, date=day, shift_key=key, effective_hours=hours, source="test")


def test_schedule_assign_and_get_code():
    schedule = Schedule(code_lookup=lambda key: {"d": "DA", "n": "NA"}[key])
    schedule.assign(make_assignment("E1", date(2024, 1, 1), "d", 12))
    schedule.assign(make_assignment("E1", date(2024, 1, 2), "n", 12))
    assert schedule.get_code("E1", date(2024, 1, 1)) == "DA"
    assert schedule.get_code("E1", date(2024, 1, 2)) == "NA"


def test_schedule_hours_by_employee():
    schedule = Schedule()
    schedule.assign(make_assignment("E1", date(2024, 1, 1), "d", 12))
    schedule.assign(make_assignment("E1", date(2024, 1, 2), "d", 12))
    schedule.assign(make_assignment("E2", date(2024, 1, 1), "n", 10))
    assert schedule.hours_by_employee() == {"E1": 24, "E2": 10}


def test_pair_overlap_detects_days():
    schedule = Schedule()
    schedule.assign(make_assignment("A", date(2024, 1, 1), "d", 12))
    schedule.assign(make_assignment("B", date(2024, 1, 1), "n", 12))
    schedule.assign(make_assignment("A", date(2024, 1, 2), "d", 12))
    assert schedule.pair_overlap("A", "B") == [date(2024, 1, 1)]
