"""QuantVenue platform application factory.

Module paths / the `server:app` import target are part of the technical
contract and must not be renamed. User-facing brand is "QuantVenue".

Explicitly out of scope here (never import into this app): trading logic,
brokers, execution, risk engines. Any such legacy code belongs in
`server.legacy` and stays isolated - see server/legacy/README.md.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from . import admin, auth, catalog, checkout, config, developers, site, subscriptions
from .db import init_db
from .privacy import PrivateModeMiddleware, SecurityHeadersMiddleware
from .util import render_error, wants_json

log = logging.getLogger("quantvenue")


def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/") or wants_json(request)


def create_app() -> FastAPI:
    init_db()

    app = FastAPI(title="QuantVenue", version="2.0.0", docs_url="/api/docs")
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PrivateModeMiddleware)
    app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "web")), name="static")

    app.include_router(auth.router)
    app.include_router(catalog.router)
    app.include_router(checkout.router)
    app.include_router(developers.router)
    app.include_router(subscriptions.router)
    app.include_router(admin.router)
    app.include_router(site.router)

    @app.get("/health")
    def health():
        # Public endpoint - deployment monitoring only.
        return {
            "ok": True,
            "service": "Vantrix",  # technical identifier, keep as-is
            "status": "running",
            "brand": "QuantVenue",
        }

    # ---------------------------------------------------------- error pages

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        message = str(exc.detail)
        if _is_api(request):
            return JSONResponse({"error": message}, status_code=exc.status_code)
        return render_error(request, exc.status_code, message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        message = "Invalid submission — please check the form fields."
        if _is_api(request):
            return JSONResponse({"error": message}, status_code=422)
        return render_error(request, 422, message)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        message = "Something went wrong on our side. Please try again."
        if _is_api(request):
            return JSONResponse({"error": "internal server error"}, status_code=500)
        return render_error(request, 500, message)

    return app


app = create_app()
