from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from dao import shift_types_dao

bp = Blueprint("shifts", __name__)


@bp.route("/shifts")
def shifts_page():
    return render_template("shifts/index.html", shift_types=shift_types_dao.get_shift_types())


@bp.route("/api/shift-types", methods=["GET"])
def list_shift_types():
    return jsonify({"shift_types": shift_types_dao.get_shift_types()})


@bp.route("/api/shift-types", methods=["POST"])
def save_shift_types():
    payload = request.get_json(force=True)
    shift_types_dao.save_shift_types(payload)
    return jsonify({"ok": True})
