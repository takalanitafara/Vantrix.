"""Operational CLI: python -m server.cli <command>

Commands:
  create-user <email> <password> [--admin] [--name "Display Name"]
  promote <email>          grant admin role
  seed                     ensure sample plans/listings exist
"""

from __future__ import annotations

import argparse

from .auth import hash_password
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
        print(f"created {email} role={role}")
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="server.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cu = sub.add_parser("create-user")
    cu.add_argument("email")
    cu.add_argument("password")
    cu.add_argument("--name", default="")
    cu.add_argument("--admin", action="store_true")

    pr = sub.add_parser("promote")
    pr.add_argument("email")

    sub.add_parser("seed")

    args = parser.parse_args()
    init_db()
    if args.cmd == "create-user":
        create_user(args.email, args.password, args.name, args.admin)
    elif args.cmd == "promote":
        promote(args.email)
    elif args.cmd == "seed":
        print("database initialized (plans + sample listings ensured)")


if __name__ == "__main__":
    main()
