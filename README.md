# Vantrix

A FastAPI-served trading-platform **prototype**, not a functioning trading system.
Currently implements a responsive landing page and `GET /health`. There is no
broker connection, bot execution, authentication, market feed, position tracking,
or profit calculation. Never use this version to manage real funds.

## Run locally (Python 3.11+)

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

Open http://localhost:8000. The server binds to `0.0.0.0` and honors `PORT`
(default `8000`). The frontend uses the same origin for API calls.

## Checks

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m pip check
node --test tests/health-ui.test.cjs
```

Node 22 is used for frontend unit tests; Node is not needed to serve the app.
GitHub Actions is configured to run the checks on Python 3.11, 3.12, and 3.13.
Direct dependencies are pinned; transitive dependencies are not fully locked.

## Docker

```sh
docker build -t vantrix .
docker run --rm -p 8000:8000 vantrix
# Custom port:
docker run --rm -e PORT=8080 -p 8080:8080 vantrix
```

The image runs as a non-root user and copies only runtime application files.

## Repository review

### Issues fixed

- The served homepage was truncated inside its style block, with no page body.
  Restored a complete document using the existing design as a starting point.
- Invalid CSS included `box-sizing:box-sizing`, `72tx`, `70tx`, a malformed
  `clamp()`, extra gradient parentheses, `crid-template-columns`, `bax-width`,
  a broken color declaration, and invalid flex/font declarations.
- Removed the obsolete `web/index. html` file, which contained two concatenated
  HTML documents, and removed tracked Python bytecode.
- Replaced misleading static online/trading indicators with unverified/not
  connected states. The health button now validates HTTP status and response
  data, handles network/JSON/server errors, times out after five seconds, and
  always permits retry.
- Python and Docker startup now honor `PORT`, instead of always using 8000.
- Pinned runtime dependencies, removed unused `aiofiles`, and separated test
  dependencies. Added ignore rules to prevent caches, virtual environments,
  and environment files from entering future changes or Docker contexts.
- Added regression tests, CI configuration, setup instructions, accessible
  status announcements, and keyboard focus styles.

### Verification completed in the workspace

- 6 Python tests passed: homepage completeness and anchors, health response,
  unknown-route behavior, working-directory independence, and both port modes.
- 6 JavaScript unit tests passed: success, HTTP failure, invalid JSON,
  unexpected payload, network failure, and timeout handling.
- Dependency consistency (`pip check`), CSS syntax parsing, and
  `git diff --check` passed.
- Started the application and received successful live HTTP responses for
  `/` and `/health` on port 8000.

### Limits / not verified

No software review can establish that every possible error is absent. This
review did not include a real-browser visual/accessibility audit, load testing,
a production security audit, a dependency-vulnerability scan, or a Docker build
(Docker is unavailable in this workspace). Local Python testing used 3.11;
other configured versions and GitHub-hosted CI have not been run here.
Production hosting and any external integrations were not verified. `/health`
is only an application liveness response, not proof of broker connectivity or
trading readiness.
