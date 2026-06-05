"""Backward-compatible entry point. Prefer the `qval` command (see qval.cli)."""
from qval.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
