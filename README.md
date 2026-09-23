# QuantVenue — trading-bot marketplace (platform layer only)

**Brand:** QuantVenue / QuantVenue Marketplace (user-facing).
**Repo / module identifiers:** Vantrix-era technical names kept as-is
(`server:app`, `/api/bots`, `/api/checkout/{slug}`, `QUANTVENUE_*` env vars).

QuantVenue is a **professional trading-bot marketplace platform**. Independent
trading bots (like Quantora) are listed, purchased/accessed and managed here as
third-party products. QuantVenue is **not a trading engine**.

## Explicitly out of scope (never built here)

No trading logic, no paper/demo/live trading, no broker connections, no market
scanners, no strategy engines, no MT5/Deriv execution, no risk engines. Any
such legacy code is isolated in `server/legacy/` and is never imported.

## Current status

- **Private production** (owner-directed, no public launch): `QUANTVENUE_PRIVATE_MODE`
  defaults to fail-closed private — only the owner/admin account can use the
  app; public signups are blocked; no unauthenticated marketplace data is
  exposed; `/health` stays public for deployment monitoring.
- **No real payments**: the business is on the free plan with no connected
  Stripe account. Checkout/confirmation is plumbing that activates when real
  Stripe payment links are stored on listings. Real financial figures come only
  from the business finance tools (`get_finance_overview` / `list_products`),
  never from the admin page.
- Explicitly deferred by the owner: real Stripe payments, paid-plan billing,
  public launch.

## Quickstart (local)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# Owner access on a private deployment: put your email in the admin list
export QUANTVENUE_ADMIN_EMAILS=you@example.com
export QUANTVENUE_PRIVATE_MODE=true        # optional — private is the default
export QUANTVENUE_SECRET_KEY=change-me     # optional in dev, required in prod

python -m server                            # http://0.0.0.0:3000
```

Then visit `/signup` — with your email in `QUANTVENUE_ADMIN_EMAILS` you can
register the owner account even while signups are otherwise blocked. Or create
accounts headlessly:

```bash
python -m server.cli create-user you@example.com 'strong-password' --admin
python -m server.cli promote you@example.com
```

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `QUANTVENUE_PRIVATE_MODE` | `true` (fail-closed) | Private: owner/admin-only, no public signups, no unauthenticated marketplace data |
| `QUANTVENUE_ADMIN_EMAILS` | _(empty)_ | Comma-separated owner/admin emails |
| `QUANTVENUE_SECRET_KEY` | ephemeral (dev) | Session signing key — set in production |
| `QUANTVENUE_DB_PATH` | `$QUANTVENUE_DATA_DIR/quantvenue.db` | SQLite database file |
| `QUANTVENUE_DATA_DIR` | `./data` | Persistent data root (volume mount) |
| `PORT` | `3000` | HTTP port |

Anything other than an explicit false value (`false/0/no/off/public/disabled`)
for `QUANTVENUE_PRIVATE_MODE` — including unset or garbage — means **private**.

## Platform surface

- **Marketplace:** listings, search/browse, categories, featured — `GET /api/bots`,
  `GET /api/bots/{slug}`, `/`, `/bot/{slug}`
- **Accounts:** signup/signin/sessions, profile & password management — `/signin`,
  `/signup`, `/account`
- **Payments (plumbing):** `GET /api/checkout/{slug}` redirects to the listing's
  stored Stripe payment link (409 when none is stored);
  `POST /api/checkout/confirm/{ref}` + `/checkout/confirm/{ref}` confirm plumbing
- **Subscriptions & licensing:** `/account/subscriptions`, licence keys,
  `/account/my-bots`
- **Reviews:** moderated ratings/reviews on bot pages
- **Developer pages:** `/developers`, `/developers/onboard`, studio at `/dev`
- **Administration:** `/admin` — users, listing moderation, review moderation,
  orders, plumbing-only finance overview
- **Ops:** `GET /health` (public), `python -m server.cli`

## Tests

```bash
.venv/bin/python -m pytest -q
```

## Docs

- `DEPLOYMENT.md` — production deployment, volumes, upgrade-in-place releases
- `server/legacy/README.md` — trading-engine isolation policy + migration notes

## Migration note (2026-09-23)

This repository was migrated from another development environment. The
migration delivered only the original FastAPI website prototype (15 commits,
`2bf2228..79d1831`) — the marketplace backbone described in earlier business-plan
versions (accounts/checkout/admin, "82 tests", PR #5/#6) is not present in this
repository's history or on GitHub and was rebuilt here against the plan's
documented API contract (`/api/bots`, `/api/bots/{slug}`, `/api/checkout/{slug}`,
`server/legacy` isolation). The broken/truncated `web/index.html` and the dead
`web/index. html` (space in filename, duplicated document) were replaced by the
template-based site in `templates/`.
