"""Administration: moderation and platform management (owner/admin only)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from .auth import db_dep, require_owner
from .checkout import _confirm_order
from .util import render, render_error

router = APIRouter(prefix="/admin")


@router.get("")
def admin_home(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = require_owner(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    stats = {
        "users": conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "bots": conn.execute("SELECT COUNT(*) c FROM bots").fetchone()["c"],
        "published": conn.execute(
            "SELECT COUNT(*) c FROM bots WHERE status='published'"
        ).fetchone()["c"],
        "orders": conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"],
        "licenses": conn.execute("SELECT COUNT(*) c FROM licenses").fetchone()["c"],
        "reviews_pending": conn.execute(
            "SELECT COUNT(*) c FROM reviews WHERE status='pending'"
        ).fetchone()["c"],
    }
    finance = conn.execute(
        """
        SELECT COUNT(*) AS orders_total,
               COALESCE(SUM(CASE WHEN status='completed' THEN amount_cents END), 0) AS gross_cents,
               COALESCE(SUM(CASE WHEN status='pending' THEN amount_cents END), 0) AS pending_cents
        FROM orders
        """
    ).fetchone()
    users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    bots = conn.execute(
        """
        SELECT b.*, d.display_name AS developer_name FROM bots b
        LEFT JOIN developer_profiles d ON d.id = b.developer_id
        ORDER BY b.status, b.name
        """
    ).fetchall()
    reviews = conn.execute(
        """
        SELECT r.*, u.display_name AS author, b.name AS bot_name, b.slug AS bot_slug
        FROM reviews r JOIN users u ON u.id = r.user_id JOIN bots b ON b.id = r.bot_id
        ORDER BY r.created_at DESC
        """
    ).fetchall()
    orders = conn.execute(
        """
        SELECT o.*, u.email AS buyer_email, b.name AS bot_name FROM orders o
        JOIN users u ON u.id = o.user_id JOIN bots b ON b.id = o.bot_id
        ORDER BY o.created_at DESC
        """
    ).fetchall()
    products = conn.execute("SELECT * FROM plans ORDER BY price_cents").fetchall()
    return render(
        request, "admin.html", user=user, stats=stats, finance=finance,
        users=users, bots=bots, reviews=reviews, orders=orders, products=products,
    )


@router.post("/users/{user_id}/role")
def set_role(
    user_id: int,
    request: Request,
    role: str = Form(...),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_owner(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    if role not in ("user", "developer", "admin"):
        return render_error(request, 400, "Unknown role.", user=user)
    conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    conn.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/bots/{bot_id}/status")
def set_status(
    bot_id: int,
    request: Request,
    status: str = Form(...),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_owner(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    if status not in ("draft", "published", "delisted"):
        return render_error(request, 400, "Unknown status.", user=user)
    conn.execute("UPDATE bots SET status=? WHERE id=?", (status, bot_id))
    conn.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/bots/{bot_id}/feature")
def set_feature(
    bot_id: int,
    request: Request,
    featured: int = Form(0),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_owner(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    conn.execute(
        "UPDATE bots SET featured=? WHERE id=?", (1 if featured else 0, bot_id)
    )
    conn.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/reviews/{review_id}/moderate")
def moderate_review(
    review_id: int,
    request: Request,
    status: str = Form(...),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_owner(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    if status not in ("pending", "approved", "hidden"):
        return render_error(request, 400, "Unknown status.", user=user)
    conn.execute("UPDATE reviews SET status=? WHERE id=?", (status, review_id))
    conn.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/orders/{ref}/confirm")
def confirm_order_admin(
    ref: str,
    request: Request,
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_owner(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    order, _lic = _confirm_order(conn, ref)
    if order is None:
        return render_error(request, 404, "Order not found.", user=user)
    return RedirectResponse("/admin", status_code=303)
