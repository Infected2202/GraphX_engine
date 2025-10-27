from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, jsonify, render_template, request

from services import reports_service

bp = Blueprint("reports", __name__)


@bp.route("/reports")
def reports_page():
    month = request.args.get("month") or datetime.utcnow().strftime("%Y-%m")
    report = reports_service.hours_report(month)
    return render_template("reports/index.html", report=report, month=month)


@bp.route("/api/reports/hours")
def hours_api():
    month = request.args.get("month") or datetime.utcnow().strftime("%Y-%m")
    return jsonify(reports_service.hours_report(month))


@bp.route("/api/reports/hours.csv")
def hours_csv():
    month = request.args.get("month") or datetime.utcnow().strftime("%Y-%m")
    buffer, filename = reports_service.export_hours_csv(month)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
