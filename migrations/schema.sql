PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    fio TEXT NOT NULL,
    emp_key TEXT,
    office TEXT,
    attrs_json TEXT DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS months (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ym TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS schedule_cells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    emp_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    value TEXT NOT NULL,
    office TEXT,
    meta_json TEXT DEFAULT '{}',
    UNIQUE(month_id, emp_id, day)
);

CREATE TABLE IF NOT EXISTS draft_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    emp_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    new_value TEXT,
    new_office TEXT,
    op TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    meta_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS calendar_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    day_type TEXT NOT NULL,
    norm_minutes INTEGER
);

CREATE TABLE IF NOT EXISTS vacations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(month_id, name)
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shift_types (
    key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_schedule_emp_month_day
    ON schedule_cells (month_id, emp_id, day);

CREATE INDEX IF NOT EXISTS idx_draft_edits_month
    ON draft_edits (month_id);

CREATE INDEX IF NOT EXISTS idx_calendar_days_type
    ON calendar_days (day_type);

CREATE INDEX IF NOT EXISTS idx_reports_month
    ON reports (month_id);
