"""Blueprint with the read-only editor view."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from ...services import generator_adapter, schedule_service
from ...dao import schedule_dao

bp = Blueprint("editor", __name__)


@bp.route("/editor")
def editor_index():
    months = schedule_service.available_months()
    month_query = request.args.get("month")
    error: str | None = None

    if month_query:
        try:
            selected_month = schedule_service.parse_month(month_query)
        except schedule_service.InvalidMonthFormatError as exc:
            error = str(exc)
            selected_month = months[-1] if months else None
    else:
        selected_month = months[-1] if months else None

    if selected_month and selected_month not in months:
        error = f"Месяц {selected_month} отсутствует в базе."
        selected_month = months[-1] if months else None

    month_view = schedule_service.build_month_view(selected_month) if selected_month else None

    return render_template(
        "editor/index.html",
        months=months,
        selected_month=selected_month,
        month_view=month_view,
        error_message=error,
    )


@bp.post("/api/schedule/generate")
def generate_schedule():
    payload = request.get_json(silent=True) or {}
    month_value = payload.get("month") or request.args.get("month")
    if not month_value:
        return jsonify({"error": "Не указан месяц"}), 400

    try:
        month = schedule_service.parse_month(month_value)
    except schedule_service.InvalidMonthFormatError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        schedule_service.ensure_month_available(month)
    except schedule_dao.MonthNotFoundError:
        return jsonify({"error": f"Месяц {month} отсутствует в базе"}), 404

    try:
        stats = generator_adapter.generate_and_store(month)
    except generator_adapter.GenerationError as exc:
        return jsonify({"error": str(exc)}), 400

    return (
        jsonify(
            {
                "status": "ok",
                "month": stats.ym,
                "employees": stats.employees,
                "days": stats.days,
                "cells": stats.cells,
            }
        ),
        200,
    )
