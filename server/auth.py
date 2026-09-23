"""Accounts: password hashing, signed-cookie sessions, sign-in/sign-up routes.

Access model (owner-directed):
  * role 'admin'          -> owner/admin account (also granted via QUANTVENUE_ADMIN_EMAILS)
  * role 'developer'      -> seller with a developer profile
  * role 'user'           -> buyer
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer

from . import config
from .db import connect
from .util import api_or_json

router = APIRouter()

SESSION_COOKIE = "qv_session"
SESSION_MAX_AGE = 7 * 24 * 3600


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


def issue_session(response, user_id: int) -> None:
    token = _serializer().dumps({"uid": user_id})
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
    return conn.execute(
        "SELECT * FROM users WHERE id = ?", (data.get("uid"),)
    ).fetchone()


def is_owner(user) -> bool:
    """Owner/admin access: DB role admin OR email in QUANTVENUE_ADMIN_EMAILS."""
    if user is None:
        return False
    return user["role"] == "admin" or config.is_admin_email(user["email"])


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
        from .util import render_error
        return render_error(request, 403, "Admin access required.")
    return user


# ---------------------------------------------------------------- routes

@router.get("/signin")
def signin_form(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    from .util import render
    user = session_user(request, conn)
    return render(request, "signin.html", user=user)


@router.post("/signin")
def signin(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    conn: sqlite3.Connection = Depends(db_dep),
):
    from .util import render_error
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
    issue_session(response, user["id"])
    return response


@router.get("/signup")
def signup_form(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    from .util import render
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
    from .util import render_error
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
    issue_session(response, cur.lastrowid)
    return response


@router.get("/account")
def account_page(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    from .util import render
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    return render(request, "account.html", user=user)


@router.post("/signout")
def signout():
    response = RedirectResponse("/", status_code=303)
    clear_session(response)
    return response
