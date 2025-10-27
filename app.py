from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, redirect, url_for

from services import db as db_service


BLUEPRINTS = [
    ("blueprints.editor.routes", "bp"),
    ("blueprints.employees.routes", "bp"),
    ("blueprints.calendar.routes", "bp"),
    ("blueprints.shifts.routes", "bp"),
    ("blueprints.reports.routes", "bp"),
    ("blueprints.settings.routes", "bp"),
]


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "graphx.sqlite"),
        JSON_SORT_KEYS=False,
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    for import_path, attr in BLUEPRINTS:
        module = __import__(import_path, fromlist=[attr])
        blueprint = getattr(module, attr)
        app.register_blueprint(blueprint)

    app.add_url_rule("/", endpoint="root", view_func=lambda: redirect(url_for("editor.editor_page")))

    @app.route("/healthz")
    def healthcheck() -> tuple[str, int]:
        return "OK", 200

    app.teardown_appcontext(db_service.close_db)

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Initialize the SQLite schema and seed data."""
        db_service.initialize_schema()
        db_service.seed_database()
        print("Database initialized and seeded.")

    if app.config.get("AUTO_INIT_DB", True):
        with app.app_context():
            db_service.initialize_schema()
            db_service.seed_database()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
