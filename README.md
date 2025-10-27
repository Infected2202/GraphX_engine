# GraphX Engine Web

This repository wraps the existing `engine/` generator in a lightweight Flask + SQLite web UI. The application exposes pages for the schedule editor, employees, calendar data, shift types, reports, and settings. A small REST API backs the UI and allows automation workflows.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app.py
flask run
```

The server seeds a SQLite database on first boot (stored under `instance/graphx.sqlite`). Open [http://localhost:5000/editor](http://localhost:5000/editor) to view the schedule grid. Use the buttons to trigger generation, export XLSX, and post JSON draft edits.

### Useful API endpoints

- `GET /api/schedule?month=YYYY-MM`
- `POST /api/schedule/generate`
- `POST /api/schedule/draft`
- `POST /api/schedule/commit`
- `GET /api/export/xlsx`
- `GET /api/employees`
- `GET /api/calendar`
- `GET /api/reports/hours`

## Tests

```bash
pytest
```

Tests spin up the Flask app with an isolated SQLite database and cover generation, export, and reporting flows.
