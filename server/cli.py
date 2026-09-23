"""Operational CLI: python -m server.cli <command>

Commands:
  create-user <email> [password] [--admin] [--name "Display Name"]
      (password is prompted with hidden input when omitted)
  promote <email>          grant admin role
  reset-token <email>      issue a one-time password-reset link (owner/admin only)
  seed                     ensure sample plans/listings exist
"""

from __future__ import annotations

import argparse
import getpass

from .auth import create_reset_token, hash_password, reset_eligible
from .db import connect, init_db


def create_user(email: str, password: str, name: str, admin: bool) -> None:
    from . import config
    email = email.strip().lower()
    role = "admin" if (admin or config.is_admin_email(email)) else "user"
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, display_name, role) "
            "VALUES (?, ?, ?, ?)",
            (email, hash_password(password), name or email.split("@")[0], role),
        )
        conn.commit()
        print(f"created {email} role={role}")  # never the password
    finally:
        conn.close()


def promote(email: str) -> None:
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE users SET role='admin' WHERE email = ?",
            (email.strip().lower(),),
        )
        conn.commit()
        print("promoted" if cur.rowcount else "no such user")
    finally:
        conn.close()


def reset_token(email: str) -> None:
    """Print a one-time reset link for the owner/admin account (operator only)."""
    conn = connect()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        if not reset_eligible(user):
            print("no eligible owner/admin account with that email")
            return
        raw = create_reset_token(conn, user)
        print(
            "single-use reset link (valid 30 minutes):\n"
            f"/reset-password?token={raw}"
        )
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="server.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cu = sub.add_parser("create-user")
    cu.add_argument("email")
    cu.add_argument("password", nargs="?", default=None)
    cu.add_argument("--name", default="")
    cu.add_argument("--admin", action="store_true")

    pr = sub.add_parser("promote")
    pr.add_argument("email")

    rt = sub.add_parser("reset-token")
    rt.add_argument("email")

    sub.add_parser("seed")

    args = parser.parse_args()
    init_db()
    if args.cmd == "create-user":
        password = args.password
        if not password:
            # Hidden input - the password is never echoed or logged.
            password = getpass.getpass("Password (input hidden): ")
            if password != getpass.getpass("Confirm password: "):
                print("passwords do not match; nothing created")
                return
        create_user(args.email, password, args.name, args.admin)
    elif args.cmd == "promote":
        promote(args.email)
    elif args.cmd == "reset-token":
        reset_token(args.email)
    elif args.cmd == "seed":
        print("database initialized (plans + sample listings ensured)")


if __name__ == "__main__":
    main()
