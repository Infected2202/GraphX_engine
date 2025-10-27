from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from dao import settings_dao

bp = Blueprint("settings", __name__)


@bp.route("/settings")
def settings_page():
    return render_template("settings/index.html", settings=settings_dao.get_settings())


@bp.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(settings_dao.get_settings())


@bp.route("/api/settings", methods=["POST"])
def save_settings():
    payload = request.get_json(force=True)
    settings_dao.save_settings(payload)
    return jsonify({"ok": True})
