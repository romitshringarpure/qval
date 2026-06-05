"""Canonical run.json read/write helpers (F-03).

The thin io layer F-01 deferred to the first importer. Importers (F-03
Promptfoo, F-09 DeepEval) write a ``CanonicalRun`` to disk via
``save_canonical``; the gate (F-04) and reports (F-05) read it back via
``load_canonical``. One place owns the on-disk JSON shape.
"""
from __future__ import annotations

import json
from pathlib import Path

from .schema import CanonicalRun


def save_canonical(run: CanonicalRun, path) -> Path:
    """Serialize a CanonicalRun to a pretty-printed JSON file; return the path."""
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_canonical(path) -> CanonicalRun:
    """Load a CanonicalRun from a run.json file.

    Raises ValueError on a missing file or malformed JSON so callers can report
    a friendly error instead of leaking a raw OSError/JSONDecodeError.
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"canonical run file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}")
    return CanonicalRun.from_dict(raw)
