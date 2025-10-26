from datetime import date

from domain.shift_types import code_to_token, hours_for_code


def test_code_to_token_first_day_night_eight():
    assert code_to_token("N8A", date(2024, 1, 1)) == "O"
    assert code_to_token("N8A", date(2024, 1, 2)) == "N"


def test_hours_for_code_known_values():
    assert hours_for_code("DA") == 12
    assert hours_for_code("M8A") == 8
    assert hours_for_code("N4A") == 4
    assert hours_for_code("VAC0") == 0
