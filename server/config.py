"""QuantVenue platform configuration.

Env var identifiers are part of the technical contract and must not be renamed:

  QUANTVENUE_PRIVATE_MODE   fail-closed privacy gate (default: private)
  QUANTVENUE_ADMIN_EMAILS   comma-separated owner/admin emails
  QUANTVENUE_SECRET_KEY     session signing key
  QUANTVENUE_DB_PATH        SQLite database file (on the persistent volume)
  QUANTVENUE_DATA_DIR       data directory root (persistent volume mount)
  PORT                      HTTP port (default 3000)

Brand wording in the UI is "QuantVenue"; repo/module identifiers stay Vantrix-era.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Anything not explicitly "falsey" means PRIVATE (fail-closed).
_FALSEY = {"false", "0", "no", "off", "public", "disabled"}

_SECRET: str | None = None


def private_mode() -> bool:
    raw = os.environ.get("QUANTVENUE_PRIVATE_MODE")
    if raw is None or not raw.strip():
        return True  # fail-closed: unset or blank -> private
    return raw.strip().lower() not in _FALSEY


def admin_emails() -> set[str]:
    raw = os.environ.get("QUANTVENUE_ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_admin_email(email: str | None) -> bool:
    return (email or "").strip().lower() in admin_emails()


def data_dir() -> Path:
    raw = os.environ.get("QUANTVENUE_DATA_DIR", "").strip()
    return Path(raw) if raw else BASE_DIR / "data"


def db_path() -> Path:
    raw = os.environ.get("QUANTVENUE_DB_PATH", "").strip()
    return Path(raw) if raw else data_dir() / "quantvenue.db"


def secret_key() -> str:
    """Session signing key. Ephemeral fallback keeps dev/test working."""
    global _SECRET
    if _SECRET is None:
        env = os.environ.get("QUANTVENUE_SECRET_KEY", "").strip()
        if env:
            _SECRET = env
        else:
            _SECRET = secrets.token_hex(32)
            print(
                "[quantvenue] QUANTVENUE_SECRET_KEY unset - using ephemeral key "
                "(sessions reset on restart). Set it in production."
            )
    return _SECRET


def port() -> int:
    try:
        return int(os.environ.get("PORT", "3000"))
    except ValueError:
        return 3000
