
import re

import bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import SessionLocal, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    """Return a salted password hash for database storage."""
    password_bytes = password.encode("utf-8")

    # bcrypt supports passwords up to 72 bytes.
    if len(password_bytes) > 72:
        raise ValueError(
            "Password is too long. Use at most 72 UTF-8 bytes."
        )

    hashed = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(rounds=12),
    )
    return hashed.decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    """Check a password against its stored hash."""
    try:
        password_bytes = password.encode("utf-8")

        if len(password_bytes) > 72:
            return False

        return bcrypt.checkpw(
            password_bytes,
            stored_hash.encode("utf-8"),
        )
    except (ValueError, TypeError, UnicodeError):
        return False


def register_user(
    name: str,
    email: str,
    password: str,
    confirm_password: str,
) -> dict:
    """Validate details and create a new account."""

    name = name.strip()
    email = normalize_email(email)

    if not name:
        return {"success": False, "message": "Please enter your name."}

    if len(name) > 100:
        return {"success": False, "message": "Name is too long."}

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return {
            "success": False,
            "message": "Please enter a valid email address.",
        }

    if len(password) < 8:
        return {
            "success": False,
            "message": "Use a password with at least 8 characters.",
        }

    if len(password.encode("utf-8")) > 72:
        return {
            "success": False,
            "message": "Password is too long. Use at most 72 UTF-8 bytes.",
        }

    if password != confirm_password:
        return {
            "success": False,
            "message": "The passwords do not match.",
        }

    try:
        with SessionLocal() as session:
            existing_user = session.scalar(
                select(User).where(User.email == email)
            )

            if existing_user is not None:
                return {
                    "success": False,
                    "message": "An account with this email already exists.",
                }

            user = User(
                name=name,
                email=email,
                password_hash=hash_password(password),
            )

            session.add(user)
            session.commit()
            session.refresh(user)

            return {
                "success": True,
                "message": "Account created successfully. You can now log in.",
                "user": {
                    "user_id": user.user_id,
                    "name": user.name,
                    "email": user.email,
                },
            }

    except IntegrityError:
        # Handles two registration attempts for the same email.
        return {
            "success": False,
            "message": "That email may already be registered. Please log in.",
        }


def authenticate_user(email: str, password: str) -> dict:
    """Verify login credentials without returning the password hash."""

    email = normalize_email(email)

    with SessionLocal() as session:
        user = session.scalar(
            select(User).where(User.email == email)
        )

        if user is None or not verify_password(
            password, user.password_hash
        ):
            return {
                "success": False,
                "message": "Invalid email or password.",
            }

        return {
            "success": True,
            "message": "Login successful.",
            "user": {
                "user_id": user.user_id,
                "name": user.name,
                "email": user.email,
            },
        }
