from __future__ import annotations

import math
import re
import secrets
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, inspect, or_, text
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from extensions import db
from models import (
    ALL_CLASSES,
    ALL_SUBJECT_FIELDS,
    AdminUser,
    ExamResult,
    MAX_ADMIN_ACCOUNTS,
    MAX_MARKS_PER_SUBJECT,
    PROJECT_NAME,
    RollRecoveryRequest,
    SCHOOL_HEADING,
    SUBJECT_FIELDS,
    SUBJECT_LABELS,
    Student,
    get_exam_title_for_class,
    get_subjects_for_class,
    infer_class_from_roll_number,
    is_valid_roll_number,
    normalize_roll_number,
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


def ensure_schema_compatibility() -> None:
    """Safely create missing tables and add new nullable columns without dropping existing data."""
    db.create_all()
    inspector = inspect(db.engine)
    if "exam_results" in inspector.get_table_names():
        existing_cols = {col["name"] for col in inspector.get_columns("exam_results")}
        with db.engine.begin() as conn:
            if "evs_moral" not in existing_cols:
                conn.execute(text("ALTER TABLE exam_results ADD COLUMN evs_moral FLOAT"))
            if "sheet_status" not in existing_cols:
                conn.execute(text("ALTER TABLE exam_results ADD COLUMN sheet_status VARCHAR(30)"))


with app.app_context():
    ensure_schema_compatibility()


@app.context_processor
def inject_branding():
    return {
        "school_name": SCHOOL_HEADING,
        "project_name": PROJECT_NAME,
        "academic_year": ACADEMIC_YEAR,
        "all_classes": ALL_CLASSES,
        "max_admin_accounts": MAX_ADMIN_ACCOUNTS,
    }


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


def get_current_result(student: Student):
    result = ExamResult.query.filter_by(
        student_id=student.id,
        academic_year=ACADEMIC_YEAR,
        exam_name=EXAM_NAME,
    ).first()
    if result is None:
        result = (
            ExamResult.query.filter_by(student_id=student.id, academic_year=ACADEMIC_YEAR)
            .order_by(ExamResult.id.desc())
            .first()
        )
    return result


def build_subject_rows(student: Student, result: ExamResult) -> list[dict]:
    fields = get_subjects_for_class(student.class_name)
    rows = []
    for field in fields:
        mark = getattr(result, field)
        rows.append(
            {
                "field": field,
                "label": SUBJECT_LABELS[field],
                "max_marks": MAX_MARKS_PER_SUBJECT,
                "mark": None if mark is None else f"{mark:g}",
                "raw_mark": mark,
            }
        )
    return rows


@app.route("/", methods=["GET", "POST"])
def home():
    student = None
    result = None
    error = None
    subject_rows = []
    roll_number = request.args.get("roll", "").strip()

    if request.method == "POST":
        roll_number = normalize_roll_number(request.form.get("roll_number", ""))
        session.pop("verified_result_student_id", None)
        if not roll_number or not is_valid_roll_number(roll_number):
            error = (
                "Please enter a valid school roll number "
                "(for example: N01 for Nursery, L01 for LKG, U01 for UKG, or 101 to 841 for Class 1–8)."
            )
        else:
            student = Student.query.filter(
                func.upper(Student.roll_number) == roll_number,
                Student.is_active.is_(True),
            ).first()
            if student:
                result = get_current_result(student)
            if student is None or result is None:
                student = None
                result = None
                error = (
                    "No result found for this roll number. Please check the number, "
                    "use 'Forgot Roll Number?' below, or contact the school office."
                )
            else:
                session["verified_result_student_id"] = student.id
                subject_rows = build_subject_rows(student, result)

    maximum = result.maximum_marks if result else 400
    exam_title = get_exam_title_for_class(student.class_name) if student else "Examination Result"

    return render_template(
        "portal.html",
        roll_number=roll_number,
        student=student,
        result=result,
        error=error,
        subject_rows=subject_rows,
        maximum=maximum,
        exam_title=exam_title,
        subject_count=(result.subject_count if result else 0),
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
    subject_rows = build_subject_rows(student, result)
    return render_template(
        "result_print.html",
        student=student,
        result=result,
        subject_rows=subject_rows,
        exam_title=get_exam_title_for_class(student.class_name),
        subject_count=result.subject_count,
        total_display=(f"{result.calculated_total:g}" if result.calculated_total is not None else None),
        percentage_display=(f"{result.percentage:.2f}" if result.percentage is not None else None),
        maximum=result.maximum_marks,
    )


def generate_recovery_reference() -> str:
    """Create a short, easy-to-write reference code for parents (e.g. REQ-482910)."""
    for _ in range(20):
        code = f"REQ-{secrets.randbelow(900000) + 100000}"
        if not RollRecoveryRequest.query.filter_by(reference_code=code).first():
            return code
    return f"REQ-{int(datetime.now(timezone.utc).timestamp())}"


def find_best_matching_student(
    class_name: str,
    student_name: str,
    father_name: str | None,
    mother_name: str | None,
    dob_value,
) -> Student | None:
    """Privately suggest the closest student record for admin review only (never exposed publicly)."""
    candidates = Student.query.filter_by(class_name=class_name, is_active=True).all()
    target_name = re.sub(r"\s+", " ", student_name.strip().lower())
    best = None
    best_score = 0
    for cand in candidates:
        cand_name = re.sub(r"\s+", " ", (cand.student_name or "").strip().lower())
        score = 0
        if cand_name == target_name:
            score += 5
        elif target_name and (target_name in cand_name or cand_name in target_name):
            score += 3
        if father_name and cand.father_name:
            fn_in = father_name.strip().lower()
            fn_db = cand.father_name.strip().lower()
            if fn_in == fn_db or fn_in in fn_db or fn_db in fn_in:
                score += 3
        if mother_name and cand.mother_name:
            mn_in = mother_name.strip().lower()
            mn_db = cand.mother_name.strip().lower()
            if mn_in == mn_db or mn_in in mn_db or mn_db in mn_in:
                score += 2
        if dob_value and cand.dob and dob_value == cand.dob:
            score += 3
        if score > best_score:
            best_score = score
            best = cand
    return best if best_score >= 3 else None


@app.route("/forgot-roll", methods=["GET", "POST"])
def forgot_roll_number():
    """Simple, privacy-preserving Forgot Roll Number page for parents/guardians."""
    submitted_request = None
    status_lookup_result = None
    status_error = None
    form_error = None
    active_tab = request.args.get("tab", "request")

    if request.method == "POST":
        action = request.form.get("action", "submit_request")
        if action == "check_status":
            active_tab = "status"
            ref_code = request.form.get("reference_code", "").strip().upper()
            mobile = re.sub(r"\D+", "", request.form.get("parent_mobile", ""))
            if not ref_code or not mobile:
                status_error = "Please enter both your Reference Code (e.g. REQ-123456) and mobile number."
            else:
                req_record = RollRecoveryRequest.query.filter_by(reference_code=ref_code).first()
                if req_record is None or re.sub(r"\D+", "", req_record.parent_mobile) != mobile:
                    status_error = (
                        "No matching request found. Please verify your Reference Code and mobile number."
                    )
                else:
                    status_lookup_result = req_record
        else:
            active_tab = "request"
            student_name = request.form.get("student_name", "").strip()
            class_name = request.form.get("class_name", "").strip()
            father_name = request.form.get("father_name", "").strip() or None
            mother_name = request.form.get("mother_name", "").strip() or None
            dob_raw = request.form.get("dob", "").strip()
            mobile_raw = re.sub(r"\D+", "", request.form.get("parent_mobile", ""))

            dob_value = None
            if dob_raw:
                try:
                    dob_value = datetime.strptime(dob_raw, "%Y-%m-%d").date()
                except ValueError:
                    form_error = "Please enter a valid Date of Birth."

            if not form_error:
                if not student_name or len(student_name) < 2:
                    form_error = "Please enter the student's full name."
                elif class_name not in ALL_CLASSES:
                    form_error = "Please select the student's class."
                elif not father_name and not mother_name and not dob_value:
                    form_error = (
                        "Please enter at least one school-verifiable detail "
                        "(Father's Name, Mother's Name, or Date of Birth)."
                    )
                elif len(mobile_raw) < 10 or len(mobile_raw) > 15:
                    form_error = "Please enter a valid 10-digit parent/guardian mobile number."

            if not form_error:
                matched = find_best_matching_student(
                    class_name=class_name,
                    student_name=student_name,
                    father_name=father_name,
                    mother_name=mother_name,
                    dob_value=dob_value,
                )
                ref_code = generate_recovery_reference()
                new_req = RollRecoveryRequest(
                    reference_code=ref_code,
                    student_name=student_name,
                    class_name=class_name,
                    father_name=father_name,
                    mother_name=mother_name,
                    dob=dob_value,
                    parent_mobile=mobile_raw,
                    status="PENDING",
                    matched_student_id=(matched.id if matched else None),
                )
                db.session.add(new_req)
                db.session.commit()
                submitted_request = new_req

    return render_template(
        "forgot_roll.html",
        active_tab=active_tab,
        submitted_request=submitted_request,
        status_lookup_result=status_lookup_result,
        status_error=status_error,
        form_error=form_error,
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
        error = "Username or password is incorrect, or the account is inactive."
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
    results = ExamResult.query.filter_by(academic_year=ACADEMIC_YEAR).all()
    class_counts = {c: sum(s.class_name == c for s in students) for c in ALL_CLASSES}
    pending_recovery_count = RollRecoveryRequest.query.filter_by(status="PENDING").count()
    admin_count = AdminUser.query.count()
    active_admin_count = AdminUser.query.filter_by(active=True).count()

    return render_template(
        "admin_dashboard.html",
        admin=current_admin(),
        total_students=len(students),
        class_counts=class_counts,
        pending_count=sum(not r.marks_complete for r in results),
        mismatch_count=sum(r.sheet_total_matches is False for r in results),
        pending_recovery_count=pending_recovery_count,
        admin_count=admin_count,
        active_admin_count=active_admin_count,
    )


def roll_sort_key(student: Student):
    """Order students naturally by class order (Nursery -> Class 8) and numeric roll suffix."""
    class_index = ALL_CLASSES.index(student.class_name) if student.class_name in ALL_CLASSES else 99
    digits = re.sub(r"\D+", "", student.roll_number or "")
    num = int(digits) if digits.isdigit() else 999999
    return (class_index, num, student.roll_number)


@app.get("/admin/students")
@admin_required
def admin_students():
    query = request.args.get("q", "").strip()
    class_filter = request.args.get("class_name", "").strip()
    status_filter = request.args.get("status", "").strip()

    students_query = Student.query.filter_by(is_active=True)
    if class_filter and class_filter in ALL_CLASSES:
        students_query = students_query.filter_by(class_name=class_filter)
    if query:
        like = f"%{query}%"
        students_query = students_query.filter(
            or_(
                Student.roll_number.ilike(like),
                Student.student_name.ilike(like),
                Student.father_name.ilike(like),
            )
        )
    students = sorted(students_query.all(), key=roll_sort_key)

    results_by_student = {
        r.student_id: r
        for r in ExamResult.query.filter_by(academic_year=ACADEMIC_YEAR).all()
    }

    if status_filter == "pending":
        students = [
            s for s in students
            if s.id not in results_by_student or not results_by_student[s.id].marks_complete
        ]
    elif status_filter == "complete":
        students = [
            s for s in students
            if s.id in results_by_student and results_by_student[s.id].marks_complete
        ]
    elif status_filter == "mismatch":
        students = [
            s for s in students
            if s.id in results_by_student and results_by_student[s.id].sheet_total_matches is False
        ]

    return render_template(
        "admin_students.html",
        admin=current_admin(),
        students=students,
        results_by_student=results_by_student,
        query=query,
        class_filter=class_filter,
        status_filter=status_filter,
    )


@app.route("/admin/student/<int:student_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_student(student_id):
    student = db.session.get(Student, student_id)
    if student is None:
        abort(404)
    result = get_current_result(student)
    errors = []
    form_values = None
    applicable_fields = get_subjects_for_class(student.class_name)
    form_marks = {
        field: (getattr(result, field) if result and getattr(result, field) is not None else "")
        for field in applicable_fields
    }

    if request.method == "POST":
        form_values = request.form
        form_marks = {field: request.form.get(field, "") for field in applicable_fields}
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
        for field in applicable_fields:
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
            flash("Student profile and subject marks saved successfully.", "success")
            return redirect(url_for("admin_edit_student", student_id=student.id))

    return render_template(
        "admin_student_edit.html",
        student=student,
        result=result,
        errors=errors,
        form_values=form_values,
        form_marks=form_marks,
        subject_fields=applicable_fields,
        subject_labels=SUBJECT_LABELS,
        admin=current_admin(),
    )


@app.route("/admin/admins", methods=["GET", "POST"])
@admin_required
def admin_manage_admins():
    """Manage up to 5 administrator accounts with lockout protection."""
    admin = current_admin()
    errors = []

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create":
            total_count = AdminUser.query.count()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")

            if total_count >= MAX_ADMIN_ACCOUNTS:
                errors.append(f"Admin account limit reached: maximum {MAX_ADMIN_ACCOUNTS} accounts allowed.")
            elif not username or len(username) > 80:
                errors.append("Username must contain 1 to 80 characters.")
            elif AdminUser.query.filter(func.lower(AdminUser.username) == username.lower()).first():
                errors.append("That username already exists. Duplicate usernames are not allowed.")
            elif len(password) < 12:
                errors.append("Password must be at least 12 characters long.")
            elif password != confirm:
                errors.append("Passwords do not match.")
            else:
                new_admin = AdminUser(
                    username=username,
                    password_hash=generate_password_hash(password),
                    active=True,
                )
                db.session.add(new_admin)
                db.session.commit()
                flash(f"Administrator account '{username}' created successfully.", "success")
                return redirect(url_for("admin_manage_admins"))

        elif action == "toggle_active":
            target_id = request.form.get("target_admin_id", type=int)
            target = db.session.get(AdminUser, target_id) if target_id else None
            if target is None:
                errors.append("Administrator account not found.")
            elif target.active:
                active_count = AdminUser.query.filter_by(active=True).count()
                if active_count <= 1:
                    errors.append("Cannot deactivate the last active administrator account.")
                elif target.id == admin.id:
                    errors.append(
                        "You cannot deactivate your own currently signed-in account. "
                        "Ask another active administrator if needed."
                    )
                else:
                    target.active = False
                    db.session.commit()
                    flash(f"Administrator '{target.username}' has been set to inactive.", "warning")
                    return redirect(url_for("admin_manage_admins"))
            else:
                target.active = True
                db.session.commit()
                flash(f"Administrator '{target.username}' is now active.", "success")
                return redirect(url_for("admin_manage_admins"))

    admins = AdminUser.query.order_by(AdminUser.id.asc()).all()
    active_count = sum(1 for a in admins if a.active)
    return render_template(
        "admin_users.html",
        admin=admin,
        admins=admins,
        active_count=active_count,
        max_admins=MAX_ADMIN_ACCOUNTS,
        errors=errors,
    )


@app.route("/admin/recovery", methods=["GET", "POST"])
@admin_required
def admin_recovery_requests():
    """Review and approve/reject parent Forgot Roll Number requests."""
    admin = current_admin()
    if request.method == "POST":
        req_id = request.form.get("request_id", type=int)
        action = request.form.get("action", "")
        resolved_roll = normalize_roll_number(request.form.get("resolved_roll_number", ""))
        admin_note = request.form.get("admin_note", "").strip() or None

        rec = db.session.get(RollRecoveryRequest, req_id) if req_id else None
        if rec is None:
            flash("Recovery request not found.", "warning")
            return redirect(url_for("admin_recovery_requests"))

        if action == "approve":
            student = Student.query.filter(
                func.upper(Student.roll_number) == resolved_roll,
                Student.is_active.is_(True),
            ).first()
            if student is None:
                flash(f"Roll number '{resolved_roll}' does not match any active student.", "warning")
            else:
                rec.status = "APPROVED"
                rec.resolved_roll_number = student.roll_number
                rec.matched_student_id = student.id
                rec.admin_note = admin_note
                rec.resolved_by_username = admin.username
                rec.resolved_at = datetime.now(timezone.utc)
                db.session.commit()
                flash(
                    f"Request {rec.reference_code} approved with Roll No. {student.roll_number} "
                    f"({student.student_name}).",
                    "success",
                )
        elif action == "reject":
            rec.status = "REJECTED"
            rec.resolved_roll_number = None
            rec.admin_note = admin_note or "Details could not be verified. Please contact the school office."
            rec.resolved_by_username = admin.username
            rec.resolved_at = datetime.now(timezone.utc)
            db.session.commit()
            flash(f"Request {rec.reference_code} marked as rejected.", "warning")

        return redirect(url_for("admin_recovery_requests"))

    status_filter = request.args.get("status", "").strip().upper()
    query = RollRecoveryRequest.query
    if status_filter in {"PENDING", "APPROVED", "REJECTED"}:
        query = query.filter_by(status=status_filter)
    requests_list = query.order_by(RollRecoveryRequest.created_at.desc()).all()

    return render_template(
        "admin_recovery.html",
        admin=admin,
        requests_list=requests_list,
        status_filter=status_filter,
    )


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", message="The requested page could not be found."), 404


@app.errorhandler(500)
def server_error(_error):
    db.session.rollback()
    return render_template("error.html", message="Something went wrong. Please contact the school administrator."), 500


if __name__ == "__main__":
    print(f"{SCHOOL_HEADING} — {PROJECT_NAME}")
    print("Local portal: http://127.0.0.1:5000")
    print("Admin login:  http://127.0.0.1:5000/admin/login")
    app.run(host="127.0.0.1", port=5000, debug=False)
