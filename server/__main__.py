"""Run the platform: python -m server  (honours PORT, default 3000)."""

import uvicorn

from . import config

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=config.port())
