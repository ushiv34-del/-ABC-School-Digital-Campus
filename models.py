"""Database models for A Bright Children's School, Lahar (ABC School Digital Campus).

Supports Nursery to Class 8 with class-specific subject configurations while
preserving 100% backward compatibility with the original 112 Class 6-8 records:
- Pre-Primary (Nursery, LKG, UKG): English, Hindi, Math (3 subjects x 50 = 150)
- Primary (Class 1 to Class 5): Hindi, English, EVS/MORAL, Math, Computer, GK (6 subjects x 50 = 300)
- Middle (Class 6 to Class 8): Science, Hindi, English, Sanskrit, Math, SST, Computer, GK (8 subjects x 50 = 400)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, UniqueConstraint

from extensions import db


SCHOOL_HEADING = "A Bright Children's School, Lahar"
PROJECT_NAME = "ABC School Digital Campus"

ALL_CLASSES = (
    "Nursery",
    "LKG",
    "UKG",
    "Class 1",
    "Class 2",
    "Class 3",
    "Class 4",
    "Class 5",
    "Class 6",
    "Class 7",
    "Class 8",
)

PRE_PRIMARY_CLASSES = {"Nursery", "LKG", "UKG"}
PRIMARY_CLASSES = {"Class 1", "Class 2", "Class 3", "Class 4", "Class 5"}
MIDDLE_CLASSES = {"Class 6", "Class 7", "Class 8"}

# Original 8 subjects kept for backward compatibility
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

ALL_SUBJECT_FIELDS = (
    "science",
    "hindi",
    "english",
    "sanskrit",
    "evs_moral",
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
    "evs_moral": "EVS / Moral",
    "math": "Math",
    "sst": "SST",
    "computer": "Computer",
    "gk": "GK",
}

CLASS_SUBJECTS: dict[str, tuple[str, ...]] = {
    "Nursery": ("english", "hindi", "math"),
    "LKG": ("english", "hindi", "math"),
    "UKG": ("english", "hindi", "math"),
    "Class 1": ("hindi", "english", "evs_moral", "math", "computer", "gk"),
    "Class 2": ("hindi", "english", "evs_moral", "math", "computer", "gk"),
    "Class 3": ("hindi", "english", "evs_moral", "math", "computer", "gk"),
    "Class 4": ("hindi", "english", "evs_moral", "math", "computer", "gk"),
    "Class 5": ("hindi", "english", "evs_moral", "math", "computer", "gk"),
    "Class 6": ("science", "hindi", "english", "sanskrit", "math", "sst", "computer", "gk"),
    "Class 7": ("science", "hindi", "english", "sanskrit", "math", "sst", "computer", "gk"),
    "Class 8": ("science", "hindi", "english", "sanskrit", "math", "sst", "computer", "gk"),
}

CLASS_EXAM_TITLE: dict[str, str] = {
    "Nursery": "Pre-Primary Examination Result",
    "LKG": "Pre-Primary Examination Result",
    "UKG": "Pre-Primary Examination Result",
    "Class 1": "Primary Examination Result",
    "Class 2": "Primary Examination Result",
    "Class 3": "Primary Examination Result",
    "Class 4": "Primary Examination Result",
    "Class 5": "Primary Examination Result",
    "Class 6": "Middle Examination Result",
    "Class 7": "Middle Examination Result",
    "Class 8": "Middle Examination Result",
}

MAX_MARKS_PER_SUBJECT = 50
MAX_TOTAL_MARKS = MAX_MARKS_PER_SUBJECT * len(SUBJECT_FIELDS)
MAX_ADMIN_ACCOUNTS = 5


def get_subjects_for_class(class_name: str | None) -> tuple[str, ...]:
    """Return the ordered subject column names for a given class."""
    if class_name and class_name in CLASS_SUBJECTS:
        return CLASS_SUBJECTS[class_name]
    return SUBJECT_FIELDS


def get_exam_title_for_class(class_name: str | None) -> str:
    """Return the human-friendly exam section title for a given class."""
    if class_name and class_name in CLASS_EXAM_TITLE:
        return CLASS_EXAM_TITLE[class_name]
    return "Annual Examination Result"


def normalize_roll_number(roll_number: str) -> str:
    """Normalize roll number by trimming spaces and uppercasing letters (e.g. 'n01 ' -> 'N01')."""
    return re.sub(r"\s+", "", str(roll_number or "")).upper()


def is_valid_roll_number(roll_number: str) -> bool:
    """Check whether a normalized roll number is valid for Nursery to Class 8."""
    try:
        infer_class_from_roll_number(roll_number)
        return True
    except ValueError:
        return False


def infer_class_from_roll_number(roll_number: str) -> str:
    """Return the class name using the school's confirmed roll-number series.

    - N01-series -> Nursery
    - L01-series -> LKG
    - U01-series -> UKG
    - 101-series -> Class 1
    - 201-series -> Class 2
    - 301-series -> Class 3
    - 401-series -> Class 4
    - 501-series -> Class 5
    - 601-series -> Class 6
    - 701-series -> Class 7
    - 801-series -> Class 8
    """
    roll = normalize_roll_number(roll_number)
    if not roll or len(roll) > 20:
        raise ValueError("Roll number is required.")

    if roll[0] in {"N", "L", "U"} and roll[1:].isdigit():
        prefix_map = {"N": "Nursery", "L": "LKG", "U": "UKG"}
        return prefix_map[roll[0]]

    if roll.isdigit() and roll[0] in {"1", "2", "3", "4", "5", "6", "7", "8"}:
        return f"Class {roll[0]}"

    raise ValueError(
        "Roll number must start with N (Nursery), L (LKG), U (UKG), or digits 1 to 8 (Class 1 to Class 8)."
    )


class Student(db.Model):
    """One student profile from the school's official dataset."""

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
        return f"<Student roll={self.roll_number!r} class={self.class_name!r} name={self.student_name!r}>"


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
            for field in ALL_SUBJECT_FIELDS
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

    # NA or blank marks are stored as None, never converted to zero.
    science = db.Column(db.Float, nullable=True)
    hindi = db.Column(db.Float, nullable=True)
    english = db.Column(db.Float, nullable=True)
    sanskrit = db.Column(db.Float, nullable=True)
    evs_moral = db.Column(db.Float, nullable=True)
    math = db.Column(db.Float, nullable=True)
    sst = db.Column(db.Float, nullable=True)
    computer = db.Column(db.Float, nullable=True)
    gk = db.Column(db.Float, nullable=True)

    # Keep the Total and Status values supplied in the original sheet for audit only.
    sheet_total = db.Column(db.Float, nullable=True)
    sheet_status = db.Column(db.String(30), nullable=True)

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
    def applicable_subjects(self) -> tuple[str, ...]:
        class_name = self.student.class_name if self.student else None
        return get_subjects_for_class(class_name)

    @property
    def subject_count(self) -> int:
        return len(self.applicable_subjects)

    @property
    def marks_complete(self) -> bool:
        return all(getattr(self, field) is not None for field in self.applicable_subjects)

    @property
    def pending_subjects(self) -> list[str]:
        return [
            SUBJECT_LABELS[field]
            for field in self.applicable_subjects
            if getattr(self, field) is None
        ]

    @property
    def calculated_total(self) -> float | None:
        if not self.marks_complete:
            return None
        return round(
            sum(float(getattr(self, field)) for field in self.applicable_subjects),
            2,
        )

    @property
    def partial_entered_total(self) -> float:
        """Sum of currently entered marks (used for audit comparison when marks are pending)."""
        return round(
            sum(
                float(getattr(self, field))
                for field in self.applicable_subjects
                if getattr(self, field) is not None
            ),
            2,
        )

    @property
    def maximum_marks(self) -> int:
        return MAX_MARKS_PER_SUBJECT * len(self.applicable_subjects)

    @property
    def percentage(self) -> float | None:
        total = self.calculated_total
        max_marks = self.maximum_marks
        if total is None or max_marks <= 0:
            return None
        return round((total / max_marks) * 100, 2)

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
    """Secure administrator accounts (up to MAX_ADMIN_ACCOUNTS = 5)."""

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


class StudentAccess(db.Model):
    """Hashed individual access code for a student's result portal (preserved for compatibility)."""

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


class RollRecoveryRequest(db.Model):
    """Parent/guardian request to recover a forgotten roll number (verified by school admin)."""

    __tablename__ = "roll_recovery_requests"

    id = db.Column(db.Integer, primary_key=True)
    reference_code = db.Column(db.String(20), nullable=False, unique=True, index=True)
    student_name = db.Column(db.String(120), nullable=False)
    class_name = db.Column(db.String(20), nullable=False, index=True)
    father_name = db.Column(db.String(120), nullable=True)
    mother_name = db.Column(db.String(120), nullable=True)
    dob = db.Column(db.Date, nullable=True)
    parent_mobile = db.Column(db.String(20), nullable=False)

    # Status: PENDING, APPROVED, REJECTED
    status = db.Column(db.String(20), nullable=False, default="PENDING", index=True)
    matched_student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_roll_number = db.Column(db.String(20), nullable=True)
    admin_note = db.Column(db.String(255), nullable=True)
    resolved_by_username = db.Column(db.String(80), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    matched_student = db.relationship("Student", foreign_keys=[matched_student_id])
