from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask
from config import Config
from extensions import db


def main() -> int:
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    with app.app_context():
        if db.engine.url.get_backend_name() != "sqlite":
            print("This helper backs up local SQLite only. Use your hosted database provider's backup/snapshot tools for PostgreSQL.")
            return 2
        database_path = Path(db.engine.url.database)
        if not database_path.is_file():
            print("Database file not found:", database_path)
            return 1
        backup_dir = Path(__file__).resolve().parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"abc_school_{stamp}.db"
        with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as destination:
            source.backup(destination)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            backup_path.unlink(missing_ok=True)
            print("Backup integrity check failed:", integrity)
            return 1
        print("Backup created:", backup_path.name)
        print("Integrity:", integrity)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
