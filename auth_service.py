
import hashlib
import secrets
from datetime import datetime, timedelta

import streamlit as st

from supabase_client import get_supabase_client
from database import SessionLocal, AuthSession


SESSION_DAYS = 7


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_saved_session(user: dict) -> str:
    """Create a random browser token and store only its hash."""

    token = secrets.token_urlsafe(32)

    db = SessionLocal()
    try:
        saved_session = AuthSession(
            session_token_hash=_hash_token(token),
            supabase_user_id=user["id"],
            email=user["email"],
            name=user["name"],
            expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
        )

        db.add(saved_session)
        db.commit()
        return token

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def restore_login(token: str) -> bool:
    """Restore login only if the saved server-side session is valid."""

    if not token:
        return False

    db = SessionLocal()
    try:
        saved_session = (
            db.query(AuthSession)
            .filter(
                AuthSession.session_token_hash == _hash_token(token),
                AuthSession.revoked_at.is_(None),
            )
            .first()
        )

        if saved_session is None:
            return False

        if saved_session.expires_at <= datetime.utcnow():
            saved_session.revoked_at = datetime.utcnow()
            db.commit()
            return False

        user = {
            "id": saved_session.supabase_user_id,
            "email": saved_session.email,
            "name": saved_session.name,
        }

        st.session_state["authenticated_user"] = user
        st.session_state["session_token"] = token
        return True

    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def register_user(
    name: str,
    email: str,
    password: str,
    confirm_password: str,
) -> dict:
    """Register an account through Supabase."""

    name = name.strip()
    email = email.strip().lower()

    if not name:
        return {"success": False, "message": "Please enter your name."}

    if len(name) > 100:
        return {"success": False, "message": "Your name is too long."}

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return {"success": False, "message": "Please enter a valid email address."}

    if len(password) < 8:
        return {
            "success": False,
            "message": "Use a password with at least 8 characters.",
        }

    if password != confirm_password:
        return {"success": False, "message": "The passwords do not match."}

    try:
        response = get_supabase_client().auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {"data": {"name": name}},
            }
        )

        if response.user is None:
            return {
                "success": False,
                "message": "Registration could not be completed. Please try again.",
            }

        if response.session is None:
            return {
                "success": True,
                "verified": False,
                "message": (
                    "Your account was created. Check your email for "
                    "the confirmation link, then return to log in."
                ),
            }

        return {
            "success": True,
            "verified": True,
            "message": "Your account is ready. You can now log in.",
        }

    except Exception:
        return {
            "success": False,
            "message": (
                "Registration failed. Check your Supabase settings and try again."
            ),
        }


def login_user(email: str, password: str) -> dict:
    """Authenticate with Supabase and create a persistent app session."""

    email = email.strip().lower()

    if not email or not password:
        return {"success": False, "message": "Enter your email and password."}

    try:
        response = get_supabase_client().auth.sign_in_with_password(
            {"email": email, "password": password}
        )

        user = response.user

        if user is None or response.session is None:
            return {
                "success": False,
                "message": "Login failed. Please check your credentials.",
            }

        authenticated_user = {
            "id": str(user.id),
            "email": user.email or email,
            "name": (user.user_metadata or {}).get("name") or user.email or email,
        }

        token = _create_saved_session(authenticated_user)

        st.session_state["authenticated_user"] = authenticated_user
        st.session_state["session_token"] = token

        return {
            "success": True,
            "message": "Login successful.",
            "user": authenticated_user,
            "session_token": token,
        }

    except Exception as e:
        print(f"Login/session creation error: {e}")
        return {
            "success": False,
            "message": (
                "Login or session creation failed. "
                "Check the terminal for the error."
            ),
        }


def logout_user(session_token: str | None = None) -> None:
    """Revoke the saved app session and clear the current login."""

    token = session_token or st.session_state.get("session_token")

    try:
        if token:
            db = SessionLocal()
            try:
                saved_session = (
                    db.query(AuthSession)
                    .filter(
                        AuthSession.session_token_hash == _hash_token(token),
                        AuthSession.revoked_at.is_(None),
                    )
                    .first()
                )

                if saved_session:
                    saved_session.revoked_at = datetime.utcnow()
                    db.commit()

            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    finally:
        try:
            get_supabase_client().auth.sign_out()
        except Exception:
            pass

        st.session_state.pop("authenticated_user", None)
        st.session_state.pop("session_token", None)
