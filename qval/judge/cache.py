"""File-backed judge cache (F-12).

The judge verdict for a given (model, prompt, response) triple is deterministic
enough to cache — the same borderline case recurring across runs should not
re-spend an API call. The key folds in the judge model so swapping models
invalidates naturally.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class JudgeCache:
    """A tiny JSON-file cache of judge verdicts, keyed by content hash."""

    def __init__(self, path):
        self.path = Path(path)
        self._data: dict[str, dict] = {}
        if self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}   # a corrupt cache is rebuilt, never fatal

    @staticmethod
    def key(model: str, prompt: str, response: str) -> str:
        h = hashlib.sha256()
        h.update(model.encode("utf-8"))
        h.update(b"\x00")
        h.update(prompt.encode("utf-8"))
        h.update(b"\x00")
        h.update(response.encode("utf-8"))
        return h.hexdigest()

    def get(self, key: str) -> dict | None:
        return self._data.get(key)

    def set(self, key: str, verdict: dict) -> None:
        self._data[key] = verdict

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
