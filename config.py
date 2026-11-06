
from pathlib import Path
import os

from dotenv import load_dotenv


# Main project directory
BASE_DIR = Path(__file__).resolve().parent

# Load private environment settings
load_dotenv(BASE_DIR / ".env")

# Private database directory
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

# Secret key
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY missing. Please check your .env file."
    )


# Database configuration
database_url = os.getenv("DATABASE_URL", "").strip()

# Convert Render PostgreSQL URLs to the Psycopg 3 driver
if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql+psycopg://",
        1
    )
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1
    )

# Use local SQLite during development
if not database_url:
    local_db = INSTANCE_DIR / "abc_school.db"
    database_url = f"sqlite:///{local_db.as_posix()}"


class Config:

    SECRET_KEY = SECRET_KEY

    SQLALCHEMY_DATABASE_URI = database_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SESSION_COOKIE_SECURE = (
        os.getenv("COOKIE_SECURE", "false")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
    )

    # Form security
    WTF_CSRF_ENABLED = True

    # Maximum upload size: 2 MB
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
