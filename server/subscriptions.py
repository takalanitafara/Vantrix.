"""Subscriptions & licensing tiers (platform layer only).

Paid plans stay unbillable on purpose: real payments are owner-deferred.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from .auth import db_dep, require_user
from .util import render, render_error

router = APIRouter()


@router.get("/account/subscriptions")
def subscriptions_page(request: Request, conn: sqlite3.Connection = Depends(db_dep)):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    plans = conn.execute("SELECT * FROM plans ORDER BY price_cents").fetchall()
    current = conn.execute(
        """
        SELECT s.*, p.name AS plan_name, p.slug AS plan_slug, p.price_cents
        FROM user_subscriptions s JOIN plans p ON p.id = s.plan_id
        WHERE s.user_id = ?
        """,
        (user["id"],),
    ).fetchone()
    return render(request, "subscriptions.html", user=user, plans=plans, current=current)


@router.post("/account/subscriptions")
def subscribe(
    request: Request,
    plan_slug: str = Form(...),
    conn: sqlite3.Connection = Depends(db_dep),
):
    user = require_user(request, conn)
    if not isinstance(user, sqlite3.Row):
        return user
    plan = conn.execute(
        "SELECT * FROM plans WHERE slug = ?", (plan_slug,)
    ).fetchone()
    if plan is None:
        return render_error(request, 404, "Plan not found.", user=user)
    # Free plans activate immediately; paid plans queue as 'pending' until the
    # owner activates real payments (explicitly deferred).
    status = "active" if plan["price_cents"] == 0 else "pending"
    conn.execute(
        """
        INSERT INTO user_subscriptions (user_id, plan_id, status) VALUES (?, ?, ?)
        ON CONFLICT (user_id) DO UPDATE SET plan_id=excluded.plan_id,
            status=excluded.status
        """,
        (user["id"], plan["id"], status),
    )
    conn.commit()
    notice = "subscribed" if status == "active" else "paid_plan_pending_payments"
    return RedirectResponse(f"/account/subscriptions?notice={notice}", status_code=303)
