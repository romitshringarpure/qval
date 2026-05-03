"""Time and run-id helpers.

A run id is a stable, sortable identifier we use to group every artifact
produced by a single evaluation run (logs, raw responses, evidence pack,
report). The format is `run_YYYYMMDD_HHMMSS_<8-char-hex>` so directory
listings sort chronologically and there is enough entropy to avoid
collisions if two runs start in the same second.
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone


def now_utc_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with timezone."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def generate_run_id() -> str:
    """Generate a sortable, collision-resistant run id."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(4)  # 8 hex chars
    return f"run_{stamp}_{suffix}"


def monotonic_ms() -> float:
    """Monotonic clock in milliseconds, for measuring durations."""
    return time.monotonic() * 1000.0


def elapsed_ms(start_ms: float) -> int:
    """Return integer milliseconds since the given monotonic start."""
    return int(monotonic_ms() - start_ms)
