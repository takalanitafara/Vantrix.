"""Shared helpers: template rendering, error pages, misc."""

from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from . import config

TEMPLATES = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))


def wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


def api_or_json(request: Request) -> bool:
    """API routes always speak JSON for auth errors, whatever the Accept header."""
    return request.url.path.startswith("/api/") or wants_json(request)


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "item"


TEMPLATES.env.globals["money"] = money


def render(request: Request, name: str, status_code: int = 200, **context):
    from .auth import is_owner, session_user
    from .db import connect

    user = context.get("user")
    if user is None and "user" not in context:
        conn = connect()
        try:
            user = session_user(request, conn)
        finally:
            conn.close()
        context["user"] = user
    context.setdefault("brand", "QuantVenue")
    context.setdefault("private_mode", config.private_mode())
    context["owner"] = is_owner(user)
    return TEMPLATES.TemplateResponse(request, name, context, status_code=status_code)


def render_error(request: Request, status: int, message: str, **context):
    if wants_json(request):
        return JSONResponse({"error": message}, status_code=status)
    return render(
        request, "error.html", status_code=status,
        status=status, message=message, **context,
    )
