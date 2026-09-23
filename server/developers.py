"""Developer/seller pages: onboarding, listing management."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from .auth import db_dep, is_owner, require_user
from .util import render, render_error, slugify

router = APIRouter()


def _profile_for(conn, user):
    return conn.execute(
        "SELECT * FROM developer_profiles WHERE user_id = ?", (user["id"],)
    ).fetchone()


def _unique_slug(conn, table: str, base: str) -> str:
    slug = slugify(base)
    n = 2
    while conn.execute(
        f"SELECT id FROM {table} WHERE slug = ?", (slug,)
    ).fetchone():
        slug = f"{slugify(base)}-{n}"
        n += 1
    return slug


@router.get("/developers")
def developers_page(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    from .auth import current_user
    user = current_user(request, conn)
    devs = conn.execute(
        """
        SELECT d.*, COUNT(b.id) AS bot_count FROM developer_profiles d
        LEFT JOIN bots b ON b.developer_id = d.id AND b.status = 'published'
        GROUP BY d.id ORDER BY d.display_name
        """
    ).fetchall()
    return render(request, "developers.html", user=user, developers=devs)


@router.get("/developers/onboard")
def onboard_form(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    existing = _profile_for(conn, user)
    return render(request, "developer_onboard.html", user=user, existing=existing)


@router.post("/developers/onboard")
def onboard(
    request: Request,
    display_name: str = Form(...),
    bio: str = Form(""),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    if _profile_for(conn, user) is not None:
        return render_error(request, 409, "You already have a developer page.", user=user)
    slug = _unique_slug(conn, "developer_profiles", display_name)
    conn.execute(
        "INSERT INTO developer_profiles (user_id, slug, display_name, bio) "
        "VALUES (?, ?, ?, ?)",
        (user["id"], slug, display_name.strip(), bio.strip()),
    )
    if user["role"] == "user":
        conn.execute("UPDATE users SET role='developer' WHERE id = ?", (user["id"],))
    conn.commit()
    return RedirectResponse("/dev", status_code=303)


@router.get("/developers/{slug}")
def developer_page(slug: str, request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    from .auth import current_user
    user = current_user(request, conn)
    dev = conn.execute(
        "SELECT * FROM developer_profiles WHERE slug = ?", (slug,)
    ).fetchone()
    if dev is None:
        return render_error(request, 404, "Developer not found.", user=user)
    bots = conn.execute(
        """
        SELECT b.*, (SELECT AVG(r.rating) FROM reviews r
                      WHERE r.bot_id = b.id AND r.status='approved') AS rating_avg
        FROM bots b WHERE b.developer_id = ? AND b.status = 'published'
        ORDER BY b.name
        """,
        (dev["id"],),
    ).fetchall()
    return render(request, "developer.html", user=user, dev=dev, bots=bots)


@router.get("/dev")
def dev_dashboard(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    dev = _profile_for(conn, user)
    if dev is None:
        return RedirectResponse("/developers/onboard", status_code=303)
    bots = conn.execute(
        "SELECT * FROM bots WHERE developer_id = ? ORDER BY status, name",
        (dev["id"],),
    ).fetchall()
    return render(request, "dev_dashboard.html", user=user, dev=dev, bots=bots)


@router.post("/dev/bots")
def create_bot(
    request: Request,
    name: str = Form(...),
    tagline: str = Form(""),
    description: str = Form(""),
    category: str = Form("general"),
    price_cents: int = Form(0),
    payment_link_url: str = Form(""),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    dev = _profile_for(conn, user)
    if dev is None:
        return RedirectResponse("/developers/onboard", status_code=303)
    slug = _unique_slug(conn, "bots", name)
    conn.execute(
        "INSERT INTO bots (slug, name, tagline, description, category, price_cents, "
        "developer_id, payment_link_url, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')",
        (slug, name.strip(), tagline.strip(), description.strip(),
         category.strip() or "general", max(0, price_cents), dev["id"],
         payment_link_url.strip() or None),
    )
    conn.commit()
    return RedirectResponse("/dev?notice=listing_created", status_code=303)


@router.post("/dev/bots/{bot_id}/update")
def update_bot(
    bot_id: int,
    request: Request,
    name: str = Form(...),
    tagline: str = Form(""),
    description: str = Form(""),
    category: str = Form("general"),
    price_cents: int = Form(0),
    payment_link_url: str = Form(""),
    conn: sqlite3.Connection = Depends(db_dep),
):
    bot, dev, user = _owned_bot(conn, request, bot_id)
    if bot is None:
        return dev  # error response
    conn.execute(
        "UPDATE bots SET name=?, tagline=?, description=?, category=?, "
        "price_cents=?, payment_link_url=? WHERE id=?",
        (name.strip(), tagline.strip(), description.strip(),
         category.strip() or "general", max(0, price_cents),
         payment_link_url.strip() or None, bot_id),
    )
    conn.commit()
    return RedirectResponse("/dev?notice=listing_updated", status_code=303)


@router.post("/dev/bots/{bot_id}/publish")
def publish_bot(bot_id: int, request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    bot, err, _user = _owned_bot(conn, request, bot_id)
    if bot is None:
        return err
    conn.execute("UPDATE bots SET status='published' WHERE id=?", (bot_id,))
    conn.commit()
    return RedirectResponse("/dev?notice=listing_published", status_code=303)


@router.post("/dev/bots/{bot_id}/delist")
def delist_bot(bot_id: int, request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    bot, err, _user = _owned_bot(conn, request, bot_id)
    if bot is None:
        return err
    conn.execute("UPDATE bots SET status='delisted' WHERE id=?", (bot_id,))
    conn.commit()
    return RedirectResponse("/dev?notice=listing_delisted", status_code=303)


def _owned_bot(conn, request, bot_id: int):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return None, user, None
    dev = _profile_for(conn, user)
    bot = conn.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
    if bot is None or dev is None or (bot["developer_id"] != dev["id"] and not is_owner(user)):
        return None, render_error(request, 404, "Listing not found.", user=user), user
    return bot, None, user
