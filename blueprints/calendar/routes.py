from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from dao import calendar_dao

bp = Blueprint("calendar", __name__)


@bp.route("/calendar")
def calendar_page():
    days = calendar_dao.list_calendar_days()
    vacations = calendar_dao.list_vacations()
    return render_template("calendar/index.html", days=days, vacations=vacations)


@bp.route("/api/calendar", methods=["GET"])
def list_calendar_days():
    return jsonify({"days": calendar_dao.list_calendar_days()})


@bp.route("/api/calendar", methods=["POST"])
def upsert_calendar_day():
    payload = request.get_json(force=True)
    calendar_dao.upsert_calendar_day(payload["date"], payload["day_type"], payload.get("norm_minutes"))
    return jsonify({"ok": True})


@bp.route("/api/calendar/<date_str>", methods=["DELETE"])
def delete_calendar_day(date_str: str):
    deleted = calendar_dao.delete_calendar_day(date_str)
    return jsonify({"deleted": deleted})


@bp.route("/api/vacations", methods=["GET"])
def list_vacations():
    emp_id = request.args.get("emp_id")
    return jsonify({"vacations": calendar_dao.list_vacations(emp_id)})


@bp.route("/api/vacations", methods=["POST"])
def create_vacation():
    payload = request.get_json(force=True)
    vacation_id = calendar_dao.add_vacation(payload)
    return jsonify({"id": vacation_id}), 201


@bp.route("/api/vacations/<int:vacation_id>", methods=["DELETE"])
def delete_vacation(vacation_id: int):
    deleted = calendar_dao.delete_vacation(vacation_id)
    return jsonify({"deleted": deleted})
