from __future__ import annotations

import math
from datetime import datetime
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash
from sqlalchemy import or_

from config import Config
from extensions import db
from models import (
    AdminUser,
    ExamResult,
    Student,
    SUBJECT_FIELDS,
    SUBJECT_LABELS,
    MAX_MARKS_PER_SUBJECT,
    MAX_TOTAL_MARKS,
    infer_class_from_roll_number,
)

ACADEMIC_YEAR = "2026-27"
EXAM_NAME = "Middle Result"

app = Flask(__name__)
app.config.from_object(Config)
app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
app.config.setdefault("PERMANENT_SESSION_LIFETIME", 60 * 60 * 8)
csrf = CSRFProtect(app)
db.init_app(app)

# create_all only creates missing tables. It does not drop or reset existing data.
with app.app_context():
    db.create_all()


def current_admin():
    admin_id = session.get("admin_id")
    if not admin_id:
        return None
    return AdminUser.query.filter_by(id=admin_id, active=True).first()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_admin() is None:
            session.pop("admin_id", None)
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.after_request
def security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def get_current_result(student):
    return ExamResult.query.filter_by(
        student_id=student.id,
        academic_year=ACADEMIC_YEAR,
        exam_name=EXAM_NAME,
    ).first()


@app.route("/", methods=["GET", "POST"])
def home():
    student = None
    result = None
    error = None
    subject_rows = []
    roll_number = ""
    if request.method == "POST":
        roll_number = request.form.get("roll_number", "").strip()
        session.pop("verified_result_student_id", None)
        if not roll_number or not roll_number.isdigit() or len(roll_number) > 20:
            error = "Please enter a valid school roll number."
        else:
            student = Student.query.filter_by(roll_number=roll_number, is_active=True).first()
            if student:
                result = get_current_result(student)
            if student is None or result is None:
                student = None
                result = None
                error = "No result found for this roll number. Please check the number or contact the school office."
            else:
                # Roll number is the sole lookup credential in this simplified parent flow.
                # Anyone who knows a roll number can view that student's result.
                session["verified_result_student_id"] = student.id
                for field in SUBJECT_FIELDS:
                    mark = getattr(result, field)
                    subject_rows.append({
                        "label": SUBJECT_LABELS[field],
                        "mark": None if mark is None else f"{mark:g}",
                    })

    return render_template(
        "portal.html",
        school_name="A Bright Children's School, Lahar",
        academic_year=ACADEMIC_YEAR,
        roll_number=roll_number,
        student=student,
        result=result,
        error=error,
        subject_rows=subject_rows,
        maximum=MAX_TOTAL_MARKS,
        total_display=(f"{result.calculated_total:g}" if result and result.calculated_total is not None else None),
        percentage_display=(f"{result.percentage:.2f}" if result and result.percentage is not None else None),
        pending_count=(len(result.pending_subjects) if result else 0),
    )

@app.get("/result/print")
def print_result():
    student_id = session.get("verified_result_student_id")
    if not student_id:
        return redirect(url_for("home"))
    student = db.session.get(Student, student_id)
    if student is None or not student.is_active:
        session.pop("verified_result_student_id", None)
        return redirect(url_for("home"))
    result = get_current_result(student)
    if result is None:
        return redirect(url_for("home"))
    subject_rows = [
        {"label": SUBJECT_LABELS[field], "mark": getattr(result, field)}
        for field in SUBJECT_FIELDS
    ]
    return render_template(
        "result_print.html", student=student, result=result,
        subject_rows=subject_rows, academic_year=ACADEMIC_YEAR,
        total_display=(f"{result.calculated_total:g}" if result.calculated_total is not None else None),
        percentage_display=(f"{result.percentage:.2f}" if result.percentage is not None else None),
        maximum=MAX_TOTAL_MARKS,
    )


@app.get("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_admin():
        return redirect(url_for("admin_dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = AdminUser.query.filter_by(username=username, active=True).first()
        if admin and check_password_hash(admin.password_hash, password):
            session.clear()
            session["admin_id"] = admin.id
            session.permanent = True
            destination = request.args.get("next", "")
            if not destination.startswith("/admin"):
                destination = url_for("admin_dashboard")
            return redirect(destination)
        error = "Username or password is incorrect."
    return render_template("admin_login.html", error=error)


@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/admin")
@admin_required
def admin_dashboard():
    students = Student.query.filter_by(is_active=True).all()
    results = ExamResult.query.filter_by(academic_year=ACADEMIC_YEAR, exam_name=EXAM_NAME).all()
    return render_template(
        "admin_dashboard.html",
        admin=current_admin(),
        total_students=len(students),
        class_counts={c: sum(s.class_name == c for s in students) for c in ("Class 6", "Class 7", "Class 8")},
        pending_count=sum(not r.marks_complete for r in results),
        mismatch_count=sum(r.sheet_total_matches is False for r in results),
    )


@app.get("/admin/students")
@admin_required
def admin_students():
    query = request.args.get("q", "").strip()
    students_query = Student.query
    if query:
        like = f"%{query}%"
        students_query = students_query.filter(
            or_(Student.roll_number.ilike(like), Student.student_name.ilike(like))
        )
    students = students_query.order_by(Student.class_name, Student.roll_number).all()
    return render_template("admin_students.html", students=students, query=query)


@app.route("/admin/student/<int:student_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_student(student_id):
    student = db.session.get(Student, student_id)
    if student is None:
        abort(404)
    result = get_current_result(student)
    errors = []
    form_values = None
    form_marks = {
        field: (getattr(result, field) if result and getattr(result, field) is not None else "")
        for field in SUBJECT_FIELDS
    }

    if request.method == "POST":
        form_values = request.form
        form_marks = {field: request.form.get(field, "") for field in SUBJECT_FIELDS}
        student_name = request.form.get("student_name", "").strip()
        father_name = request.form.get("father_name", "").strip() or None
        mother_name = request.form.get("mother_name", "").strip() or None
        dob_raw = request.form.get("dob", "").strip()
        if not student_name:
            errors.append("Student name is required.")
        dob_value = None
        if dob_raw:
            try:
                dob_value = datetime.strptime(dob_raw, "%Y-%m-%d").date()
            except ValueError:
                errors.append("Date of birth must be a valid date.")

        marks = {}
        for field in SUBJECT_FIELDS:
            raw = request.form.get(field, "").strip()
            if raw == "":
                marks[field] = None
                continue
            try:
                mark = float(raw)
                if not math.isfinite(mark) or not 0 <= mark <= MAX_MARKS_PER_SUBJECT:
                    raise ValueError
                marks[field] = mark
            except ValueError:
                errors.append(f"{SUBJECT_LABELS[field]} must be blank or between 0 and 50.")

        if not errors:
            student.student_name = student_name
            student.father_name = father_name
            student.mother_name = mother_name
            student.dob = dob_value
            if result is None:
                result = ExamResult(
                    student_id=student.id,
                    academic_year=ACADEMIC_YEAR,
                    exam_name=EXAM_NAME,
                )
                db.session.add(result)
            for field, mark in marks.items():
                setattr(result, field, mark)
            # sheet_total is deliberately not changed by this editor.
            db.session.commit()
            flash("Student and subject marks saved successfully.", "success")
            return redirect(url_for("admin_edit_student", student_id=student.id))

    return render_template(
        "admin_student_edit.html",
        student=student,
        result=result,
        errors=errors,
        form_values=form_values,
        form_marks=form_marks,
        new_access_code=None,
        subject_fields=SUBJECT_FIELDS,
        subject_labels=SUBJECT_LABELS,
        admin=current_admin(),
    )


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", message="The requested page could not be found."), 404


@app.errorhandler(500)
def server_error(_error):
    db.session.rollback()
    return render_template("error.html", message="Something went wrong. Please contact the school administrator."), 500


if __name__ == "__main__":
    print("ABC SCHOOL DIGITAL CAMPUS")
    print("Local portal: http://127.0.0.1:5000")
    print("Admin login: http://127.0.0.1:5000/admin/login")
    app.run(host="127.0.0.1", port=5000, debug=False)
