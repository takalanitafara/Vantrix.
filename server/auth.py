"""Accounts: password hashing, signed-cookie sessions, sign-in/sign-up routes.

Access model (owner-directed):
  * role 'admin'          -> owner/admin account (also granted via QUANTVENUE_ADMIN_EMAILS)
  * role 'developer'      -> seller with a developer profile
  * role 'user'           -> buyer

Security notes:
  * Passwords are only ever hashed (PBKDF2); the plaintext is never stored,
    displayed, logged, or returned anywhere.
  * Sessions embed a per-user pw_epoch; changing or resetting a password bumps
    it, which invalidates every previously issued session cookie.
  * Password-reset tokens are single-use, short-lived, stored hashed, and
    delivered only through operator channels (server console / CLI) - never in
    web responses.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import sys
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer

from . import config
from .db import connect
from .util import api_or_json, render, render_error

router = APIRouter()

SESSION_COOKIE = "qv_session"
SESSION_MAX_AGE = 7 * 24 * 3600

RESET_TTL_MINUTES = 30
_RESET_LIMIT = 5          # forgot-password requests ...
_RESET_WINDOW = 3600.0    # ... per key per hour
_RESET_ATTEMPTS: dict[str, list[float]] = {}


# ---------------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 200_000
    ).hex()
    return f"pbkdf2${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _scheme, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 200_000
    ).hex()
    return hmac.compare_digest(candidate, digest)


# ---------------------------------------------------------------- sessions

def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(config.secret_key(), salt="qv-session")


def issue_session(response, user_id: int, epoch: int = 1) -> None:
    token = _serializer().dumps({"uid": user_id, "ep": epoch})
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_MAX_AGE,
        httponly=True, samesite="lax",
    )


def clear_session(response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def session_user(request: Request, conn: sqlite3.Connection):
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return None
    try:
        data = _serializer().loads(token)
    except BadSignature:
        return None
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (data.get("uid"),)
    ).fetchone()
    if user is None or data.get("ep") != user["pw_epoch"]:
        return None  # cookie predates a password change/reset
    return user


def is_owner(user) -> bool:
    """Owner/admin access: DB role admin OR email in QUANTVENUE_ADMIN_EMAILS."""
    if user is None:
        return False
    return user["role"] == "admin" or config.is_admin_email(user["email"])


# ------------------------------------------------------- password reset

def reset_eligible(user) -> bool:
    """Password reset is scoped to the owner/admin account only."""
    return is_owner(user)


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def bump_pw_epoch(conn: sqlite3.Connection, user_id: int) -> int:
    conn.execute(
        "UPDATE users SET pw_epoch = pw_epoch + 1 WHERE id = ?", (user_id,)
    )
    return conn.execute(
        "SELECT pw_epoch FROM users WHERE id = ?", (user_id,)
    ).fetchone()["pw_epoch"]


def invalidate_reset_tokens(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "UPDATE password_reset_tokens SET used_at = datetime('now') "
        "WHERE user_id = ? AND used_at IS NULL",
        (user_id,),
    )


def create_reset_token(conn: sqlite3.Connection, user) -> str:
    """Issue a single-use, short-lived reset token. Returns the raw token ONCE
    (for operator delivery); only its hash is persisted."""
    raw = secrets.token_urlsafe(32)
    invalidate_reset_tokens(conn, user["id"])
    conn.execute(
        "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
        "VALUES (?, ?, datetime('now', ?))",
        (user["id"], hash_reset_token(raw), f"+{RESET_TTL_MINUTES} minutes"),
    )
    conn.commit()
    return raw


def consume_reset_token(conn: sqlite3.Connection, raw: str):
    """Return the token row if it is valid (unused and unexpired), else None."""
    if not raw:
        return None
    return conn.execute(
        "SELECT * FROM password_reset_tokens "
        "WHERE token_hash = ? AND used_at IS NULL AND expires_at > datetime('now')",
        (hash_reset_token(raw),),
    ).fetchone()


def _rate_limited(key: str) -> bool:
    now = time.time()
    hits = [t for t in _RESET_ATTEMPTS.get(key, []) if now - t < _RESET_WINDOW]
    if len(hits) >= _RESET_LIMIT:
        _RESET_ATTEMPTS[key] = hits
        return True
    hits.append(now)
    _RESET_ATTEMPTS[key] = hits
    return False


# ---------------------------------------------------------------- deps

def db_dep():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    return session_user(request, conn)


def require_user(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = session_user(request, conn)
    if user is None:
        if api_or_json(request):
            return JSONResponse({"error": "authentication required"}, status_code=401)
        return RedirectResponse("/signin", status_code=303)
    return user


def require_owner(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = session_user(request, conn)
    if user is None:
        if api_or_json(request):
            return JSONResponse({"error": "authentication required"}, status_code=401)
        return RedirectResponse("/signin", status_code=303)
    if not is_owner(user):
        if api_or_json(request):
            return JSONResponse({"error": "admin access required"}, status_code=403)
        return render_error(request, 403, "Admin access required.")
    return user


# ---------------------------------------------------------------- routes

@router.get("/signin")
def signin_form(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = session_user(request, conn)
    return render(request, "signin.html", user=user)


@router.post("/signin")
def signin(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    conn: sqlite3.Connection = Depends(db_dep),
):
    email = email.strip().lower()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not verify_password(password, user["password_hash"]):
        if api_or_json(request):
            return JSONResponse({"error": "invalid credentials"}, status_code=401)
        return render_error(request, 401, "Invalid email or password.")
    # Fail-closed: in private mode only owner/admin accounts may sign in.
    if config.private_mode() and not is_owner(user):
        if api_or_json(request):
            return JSONResponse({"error": "this deployment is private"}, status_code=403)
        return render_error(
            request, 403,
            "This deployment is private. Only the owner/admin account can sign in.",
        )
    # Keep owner access robust if the admin-email list changed.
    if config.is_admin_email(user["email"]) and user["role"] != "admin":
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],))
        conn.commit()
    response = RedirectResponse("/", status_code=303)
    issue_session(response, user["id"], user["pw_epoch"])
    return response


@router.get("/signup")
def signup_form(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = session_user(request, conn)
    return render(request, "signup.html", user=user)


@router.post("/signup")
def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(...),
    conn: sqlite3.Connection = Depends(db_dep),
):
    email = email.strip().lower()
    # Public signups are blocked in private mode; owner/admin emails may still
    # onboard so the deployment stays owner-accessible.
    if config.private_mode() and not config.is_admin_email(email):
        if api_or_json(request):
            return JSONResponse(
                {"error": "public signups are disabled on this deployment"},
                status_code=403,
            )
        return render_error(
            request, 403,
            "Public signups are disabled. This deployment is invite-only "
            "(owner/admin accounts).",
        )
    if len(password) < 8:
        if api_or_json(request):
            return JSONResponse({"error": "password too short"}, status_code=400)
        return render_error(request, 400, "Password must be at least 8 characters.")
    exists = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if exists:
        if api_or_json(request):
            return JSONResponse({"error": "email already registered"}, status_code=409)
        return render_error(request, 409, "That email is already registered.")
    role = "admin" if config.is_admin_email(email) else "user"
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
        (email, hash_password(password), display_name.strip() or email.split("@")[0], role),
    )
    conn.commit()
    response = RedirectResponse("/", status_code=303)
    issue_session(response, cur.lastrowid, 1)
    return response


# ------------------------------------------------- signed-in password change

@router.get("/account")
def account_page(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    return render(request, "account.html", user=user)


@router.post("/account/profile")
def update_profile(
    request: Request,
    display_name: str = Form(...),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    name = display_name.strip()
    if not name:
        return render_error(request, 400, "Display name cannot be empty.", user=user)
    conn.execute(
        "UPDATE users SET display_name = ? WHERE id = ?", (name, user["id"])
    )
    conn.commit()
    return RedirectResponse("/account?notice=profile_updated", status_code=303)


@router.post("/account/password")
def update_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    if not verify_password(current_password, user["password_hash"]):
        return render_error(request, 400, "Current password is incorrect.", user=user)
    if len(new_password) < 8:
        return render_error(
            request, 400, "New password must be at least 8 characters.", user=user
        )
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user["id"]),
    )
    new_epoch = bump_pw_epoch(conn, user["id"])   # kills every other session
    invalidate_reset_tokens(conn, user["id"])     # pending reset links die too
    conn.commit()
    response = RedirectResponse("/account?notice=password_changed", status_code=303)
    issue_session(response, user["id"], new_epoch)  # keep THIS device signed in
    return response


# ------------------------------------------------- forgot / reset password

@router.get("/forgot-password")
def forgot_form(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = session_user(request, conn)
    return render(request, "forgot_password.html", user=user, sent=False)


@router.post("/forgot-password")
def forgot_submit(
    request: Request,
    email: str = Form(""),
    conn: sqlite3.Connection = Depends(db_dep),
):
    email_norm = (email or "").strip().lower()
    client = request.client.host if request.client else "?"
    if _rate_limited(f"{email_norm}|{client}"):
        return render_error(
            request, 429,
            "Too many reset requests. Please wait a while before trying again.",
        )
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email_norm,)
    ).fetchone()
    if reset_eligible(user):
        raw = create_reset_token(conn, user)
        # Operator-channel delivery ONLY (docker compose logs / server console).
        # This is a single-use reset token, not the password - the password is
        # never displayed, logged, or returned anywhere.
        print(
            f"[quantvenue] password reset for {email_norm}: "
            f"/reset-password?token={raw} "
            f"(single use, valid {RESET_TTL_MINUTES} minutes)",
            file=sys.stderr,
        )
    # Identical neutral response either way (no account enumeration).
    return render(request, "forgot_password.html", user=None, sent=True)


@router.get("/reset-password")
def reset_form(
    request: Request, token: str = "", conn: sqlite3.Connection = Depends(db_dep)
):
    if consume_reset_token(conn, token) is None:
        return render_error(
            request, 404,
            "This password reset link is invalid or has expired. "
            "You can request a new one from the sign-in page.",
        )
    # Never reveal which account the token belongs to.
    return render(request, "reset_password.html", user=None, token=token)


@router.post("/reset-password")
def reset_submit(
    request: Request,
    token: str = Form(""),
    new_password: str = Form(...),
    confirm_password: str = Form(""),
    conn: sqlite3.Connection = Depends(db_dep),
):
    row = consume_reset_token(conn, token)
    if row is None:
        return render_error(
            request, 404,
            "This password reset link is invalid or has expired. "
            "You can request a new one from the sign-in page.",
        )
    if new_password != confirm_password:
        return render_error(
            request, 400, "Passwords do not match.", token=token
        )
    if len(new_password) < 8:
        return render_error(
            request, 400, "New password must be at least 8 characters.", token=token
        )
    conn.execute(
        "UPDATE password_reset_tokens SET used_at = datetime('now') WHERE id = ?",
        (row["id"],),
    )
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), row["user_id"]),
    )
    bump_pw_epoch(conn, row["user_id"])        # invalidate all sessions
    invalidate_reset_tokens(conn, row["user_id"])  # and any sibling links
    conn.commit()
    return RedirectResponse("/signin?notice=password_reset", status_code=303)


@router.post("/signout")
def signout():
    response = RedirectResponse("/", status_code=303)
    clear_session(response)
    return response
