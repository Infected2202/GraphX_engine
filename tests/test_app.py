from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test.sqlite"
    app = create_app({
        "TESTING": True,
        "DATABASE": str(db_path),
        "AUTO_INIT_DB": True,
    })
    with app.test_client() as client:
        yield client


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.data == b"OK"


def test_generate_and_fetch_schedule(client):
    month = "2025-09"
    resp_generate = client.post("/api/schedule/generate", json={"month": month})
    assert resp_generate.status_code == 200
    payload = resp_generate.get_json()
    assert payload["ok"] is True

    resp_schedule = client.get(f"/api/schedule?month={month}")
    assert resp_schedule.status_code == 200
    data = resp_schedule.get_json()
    assert data["month"] == month
    assert "employees" in data


def test_export_and_reports(client):
    month = "2025-09"
    client.post("/api/schedule/generate", json={"month": month})

    resp_export = client.get(f"/api/export/xlsx?month={month}")
    assert resp_export.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in resp_export.headers["Content-Type"]

    resp_report = client.get(f"/api/reports/hours?month={month}")
    assert resp_report.status_code == 200
    report = resp_report.get_json()
    assert "employees" in report
