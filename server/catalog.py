"""Marketplace catalog: bot listings API + public catalog pages.

API contract (technical, keep as-is):
  GET /api/bots          list published listings (q, category, featured filters)
  GET /api/bots/{slug}   one listing by slug
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .auth import current_user, db_dep, require_user
from .util import render, render_error

router = APIRouter()


def _bot_json(row: sqlite3.Row) -> dict:
    rating = row["rating_avg"]
    return {
        "slug": row["slug"],
        "name": row["name"],
        "tagline": row["tagline"],
        "description": row["description"],
        "category": row["category"],
        "price_cents": row["price_cents"],
        "developer": row["developer_name"],
        "featured": bool(row["featured"]),
        "status": row["status"],
        "rating_avg": round(rating, 2) if rating is not None else None,
        "review_count": row["review_count"],
    }


BOT_SELECT = """
SELECT b.*, d.display_name AS developer_name, d.slug AS developer_slug,
       (SELECT AVG(r.rating) FROM reviews r
         WHERE r.bot_id = b.id AND r.status = 'approved') AS rating_avg,
       (SELECT COUNT(*) FROM reviews r
         WHERE r.bot_id = b.id AND r.status = 'approved') AS review_count
FROM bots b LEFT JOIN developer_profiles d ON d.id = b.developer_id
"""


# ---------------------------------------------------------------- API

@router.get("/api/bots")
def api_bots(
    request: Request,
    q: str = "",
    category: str = "",
    featured: bool = False,
    conn: sqlite3.Connection = Depends(db_dep),
):
    sql = BOT_SELECT + " WHERE b.status = 'published'"
    params: list = []
    if q:
        sql += " AND (b.name LIKE ? OR b.tagline LIKE ? OR b.description LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if category:
        sql += " AND b.category = ?"
        params.append(category)
    if featured:
        sql += " AND b.featured = 1"
    sql += " ORDER BY b.featured DESC, b.name"
    rows = conn.execute(sql, params).fetchall()
    return {"bots": [_bot_json(r) for r in rows]}


@router.get("/api/bots/{slug}")
def api_bot(slug: str, conn: sqlite3.Connection = Depends(db_dep)):
    row = conn.execute(BOT_SELECT + " WHERE b.slug = ?", (slug,)).fetchone()
    if row is None or row["status"] != "published":
        return JSONResponse({"error": "bot not found"}, status_code=404)
    return _bot_json(row)


# ---------------------------------------------------------------- pages

@router.get("/")
def catalog_page(
    request: Request,
    q: str = "",
    category: str = "",
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = current_user(request, conn)
    sql = BOT_SELECT + " WHERE b.status = 'published'"
    params: list = []
    if q:
        sql += " AND (b.name LIKE ? OR b.tagline LIKE ? OR b.description LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if category:
        sql += " AND b.category = ?"
        params.append(category)
    sql += " ORDER BY b.featured DESC, b.name"
    bots = conn.execute(sql, params).fetchall()
    categories = [
        r["category"]
        for r in conn.execute(
            "SELECT DISTINCT category FROM bots WHERE status='published' ORDER BY category"
        )
    ]
    return render(
        request, "index.html", user=user, bots=bots, categories=categories,
        q=q, category=category,
    )


@router.get("/bot/{slug}")
def bot_page(slug: str, request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = current_user(request, conn)
    bot = conn.execute(BOT_SELECT + " WHERE b.slug = ?", (slug,)).fetchone()
    if bot is None or bot["status"] != "published":
        return render_error(request, 404, "That bot listing was not found.", user=user)
    reviews = conn.execute(
        """
        SELECT r.*, u.display_name FROM reviews r JOIN users u ON u.id = r.user_id
        WHERE r.bot_id = ? AND r.status = 'approved' ORDER BY r.created_at DESC
        """,
        (bot["id"],),
    ).fetchall()
    my_review = None
    if user is not None:
        my_review = conn.execute(
            "SELECT * FROM reviews WHERE bot_id = ? AND user_id = ?",
            (bot["id"], user["id"]),
        ).fetchone()
    return render(
        request, "bot.html", user=user, bot=bot, reviews=reviews, my_review=my_review,
    )


@router.post("/bot/{slug}/reviews")
def submit_review_form(
    slug: str,
    request: Request,
    rating: int = Form(...),
    body: str = Form(""),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_user(request, conn)
    if not hasattr(user, "keys"):  # error response from dependency
        return user
    bot = conn.execute("SELECT * FROM bots WHERE slug = ?", (slug,)).fetchone()
    if bot is None:
        return render_error(request, 404, "That bot listing was not found.", user=user)
    _upsert_review(conn, bot["id"], user["id"], rating, body)
    return RedirectResponse(f"/bot/{slug}?notice=review_submitted", status_code=303)


@router.post("/api/bots/{slug}/reviews")
def submit_review_api(
    slug: str,
    request: Request,
    rating: int = Form(...),
    body: str = Form(""),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_user(request, conn)
    if not hasattr(user, "keys"):
        return user
    bot = conn.execute("SELECT * FROM bots WHERE slug = ?", (slug,)).fetchone()
    if bot is None:
        return JSONResponse({"error": "bot not found"}, status_code=404)
    if not 1 <= rating <= 5:
        return JSONResponse({"error": "rating must be 1..5"}, status_code=400)
    _upsert_review(conn, bot["id"], user["id"], rating, body)
    return JSONResponse(
        {"ok": True, "status": "pending", "note": "review queued for moderation"},
        status_code=201,
    )


def _upsert_review(conn, bot_id: int, user_id: int, rating: int, body: str) -> None:
    rating = max(1, min(5, int(rating)))
    conn.execute(
        """
        INSERT INTO reviews (bot_id, user_id, rating, body, status)
        VALUES (?, ?, ?, ?, 'pending')
        ON CONFLICT (bot_id, user_id) DO UPDATE SET
            rating = excluded.rating, body = excluded.body, status = 'pending'
        """,
        (bot_id, user_id, rating, (body or "").strip()),
    )
    conn.commit()
