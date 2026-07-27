"""Entry point for `python -m tools.ingest`. See `cli.py` for the flags."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
