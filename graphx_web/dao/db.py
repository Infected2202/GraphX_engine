"""SQLite helpers for the web application."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

import click
from flask import Flask, current_app, g

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"
SCHEMA_VERSION = "0001_init"


def get_db() -> sqlite3.Connection:
    """Return a connection for the current request context."""
    if "db" not in g:
        database_path = current_app.config["DATABASE"]
        g.db = sqlite3.connect(database_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db  # type: ignore[return-value]


def close_db(_: object | None = None) -> None:
    """Close the connection stored in the application context."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app: Flask) -> None:
    """Attach teardown handlers and CLI commands to the app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


def ensure_schema(app: Flask) -> None:
    """Ensure the database schema and seed data are present."""
    initialize_database(app, drop_existing=False)


def initialize_database(app: Flask, *, drop_existing: bool) -> None:
    database_path = Path(app.config["DATABASE"])
    if drop_existing and database_path.exists():
        database_path.unlink()

    with app.app_context():
        db = get_db()
        try:
            if not _has_version(db, SCHEMA_VERSION):
                _apply_scripts(db, [MIGRATIONS_DIR / "0001_init.sql", SEEDS_DIR / "seed.sql"])
                db.commit()
        finally:
            close_db(None)


def _apply_scripts(db: sqlite3.Connection, scripts: Iterable[Path]) -> None:
    for script in scripts:
        sql = script.read_text(encoding="utf-8")
        db.executescript(sql)


def _has_version(db: sqlite3.Connection, version: str) -> bool:
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    )
    if cursor.fetchone() is None:
        return False
    version_cursor = db.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,))
    return version_cursor.fetchone() is not None


@click.command("init-db")
@click.option("--force", is_flag=True, help="Recreate the database from scratch.")
def init_db_command(force: bool) -> None:
    """Initialize the database using the bundled migrations and seeds."""
    app = current_app._get_current_object()  # type: ignore[attr-defined]
    initialize_database(app, drop_existing=force)
    click.echo("Database initialized.")
