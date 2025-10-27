from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from services import schedule_service
from services.generator_adapter import export_xlsx, generate_schedule

bp = Blueprint("editor", __name__)


def _resolve_month() -> str:
    month = request.args.get("month") or request.json.get("month") if request.is_json else None
    if month:
        return month
    today = datetime.utcnow().date()
    return f"{today.year:04d}-{today.month:02d}"


@bp.route("/editor")
def editor_page():
    month = request.args.get("month") or _resolve_month()
    matrix = schedule_service.get_matrix(month)
    return render_template("editor/index.html", data=matrix)


@bp.route("/api/schedule")
def get_schedule():
    month = request.args.get("month") or _resolve_month()
    return jsonify(schedule_service.get_matrix(month))


@bp.route("/api/schedule/generate", methods=["POST"])
def generate_endpoint():
    payload = request.get_json(silent=True) or {}
    month = payload.get("month") or request.args.get("month") or _resolve_month()
    result = generate_schedule(month)
    return jsonify({"ok": True, "summary": result})


@bp.route("/api/schedule/draft", methods=["POST"])
def draft_endpoint():
    payload = request.get_json(force=True)
    month = payload.get("month") or _resolve_month()
    edits = payload.get("edits", [])
    count = schedule_service.apply_draft(month, edits)
    return jsonify({"count": count})


@bp.route("/api/schedule/commit", methods=["POST"])
def commit_endpoint():
    payload = request.get_json(force=True)
    month = payload.get("month") or _resolve_month()
    applied = schedule_service.commit_draft(month)
    return jsonify({"applied": applied})


@bp.route("/api/export/xlsx")
def export_endpoint():
    month = request.args.get("month") or _resolve_month()
    stream, filename = export_xlsx(month)
    return (stream.getvalue(), 200, {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": f"attachment; filename={filename}",
    })
