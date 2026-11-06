from getpass import getpass

from app import app, db
from models import AdminUser
from werkzeug.security import generate_password_hash


def main():
    with app.app_context():
        db.create_all()
        count = AdminUser.query.count()
        if count >= 5:
            print("Admin account limit reached: maximum 2 accounts.")
            return

        username = input("New admin username: ").strip()
        if not username or len(username) > 80:
            print("Username must contain 1 to 80 characters.")
            return
        if AdminUser.query.filter_by(username=username).first():
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
        print("Active admin accounts:", AdminUser.query.filter_by(active=True).count())


if __name__ == "__main__":
    main()
