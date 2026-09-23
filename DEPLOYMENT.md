# Production deployment — private production, upgradeable in place

Goal (owner-directed): **private production + owner access + upgradeable
deployment** — the same repo upgrades for future releases without a
rebuild-from-scratch. No public launch, no real payments yet.

## Topology

- One container (Python 3.11, FastAPI/Uvicorn) listening on `$PORT` (default 3000)
- One persistent volume mounted at `/app/data` holding the SQLite database
  (`/app/data/quantvenue.db`) — this is the entire mutable state
- `/health` reachable without auth for deployment monitoring; everything else
  is behind the fail-closed `QUANTVENUE_PRIVATE_MODE` gate

## First deploy (docker compose)

```bash
cat > .env <<'EOF'
QUANTVENUE_ADMIN_EMAILS=you@example.com
QUANTVENUE_PRIVATE_MODE=true
QUANTVENUE_SECRET_KEY=<long random string>
PORT=3000
EOF

docker compose up -d --build
curl -s https://your-host/health   # {"ok": true, ...}
```

Bootstrap the owner account (either way):

```bash
docker compose exec quantvenue python -m server.cli create-user you@example.com --admin
# password is prompted with hidden input (omit the argument; it is never echoed or logged)
# or visit /signup with an email listed in QUANTVENUE_ADMIN_EMAILS
```

### Password recovery (owner/admin)

If the owner is locked out, issue a single-use reset link (30-minute expiry,
stored hashed; the password itself is never displayed or logged):

```bash
# option A: CLI prints the link directly
docker compose exec quantvenue python -m server.cli reset-token you@example.com

# option B: request it from /forgot-password on the site, then read the
# operator console delivery:
docker compose logs quantvenue | grep reset-password
```

Then open `/reset-password?token=…`, choose a new password, and sign in.
Changing the password from `/account` (or via reset) signs out every other
session and cancels any outstanding reset links.

Confirm the gate: signed out, `/` and `/api/bots` must return 401; `/health`
must return 200.

## Upgrades (no rebuild-from-scratch)

State lives only in the `quantvenue_data` volume (users, listings, orders,
licences, reviews, subscriptions). Releases replace code, never data:

```bash
git pull                                  # new release
docker compose build quantvenue           # rebuild image (code only)
docker compose up -d                      # swap container; volume persists
docker compose exec quantvenue python -m server.cli seed   # harmless; only fills empty tables
```

Database schema is created with `CREATE TABLE IF NOT EXISTS` on startup; sample
listings/plans are only inserted when tables are empty, so upgrades never
overwrite production data. Take a volume snapshot before risky releases:

```bash
docker compose exec quantvenue cp /app/data/quantvenue.db /app/data/quantvenue.db.bak-$(date +%F)
```

## Platform notes

- **Port:** the app honours `$PORT` (default 3000) — works on platforms that
  inject a port, and on plain Docker alike.
- **Secrets:** set `QUANTVENUE_SECRET_KEY` permanently, or sessions reset on
  every restart (an ephemeral key is generated with a startup warning).
- **Fail-closed privacy:** `QUANTVENUE_PRIVATE_MODE` unset/garbage ⇒ private.
  Only DB-role `admin` users or `QUANTVENUE_ADMIN_EMAILS` addresses can sign in;
  public signups return 403; catalog/bot/developer/account/admin pages and APIs
  return auth errors to anyone else.
- **Payments:** leave payment-link fields empty until real Stripe links exist —
  checkout returns 409 "payments_not_activated" by design. Do not mark this
  deployment as handling real money until the owner activates payments.

## Without Docker (systemd sketch)

```ini
[Service]
Environment=PORT=3000
Environment=QUANTVENUE_DATA_DIR=/var/lib/quantvenue
Environment=QUANTVENUE_ADMIN_EMAILS=you@example.com
Environment=QUANTVENUE_SECRET_KEY=...
WorkingDirectory=/opt/quantvenue
ExecStart=/opt/quantvenue/.venv/bin/python -m server
```

Mount/backup `/var/lib/quantvenue` as your persistent volume.
