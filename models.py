"""Database models for A Bright Children's School result portal.

Matches the original 8-subject Google Sheets export:
Roll number, Student's name, Father's Name, Mother's Name, DOB,
Science, Hindi, English, Sanskrit, Math, SST, Computer, GK, Total.

Class is inferred from the confirmed roll-number series:
6xx -> Class 6, 7xx -> Class 7, 8xx -> Class 8.
"""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, UniqueConstraint

from extensions import db


# Subject field names match the original sheet's eight subject columns.
SUBJECT_FIELDS = (
    "science",
    "hindi",
    "english",
    "sanskrit",
    "math",
    "sst",
    "computer",
    "gk",
)

SUBJECT_LABELS = {
    "science": "Science",
    "hindi": "Hindi",
    "english": "English",
    "sanskrit": "Sanskrit",
    "math": "Math",
    "sst": "SST",
    "computer": "Computer",
    "gk": "GK",
}

MAX_MARKS_PER_SUBJECT = 50
MAX_TOTAL_MARKS = MAX_MARKS_PER_SUBJECT * len(SUBJECT_FIELDS)


def infer_class_from_roll_number(roll_number: str) -> str:
    """Return the class name using the school's confirmed roll series.

    601-series -> Class 6; 701-series -> Class 7; 801-series -> Class 8.
    The roll number is kept as text so leading zeroes are not lost.
    """
    roll = str(roll_number).strip()
    if not roll or not roll.isdigit():
        raise ValueError("Roll number must contain digits only.")

    class_digit = roll[0]
    if class_digit not in {"6", "7", "8"}:
        raise ValueError(
            "Roll number must start with 6, 7, or 8 for Class 6, 7, or 8."
        )

    return f"Class {class_digit}"


class Student(db.Model):
    """One student profile from the original sheet's identity columns."""

    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(20), nullable=False, unique=True, index=True)
    class_name = db.Column(db.String(20), nullable=False, index=True)
    student_name = db.Column(db.String(120), nullable=False)
    father_name = db.Column(db.String(120), nullable=True)
    mother_name = db.Column(db.String(120), nullable=True)
    dob = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_results = db.relationship(
        "ExamResult",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def __repr__(self) -> str:
        return f"<Student roll={self.roll_number!r} name={self.student_name!r}>"


class ExamResult(db.Model):
    """One student's marks for one named examination and academic year."""

    __tablename__ = "exam_results"

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "academic_year",
            "exam_name",
            name="uq_result_student_year_exam",
        ),
        CheckConstraint(
            "sheet_total IS NULL OR (sheet_total >= 0 AND sheet_total <= 400)",
            name="ck_result_sheet_total_0_400",
        ),
        *(
            CheckConstraint(
                f"{field} IS NULL OR ({field} >= 0 AND {field} <= 50)",
                name=f"ck_result_{field}_0_50",
            )
            for field in SUBJECT_FIELDS
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    academic_year = db.Column(db.String(20), nullable=False)
    exam_name = db.Column(db.String(80), nullable=False)

    # NA or blank marks will be stored as None, never changed to zero.
    science = db.Column(db.Float, nullable=True)
    hindi = db.Column(db.Float, nullable=True)
    english = db.Column(db.Float, nullable=True)
    sanskrit = db.Column(db.Float, nullable=True)
    math = db.Column(db.Float, nullable=True)
    sst = db.Column(db.Float, nullable=True)
    computer = db.Column(db.Float, nullable=True)
    gk = db.Column(db.Float, nullable=True)

    # Keep the Total value supplied in the original sheet for audit only.
    # The website should display calculated_total, not this imported value.
    sheet_total = db.Column(db.Float, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    student = db.relationship("Student", back_populates="exam_results")

    @property
    def marks_complete(self) -> bool:
        return all(getattr(self, field) is not None for field in SUBJECT_FIELDS)

    @property
    def pending_subjects(self) -> list[str]:
        return [
            SUBJECT_LABELS[field]
            for field in SUBJECT_FIELDS
            if getattr(self, field) is None
        ]

    @property
    def calculated_total(self) -> float | None:
        if not self.marks_complete:
            return None
        return round(sum(float(getattr(self, field)) for field in SUBJECT_FIELDS), 2)

    @property
    def maximum_marks(self) -> int:
        return MAX_TOTAL_MARKS

    @property
    def percentage(self) -> float | None:
        total = self.calculated_total
        if total is None:
            return None
        return round((total / MAX_TOTAL_MARKS) * 100, 2)

    @property
    def result_status(self) -> str:
        return "COMPLETE" if self.marks_complete else "PENDING"

    @property
    def sheet_total_matches(self) -> bool | None:
        """Compare a supplied sheet total with calculated total when both exist."""
        total = self.calculated_total
        if self.sheet_total is None or total is None:
            return None
        return round(float(self.sheet_total), 2) == total

    def __repr__(self) -> str:
        return (
            f"<ExamResult student_id={self.student_id} "
            f"year={self.academic_year!r} exam={self.exam_name!r}>"
        )
class AdminUser(db.Model):
    """Secure administrator accounts."""

    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.active

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


# Append this model to the bottom of your existing models.py.
# Do not replace the existing Student, ExamResult, or AdminUser models.

class StudentAccess(db.Model):
    """Hashed individual access code for a student's result portal."""

    __tablename__ = "student_access"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    access_code_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    issued_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student", backref=db.backref("result_access", uselist=False))
