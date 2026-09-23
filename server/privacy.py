"""QUANTVENUE_PRIVATE_MODE gate (owner-directed private production).

When private (the default, fail-closed):
  * only the owner/admin account (DB role admin or QUANTVENUE_ADMIN_EMAILS)
    can use the app - anyone else gets auth errors everywhere
  * public signups are blocked (the signup route only accepts admin emails)
  * catalog / bot / developer / account / admin pages and APIs expose no
    unauthenticated marketplace data
  * /health stays public for deployment monitoring
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import config
from .auth import is_owner, session_user
from .db import connect
from .util import render_error

# Paths reachable without any session while private.
_OPEN_PATHS = {"/health", "/signin", "/signout", "/signup"}

_ASSET_PREFIXES = ("/static/",)


class PrivateModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not config.private_mode():
            return await call_next(request)

        path = request.url.path
        if path in _OPEN_PATHS or path.startswith(_ASSET_PREFIXES):
            return await call_next(request)

        conn = connect()
        try:
            user = session_user(request, conn)
        finally:
            conn.close()

        if user is None:
            if path.startswith("/api/"):
                return JSONResponse(
                    {"error": "authentication required"}, status_code=401
                )
            return render_error(
                request, 401,
                "This deployment is private. Sign in with the owner/admin account.",
            )

        if not is_owner(user):
            if path.startswith("/api/"):
                return JSONResponse(
                    {"error": "this deployment is private"}, status_code=403
                )
            return render_error(
                request, 403,
                "This deployment is private. Only the owner/admin account has access.",
                user=user,
            )

        return await call_next(request)
