"""Turning a stored Commons file name into something a browser can load.

`Special:FilePath` resolves a bare file name to the image and takes a width,
which is why the *name* is what the database stores. Commons thumbnails live at
a hash-derived path (`/thumb/8/83/...`) that cannot be computed from the name,
so storing a URL would mean storing something we could not regenerate.

Pictures are loaded straight from Commons rather than through this API. An
earlier version proxied them behind an opaque `/lobbies/{code}/images/{id}`
redirect, because a file name like `Pont Neuf Paris.jpg` names both the answer
and the category it belongs to -- but that only defends against a player who
opens the network tab to win a party game, and it cost a request through a
serverless function for every picture on every board. Commons has a CDN; we do
not.

What still matters, and is not about cheating, is that nothing *rendered on
screen* gives the answer away: the item's label and the image credit are both
withheld until the answer is placed. See `_published_image` in `lobbies.py`.
"""

from __future__ import annotations

import urllib.parse

# Wide enough to read a photograph on a laptop, small enough that ten of them
# are not a megabyte. Commons renders and caches this size for us.
THUMB_WIDTH = 640


def commons_url(file: str, *, width: int = THUMB_WIDTH) -> str:
    """A directly loadable URL for a Commons file name."""
    quoted = urllib.parse.quote(file.replace(" ", "_"), safe="")
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quoted}?width={width}"
