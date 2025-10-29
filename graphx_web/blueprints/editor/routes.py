"""Blueprint with the read-only editor view."""

from __future__ import annotations

from flask import Blueprint, render_template, request

from ...services import schedule_service

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
