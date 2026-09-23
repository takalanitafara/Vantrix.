"""Site meta routes: favicon + robots.txt (public, no marketplace data)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, PlainTextResponse

from . import config

router = APIRouter()

FAVICON = config.BASE_DIR / "web" / "favicon.svg"


@router.get("/robots.txt")
def robots():
    # Private production deployment: never index.
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@router.get("/favicon.svg")
def favicon_svg():
    return FileResponse(FAVICON, media_type="image/svg+xml")


@router.get("/favicon.ico")
def favicon_ico():
    # Modern browsers accept the SVG mark at this URL too.
    return FileResponse(FAVICON, media_type="image/svg+xml")
