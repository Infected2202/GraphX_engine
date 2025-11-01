"""Application factory for the GraphX web interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, redirect, url_for
from flask.typing import ResponseReturnValue

from .dao import db as db_module
from .blueprints.editor.routes import bp as editor_bp


DEFAULT_CONFIG: dict[str, Any] = {
    "SECRET_KEY": "dev",
}


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_mapping(DEFAULT_CONFIG)

    if config:
        app.config.update(config)

    database_path = app.config.get(
        "DATABASE",
        Path(app.instance_path) / "graphx_web.sqlite",
    )
    if isinstance(database_path, Path):
        database_path = str(database_path)
    app.config["DATABASE"] = database_path

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db_module.init_app(app)
    db_module.ensure_schema(app)

    app.register_blueprint(editor_bp)

    @app.get("/")
    def index() -> ResponseReturnValue:
        return redirect(url_for("editor.editor_index"))

    @app.get("/healthz")
    def healthcheck() -> tuple[str, int]:
        return "OK", 200

    return app
