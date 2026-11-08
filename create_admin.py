from getpass import getpass

from sqlalchemy import func
from werkzeug.security import generate_password_hash

from app import app, db
from models import AdminUser, MAX_ADMIN_ACCOUNTS


def main():
    with app.app_context():
        db.create_all()
        count = AdminUser.query.count()
        if count >= MAX_ADMIN_ACCOUNTS:
            print(f"Admin account limit reached: maximum {MAX_ADMIN_ACCOUNTS} accounts.")
            return

        print(f"Administrator Accounts: {count} / {MAX_ADMIN_ACCOUNTS} used")
        username = input("New admin username: ").strip()
        if not username or len(username) > 80:
            print("Username must contain 1 to 80 characters.")
            return
        if AdminUser.query.filter(func.lower(AdminUser.username) == username.lower()).first():
            print("That username already exists.")
            return

        password = getpass("New password (minimum 12 characters): ")
        confirm = getpass("Confirm password: ")
        if len(password) < 12:
            print("Password must be at least 12 characters long.")
            return
        if password != confirm:
            print("Passwords do not match.")
            return

        admin = AdminUser(
            username=username,
            password_hash=generate_password_hash(password),
            active=True,
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin account created successfully.")
        print(
            f"Active admin accounts: {AdminUser.query.filter_by(active=True).count()} "
            f"(Total: {AdminUser.query.count()} / {MAX_ADMIN_ACCOUNTS})"
        )


if __name__ == "__main__":
    main()
