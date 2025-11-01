PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    fio TEXT NOT NULL,
    key TEXT NOT NULL UNIQUE,
    office TEXT,
    attrs_json TEXT DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS months (
    id INTEGER PRIMARY KEY,
    ym TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS schedule_cells (
    id INTEGER PRIMARY KEY,
    month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    emp_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    value TEXT,
    office TEXT,
    meta_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_schedule_cells_month_emp_day
    ON schedule_cells(month_id, emp_id, day);

CREATE TABLE IF NOT EXISTS draft_edits (
    id INTEGER PRIMARY KEY,
    month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    emp_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    new_value TEXT,
    new_office TEXT,
    op TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_days (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL UNIQUE,
    day_type TEXT NOT NULL,
    norm_minutes INTEGER
);

CREATE TABLE IF NOT EXISTS vacations (
    id INTEGER PRIMARY KEY,
    emp_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY,
    payload_json TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0001_init');
