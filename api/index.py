"""Vercel entrypoint.

Vercel's Python runtime looks for a module-level ASGI app; `vercel.json` routes
every path here. Local development does not use this file -- Docker runs
`uvicorn app.main:app` directly.

`vercel.json` pins `"regions": ["cdg1"]` -- Paris -- and the reason lives here
because JSON has no comments and Vercel's schema rejects any key it does not
recognise, including a `"//"` used as one.

The reason: the Supabase project is in eu-west-3, also Paris. Every lobby
mutation is two Postgres round trips (`lobby_acquire`, then `lobby_release`)
plus a Realtime publish, so the distance between this function and the database
is paid three times per move. Vercel's default of iad1 put the Atlantic in the
middle of each one.
"""

from app.main import app

__all__ = ["app"]
