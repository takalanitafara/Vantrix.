"""QuantVenue platform application factory.

Module paths / the `server:app` import target are part of the technical
contract and must not be renamed. User-facing brand is "QuantVenue".

Explicitly out of scope here (never import into this app): trading logic,
brokers, execution, risk engines. Any such legacy code belongs in
`server.legacy` and stays isolated - see server/legacy/README.md.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import admin, auth, catalog, checkout, config, developers, subscriptions
from .db import init_db
from .privacy import PrivateModeMiddleware


def create_app() -> FastAPI:
    init_db()

    app = FastAPI(title="QuantVenue", version="2.0.0", docs_url="/api/docs")
    app.add_middleware(PrivateModeMiddleware)
    app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "web")), name="static")

    app.include_router(auth.router)
    app.include_router(catalog.router)
    app.include_router(checkout.router)
    app.include_router(developers.router)
    app.include_router(subscriptions.router)
    app.include_router(admin.router)

    @app.get("/health")
    def health():
        # Public endpoint - deployment monitoring only.
        return {
            "ok": True,
            "service": "Vantrix",  # technical identifier, keep as-is
            "status": "running",
            "brand": "QuantVenue",
        }

    return app


app = create_app()
