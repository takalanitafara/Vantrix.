# server/legacy — isolated, never imported

Per the business plan, any trading-engine code (Quantora / MT5 / Deriv /
strategy / risk-engine code) is **isolated here** and is **never imported by
the default app**. QuantVenue is a marketplace platform layer only: listing,
accounts, checkout, licensing, reviews, developer pages, administration.

Scope reminder — this package must never contain or connect to:

- trading logic, paper/demo/live trading
- broker connections, MT5/Deriv execution
- market scanners, strategy engines, risk engines

## Migration note (2026-09-23)

The repository history (15 commits, from `2bf2228` to `79d1831`) contains only
the FastAPI website prototype — no trading-engine code was ever committed here.
This package therefore exists as the designated isolation point: if the
original prototype's embedded Quantora/MT5/Deriv/risk code is recovered from
another development environment, it lands in this directory and stays
unimported by `server.*` modules.
