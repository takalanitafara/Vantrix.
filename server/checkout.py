"""Purchases: checkout plumbing + licence grants.

API contract (technical, keep as-is):
  GET  /api/checkout/{slug}          redirect to the bot's stored Stripe
                                     payment link (409 when none is stored)
  POST /api/checkout/confirm/{ref}   payment-confirmation plumbing: marks the
                                     order completed and grants a licence

IMPORTANT: this is plumbing only. No real payments are processed and no Stripe
account is connected (owner-directed deferral). Real Stripe payment links
activate the flow when they are stored on a listing.
"""

from __future__ import annotations

import secrets
import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .auth import current_user, db_dep, is_owner, require_user
from .util import render, render_error, wants_json

router = APIRouter()


def _get_bot(conn, slug: str):
    return conn.execute(
        """
        SELECT b.*, d.display_name AS developer_name FROM bots b
        LEFT JOIN developer_profiles d ON d.id = b.developer_id
        WHERE b.slug = ?
        """,
        (slug,),
    ).fetchone()


def _pending_order(conn, user_id: int, bot_id: int, amount: int):
    order = conn.execute(
        "SELECT * FROM orders WHERE user_id=? AND bot_id=? AND status='pending'",
        (user_id, bot_id),
    ).fetchone()
    if order is None:
        ref = secrets.token_urlsafe(8)
        cur = conn.execute(
            "INSERT INTO orders (ref, user_id, bot_id, amount_cents) VALUES (?, ?, ?, ?)",
            (ref, user_id, bot_id, amount),
        )
        conn.commit()
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return order


def _grant_license(conn, order) -> sqlite3.Row:
    """Idempotent licence grant for a completed order (one active licence)."""
    lic = conn.execute(
        "SELECT * FROM licenses WHERE order_id = ?", (order["id"],)
    ).fetchone()
    if lic is not None:
        return lic
    key = "QV-" + secrets.token_hex(8).upper()
    cur = conn.execute(
        "INSERT INTO licenses (license_key, user_id, bot_id, order_id) VALUES (?, ?, ?, ?)",
        (key, order["user_id"], order["bot_id"], order["id"]),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM licenses WHERE id = ?", (cur.lastrowid,)
    ).fetchone()


def _confirm_order(conn, ref: str):
    order = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if order is None:
        return None, None
    if order["status"] != "completed":
        conn.execute(
            "UPDATE orders SET status='completed', completed_at=datetime('now') "
            "WHERE id = ?",
            (order["id"],),
        )
        conn.commit()
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order["id"],)
        ).fetchone()
    return order, _grant_license(conn, order)


@router.get("/api/checkout/{slug}")
def checkout(slug: str, request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    bot = _get_bot(conn, slug)
    if bot is None or bot["status"] != "published":
        return JSONResponse({"error": "bot not found"}, status_code=404)
    if not bot["payment_link_url"]:
        # 409 when no Stripe payment link is stored (payments not activated).
        if wants_json(request):
            return JSONResponse(
                {
                    "error": "payment link not configured for this bot",
                    "status": "payments_not_activated",
                    "note": "Checkout plumbing is ready; real payments activate "
                            "when a Stripe payment link is stored on the listing.",
                },
                status_code=409,
            )
        return render_error(
            request, 409,
            "Payments are not activated for this listing yet (no payment link "
            "is stored). Checkout plumbing is ready and will activate when the "
            "owner connects a real Stripe payment link.",
            user=user,
        )
    _pending_order(conn, user["id"], bot["id"], bot["price_cents"])
    return RedirectResponse(bot["payment_link_url"], status_code=302)


@router.get("/checkout/confirm/{ref}")
def confirm_page(ref: str, request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    order = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if order is None or (order["user_id"] != user["id"] and not is_owner(user)):
        return render_error(request, 404, "Order not found.", user=user)
    order, lic = _confirm_order(conn, ref)
    bot = conn.execute("SELECT * FROM bots WHERE id = ?", (order["bot_id"],)).fetchone()
    return render(request, "checkout_confirm.html", user=user, order=order, lic=lic, bot=bot)


@router.post("/api/checkout/confirm/{ref}")
def confirm_api(ref: str, request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    """Payment-confirmation plumbing. Placeholder for a future Stripe webhook;
    verifies nothing today because no real payments can occur yet."""
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    order = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if order is None or (order["user_id"] != user["id"] and not is_owner(user)):
        return JSONResponse({"error": "order not found"}, status_code=404)
    order, lic = _confirm_order(conn, ref)
    return {
        "ok": True,
        "order_ref": order["ref"],
        "order_status": order["status"],
        "license_key": lic["license_key"],
        "license_status": lic["status"],
    }


@router.get("/account/my-bots")
def my_bots(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    licenses = conn.execute(
        """
        SELECT l.*, b.name AS bot_name, b.slug AS bot_slug, b.tagline
        FROM licenses l JOIN bots b ON b.id = l.bot_id
        WHERE l.user_id = ? ORDER BY l.created_at DESC
        """,
        (user["id"],),
    ).fetchall()
    orders = conn.execute(
        """
        SELECT o.*, b.name AS bot_name FROM orders o JOIN bots b ON b.id = o.bot_id
        WHERE o.user_id = ? ORDER BY o.created_at DESC
        """,
        (user["id"],),
    ).fetchall()
    return render(request, "my_bots.html", user=user, licenses=licenses, orders=orders)
