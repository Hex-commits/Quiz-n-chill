"""Vercel entrypoint.

Vercel's Python runtime looks for a module-level ASGI app; `vercel.json` routes
every path here. Local development does not use this file -- Docker runs
`uvicorn app.main:app` directly.
"""

from app.main import app

__all__ = ["app"]
