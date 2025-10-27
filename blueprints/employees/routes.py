from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from dao import employees_dao

bp = Blueprint("employees", __name__)


@bp.route("/employees")
def employees_page():
    return render_template("employees/index.html", employees=employees_dao.list_employees(include_inactive=True))


@bp.route("/api/employees", methods=["GET"])
def list_employees():
    return jsonify({"employees": employees_dao.list_employees(include_inactive=True)})


@bp.route("/api/employees", methods=["POST"])
def create_employee():
    payload = request.get_json(force=True)
    emp_id = employees_dao.create_employee(payload)
    return jsonify({"id": emp_id}), 201


@bp.route("/api/employees/<emp_id>", methods=["PUT"])
def update_employee(emp_id: str):
    payload = request.get_json(force=True)
    updated = employees_dao.update_employee(emp_id, payload)
    return jsonify({"updated": updated})


@bp.route("/api/employees/<emp_id>", methods=["DELETE"])
def delete_employee(emp_id: str):
    deleted = employees_dao.delete_employee(emp_id)
    return jsonify({"deleted": deleted})


@bp.route("/api/employees/import", methods=["POST"])
def import_employees():
    payload = request.get_json(force=True)
    employees = payload.get("employees", [])
    created = []
    for emp in employees:
        employees_dao.create_employee(emp)
        created.append(emp.get("id"))
    return jsonify({"created": created})
