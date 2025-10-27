# Port GraphX_engine to a local Flask + SQLite web app (MVP)

This ExecPlan is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` up to date as work proceeds. Treat the reader as a complete beginner to this repo: they have only the current working tree and this file.

If a canonical PLANS.md template exists in your org, maintain this document in accordance with it.

## Purpose / Big Picture

We will expose GraphX_engine’s schedule generator via a local, single-user web app using Flask and SQLite (no build step, runs locally). Users can:
- Generate a monthly schedule (using the **previous calendar month** for context).
- Edit cells (change shift keys, multi-select, phase-shift), stage edits in a **draft**, then commit.
- Manage employees, calendar (holidays, norms, vacations), shift-type legend/formatting, and settings.
- Export XLSX and view built-in reports/metrics.

By the end, starting the app and visiting `http://localhost:5000/` will present a sidebar with **Editor, Employees, Calendar, Shift Types, Reports, Settings** and a working editor grid that mirrors the existing XLSX styling.

## Constraints

- Single user, local only. No auth. No external services.
- Flask + SQLite; avoid heavy front-end build tooling. Jinja templates + light JS only.
- Repo path names must be explicit and stable. Prefer additive changes over refactors.
- Generator must be callable as a **pure library function** (no CLI I/O, no “prev_tail_by_emp”). Context is the previous month.

## Progress

Use timestamps (UTC or local) to record progress. Split partially done tasks so “done” vs “remaining” is unambiguous.

- [ ] (YYYY-MM-DD HH:MM) Create virtualenv, add minimal requirements, app skeleton boots: `/healthz` = OK.
- [ ] Editor page renders grid from DB for a chosen month (read-only).
- [ ] Generator adapter: `generate_schedule(month)` returns matrix; `/api/schedule/generate` populates DB.
- [ ] XLSX export endpoint returns a valid file.
- [ ] Draft edits table + apply/commit flow wired to grid.
- [ ] Employees CRUD + JSON import.
- [ ] Calendar (holidays/norms/vacations) CRUD + JSON import.
- [ ] Shift types (legend/colors) JSON editor + live mapping to cell classes.
- [ ] Settings JSON editor (all prior config fields).
- [ ] Reports page (at least: hours per employee/office) + CSV/XLSX export.
- [ ] Seed DB with synthetic data on first run.
- [ ] Smoke/integration tests (pytest + Flask client) passing.
- [ ] README quickstart and this plan updated with Decisions/Outcomes.

## Surprises & Discoveries

Document unexpected behaviors succinctly with evidence.

- Observation: …
  Evidence: …

## Decision Log

Record every decision with rationale.

- Decision: **SQLite without ORM (DAO layer only).**
  Rationale: Single-user local app; faster to ship; less moving parts.
  Date/Author: …

- Decision: **Static front-end (Jinja + light JS).**
  Rationale: No build step; MVP scope; option to add HTMX/Alpine later if needed.
  Date/Author: …

- Decision: **Separate `settings.json` and `shift_types.json`.**
  Rationale: Keep visualization/legend isolated; easier to version and edit.
  Date/Author: …

- Decision: **“Previous month” rule is authoritative.**
  Rationale: Replaces prior `prev_tail_by_emp`; simplifies API contract and UI.
  Date/Author: …

## Outcomes & Retrospective

Summarize what shipped, proof it works, gaps and next steps.

- Outcome: …
- Evidence: …
- Lessons: …

## Context and Orientation

Repository: `Infected2202/GraphX_engine` (Python project). There is an `engine/` directory containing the existing generator and XLSX styling logic. Assume the generator currently runs as scripts/functions that produce stylized tables and reports.

**Goal:** Do not rewrite the engine. Instead, wrap it with a web-friendly adapter, capture inputs from DB/JSON, and persist outputs back to DB/XLSX.

**MVP data model (SQLite tables):**

- `employees(id, fio, key, office, attrs_json, is_active)`
- `months(id, ym TEXT UNIQUE)` — `YYYY-MM`
- `schedule_cells(id, month_id, emp_id, day INTEGER, value TEXT, office TEXT, meta_json)`
- `draft_edits(id, month_id, emp_id, day, new_value, new_office, op TEXT, created_at)`
- `calendar_days(id, date TEXT UNIQUE, day_type TEXT, norm_minutes INTEGER)` — `day_type` ∈ {workday, weekend, holiday, shifted}
- `vacations(id, emp_id, start_date, end_date, kind TEXT)`
- `reports(id, month_id, name, payload_json, created_at)`
- `settings(id INTEGER PRIMARY KEY, payload_json)` — single row (id=1)

**Configs on disk (JSON):**
- `configs/settings.json` — generator/global settings.
- `configs/shift_types.json` — mapping `key -> {label, text_color, bg_color, css_class, …}`.

## Plan of Work

Narrative description of edits and additions with precise paths. Keep changes additive and testable.

### 1) New web app skeleton (no build tools)

Create:

```

app.py                          # create_app(), register blueprints
blueprints/
editor/routes.py
employees/routes.py
calendar/routes.py
shifts/routes.py
reports/routes.py
settings/routes.py
services/
generator_adapter.py
schedule_service.py
reports_service.py
dao/
db.py
employees_dao.py
schedule_dao.py
draft_dao.py
calendar_dao.py
settings_dao.py
templates/
_layout.html
editor/index.html
employees/index.html
calendar/index.html
shifts/index.html
reports/index.html
settings/index.html
static/
css/app.css
js/editor.js
configs/
settings.json
shift_types.json
migrations/
0001_init.sql
seeds/
seed.sql

```

- `dao/db.py`: open SQLite with `row_factory=sqlite3.Row`; `apply_migrations()` runs SQL files in lexical order, idempotently (`IF NOT EXISTS`).
- `app.py`: `create_app()` wires blueprints at `/`, `/api/*`; `/healthz` returns `200 OK`.
- `templates/_layout.html`: sidebar with sections; simple CSS.

### 2) Generator adapter and contracts

- `services/generator_adapter.py` exposes:

```

def generate_schedule(month_ym: str, *, employees, calendar, settings, shift_types):
"""
Returns:
{
"month": "YYYY-MM", "days_in_month": N,
"cells": [
{"emp_id": int, "day": int, "value": "DA|NB|OFF|...", "office": "NA|NB|...", "meta": {...}}
],
"metrics": {...}
}
"""

```

- Adapter loads inputs from DB/JSON, calls into `engine/` (identify and import the function(s) producing the monthly plan), **does not write files**, and returns in-memory structures. If XLSX export is requested, call the engine’s XLSX writer with the prepared matrix and return `BytesIO` to the Flask response.

- Define a pure helper `previous_month("YYYY-MM") -> "YYYY-MM"` and ensure the engine uses previous calendar month for context, never `prev_tail_by_emp`.

### 3) Editor (read-only → editable)

- `GET /editor?month=YYYY-MM` renders grid from `schedule_cells`.
- `GET /api/schedule?month=YYYY-MM` returns JSON matrix.
- `POST /api/schedule/generate?month=YYYY-MM` calls adapter and bulk-upserts `schedule_cells` in a transaction; clears `draft_edits`.
- `POST /api/schedule/draft` accepts `{edits:[{emp_id,day,op,new_value,new_office,"+":1?}]}` and stores in `draft_edits`.
- `POST /api/schedule/commit` applies `draft_edits` to `schedule_cells` atomically and clears the draft.

- `templates/editor/index.html`: grid with month chooser, buttons **Generate**, **Export XLSX**, **Apply Draft**. Use `<select>` overlays on click for shift keys; multi-select via `Ctrl` (keep selection on client) and send batch in `POST /api/schedule/draft`.

- `static/js/editor.js`: very small vanilla JS to (a) fetch data, (b) maintain selection, (c) post edits, (d) refresh grid.

### 4) Employees

- `GET /employees` + CRUD API: `GET/POST/PUT/DELETE /api/employees`.
- JSON import: `POST /api/employees/import` accepts array of employees with keys.

### 5) Calendar & Vacations

- `GET /calendar?year=YYYY` shows mini-calendar with toggles for `day_type`, norm minutes, and vacation spans per employee.
- APIs:
- `GET/POST /api/calendar?year=YYYY` (upsert many days).
- `POST /api/vacations` (create/update intervals).
- `POST /api/calendar/import` (JSON compatible with current engine).

### 6) Shift Types & Settings

- `GET /shifts` reads `configs/shift_types.json` and shows legend; `POST /api/shift-types` writes it back atomically (temp + replace).
- `GET /settings` reads `configs/settings.json`; `POST /api/settings` writes it back. Validate known fields.

### 7) Reports & Export

- `GET /reports?month=YYYY-MM` lists available reports.
- `GET /api/reports/<name>?month=YYYY-MM` returns JSON/CSV.
- `GET /api/export/xlsx?month=YYYY-MM` streams XLSX (`Content-Disposition: attachment`).

### 8) Migrations & Seed

- `migrations/0001_init.sql` creates all tables; all `CREATE TABLE IF NOT EXISTS`.
- `seeds/seed.sql` pre-populates `employees`, a baseline `calendar_days`, and one demo month’s `schedule_cells`.
- On boot, if DB empty, run seed.

### 9) Testing

- Add `tests/` with:
- `test_boot.py`: `/healthz` OK.
- `test_generate.py`: POST generate, then GET schedule returns non-empty cells for target month.
- `test_draft_commit.py`: apply draft edit, commit, and observe cell changed.
- `test_export.py`: XLSX endpoint returns file-like response.

## Concrete Steps

Commands are relative to repo root.

1) **Environment & deps**

  python -m venv .venv
  . .venv/bin/activate          # Windows: .venv\Scripts\activate
  pip install --upgrade pip
  pip install flask python-dateutil openpyxl pytest

  echo "flask\npython-dateutil\nopenpyxl\npytest" > requirements.txt

2) **Scaffold directories**

  mkdir -p blueprints/{editor,employees,calendar,shifts,reports,settings} services dao templates/{editor,employees,calendar,shifts,reports,settings} static/{css,js} configs migrations seeds tests

3) **Create `app.py` with `create_app()`** and register blueprints. Add `/healthz`.

4) **Add `dao/db.py`** with `get_db()` and `apply_migrations()`; create `migrations/0001_init.sql` with the schema listed above. On app start, call `apply_migrations()`.

5) **Templates**: `_layout.html` with sidebar; `editor/index.html` with an empty grid `<table id="grid">` and minimal CSS. Add `static/js/editor.js` for fetching and rendering JSON matrix.

6) **Adapter**: `services/generator_adapter.py` implementing `generate_schedule(month_ym, *, employees, calendar, settings, shift_types)`; inside, import from `engine` and map existing outputs to the matrix shape. Ensure no file I/O.

7) **Editor API**: implement `GET /api/schedule`, `POST /api/schedule/generate`, `POST /api/schedule/draft`, `POST /api/schedule/commit` in `blueprints/editor/routes.py`. Back these with `services/schedule_service.py` and DAOs.

8) **Employees/Calendar/Shift Types/Settings/Reports**: add read/write endpoints and pages as described in Plan of Work.

9) **Seed**: create `seeds/seed.sql` to insert a handful of employees, a month (`YYYY-MM`), and a small matrix (e.g., 2 employees × 7 days) plus basic `calendar_days`.

10) **Run & verify**

  FLASK_APP=app.py FLASK_ENV=development flask run

Expected:

- `GET http://localhost:5000/healthz` -> `OK`.
- `GET /editor?month=2025-09` renders a grid (even if empty initially).
- `POST /api/schedule/generate?month=2025-09` returns `{ok:true}`; reload shows cells.
- `POST /api/schedule/draft` with one edit returns `{count:1}`; `POST /api/schedule/commit` applies it.
- `GET /api/export/xlsx?month=2025-09` downloads an XLSX.

11) **Tests**

  pytest -q

Expected: all tests pass; export test asserts `Content-Disposition` includes `.xlsx`.

## Validation and Acceptance

**User-visible acceptance** (manual):

1. Start app; open `/`. Sidebar shows: Editor, Employees, Calendar, Shift Types, Reports, Settings.
2. Go to **Editor**, choose month `YYYY-MM`, press **Generate**. Grid fills with shifts; cells colored per legend.
3. Select a cell, change shift via dropdown; select multiple with Ctrl and perform **phase shift +1**; press **Apply Draft** then **Commit**. Grid reflects changes after reload.
4. Export **XLSX** and open; structure and styling match existing engine’s report.
5. Add a new employee and a vacation range; regenerate; schedule respects calendar and vacations.
6. Change a color in **Shift Types**; the grid updates classes/styles accordingly.
7. View **Reports** for the month (hours per employee). Export CSV; open and verify numbers.

**Automated acceptance**: tests described in Concrete Steps must pass; add at least one pre/post assertion that fails before adapter is wired and passes after.

## Idempotence and Recovery

- Migrations are idempotent; safe to re-run on each boot.
- Seeding is guarded: only insert if tables are empty.
- `POST /api/schedule/generate` upserts within a transaction; safe to retry.
- `draft_edits` → `commit` is atomic; in case of failure, roll back and keep draft intact.
- JSON config writes use temp file + atomic rename to prevent truncation.
- Backups: recommend copying the SQLite DB file before running destructive experiments.

## Artifacts and Notes

Keep artifacts minimal and focused on proof:

- Short terminal transcripts for `/healthz`, `generate`, and `export`.
- One small JSON example of `shift_types.json`:

  {
    "DA": {"label":"Day A","css_class":"DA","bg_color":"#F5F5F5","text_color":"#111"},
    "NB": {"label":"Night B","css_class":"NB","bg_color":"#CCE5FF","text_color":"#111"},
    "OFF":{"label":"Off","css_class":"OFF","bg_color":"#EEE","text_color":"#666"}
  }

- Example draft edit payload:

  {"edits":[{"emp_id":1,"day":5,"op":"set","new_value":"OFF"},{"emp_id":1,"day":6,"op":"shift_phase","+":1}]}

## Interfaces and Dependencies

**Python deps (requirements.txt):** `flask`, `python-dateutil`, `openpyxl`, `pytest`.

**Adapter contracts:**

- `services/generator_adapter.py`:

  def generate_schedule(month_ym: str, *, employees, calendar, settings, shift_types) -> dict: ...

  def export_xlsx(month_ym: str) -> io.BytesIO: ...

- `services/schedule_service.py`:

  def get_matrix(month_ym: str) -> dict: ...
  def apply_draft(month_ym: str, edits: list[dict]) -> int: ...
  def commit_draft(month_ym: str) -> int: ...

- `dao/*_dao.py`: Each DAO exposes typed methods with explicit SQL; no ORM.

**HTTP endpoints:**  
- Pages: `/`, `/editor`, `/employees`, `/calendar`, `/shifts`, `/reports`, `/settings`.  
- API:  
- `/api/schedule`, `/api/schedule/generate`, `/api/schedule/draft`, `/api/schedule/commit`, `/api/export/xlsx`
- `/api/employees` (CRUD), `/api/employees/import`
- `/api/calendar`, `/api/vacations`, `/api/calendar/import`
- `/api/shift-types` (GET/POST)
- `/api/settings` (GET/POST)
- `/api/reports/<name>`

**Edge rules baked into adapter:**
- Use the **previous calendar month** for generator context; never `prev_tail_by_emp`.
- Cell record: `value` (shift key), `office` (e.g., NA/NB), `meta` (styling tokens).
- Phase shift is a pure transformation on the selected cells, not a global re-run.

## Milestones

**M1 – Boot & Read-only Editor (2–4 commits)**  
App boots, migrations apply, `/editor` renders grid via `GET /api/schedule`. Adapter stub returns canned data; XLSX export returns trivial file. Proof: `/healthz` OK, `/editor` shows skeleton grid.

**M2 – Generator & Export (3–6 commits)**  
Wire `generate_schedule`, persist to `schedule_cells`, real XLSX export. Proof: POST generate populates DB; export opens in Excel.

**M3 – Editing & Draft (4–8 commits)**  
Implement draft/commit flow, multi-select + phase shift in UI. Proof: edits visible after commit; draft count increments.

**M4 – Entities & Config (4–8 commits)**  
Employees CRUD + import; Calendar + vacations; Shift Types & Settings editors. Proof: changes reflect in generation and UI styling.

**M5 – Reports & Tests (3–6 commits)**  
Add basic reports, CSV export, and minimal pytest suite. Proof: tests pass; CSV columns correct.
