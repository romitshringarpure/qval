"""Per-model pricing lookup and cost computation.

A separate helper (vs. inlining in model_client) so the lookup rules have a
clean test surface and the model client stays focused on transport.

Pricing entries live in `config/model_config.json` under the `pricing` key:

    "pricing": {
      "_note": "...",
      "_priced_at": "2026-05",
      "gpt-4o-mini": {"prompt_per_1k": 0.00015, "completion_per_1k": 0.0006}
    }

Lookup rules (in order):
  1. Model slug ends with ":free" -> (0.0, "free")  (wins even if listed)
  2. Exact match in pricing dict   -> ("priced")
  3. Slug contains "/" (OpenRouter style: "openai/gpt-4o-mini"): strip
     the provider prefix and retry exact match.
  4. Miss -> warn once per model name, return (None, "unknown").
"""

from __future__ import annotations

import sys


_warned: set[str] = set()


def load_pricing(config: dict) -> dict[str, dict]:
    """Read the `pricing` block from a model config; skip `_`-prefixed keys.

    Keys starting with `_` (e.g. `_note`, `_priced_at`) are documentation
    only and must not be treated as model names.
    """
    raw = config.get("pricing") or {}
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int,
                 pricing: dict[str, dict]) -> tuple[float | None, str]:
    """Return (cost_usd, status) for a single call.

    status is one of "priced", "free", "unknown". The :free suffix short-
    circuits to $0 before pricing lookup so a misconfigured price entry on a
    free model can never bill anything.
    """
    if model.endswith(":free"):
        return 0.0, "free"

    entry = pricing.get(model)
    if entry is None and "/" in model:
        stripped = model.split("/", 1)[1]
        entry = pricing.get(stripped)

    if entry is None:
        if model not in _warned:
            _warned.add(model)
            print(f"[pricing] no entry for model {model!r}; "
                  f"cost will be reported as unknown.", file=sys.stderr)
        return None, "unknown"

    prompt_rate = float(entry.get("prompt_per_1k", 0.0))
    completion_rate = float(entry.get("completion_per_1k", 0.0))
    cost = (prompt_tokens / 1000.0) * prompt_rate \
        + (completion_tokens / 1000.0) * completion_rate
    return cost, "priced"


def reset_warnings() -> None:
    """Test-only: clear the warn-once memo between cases."""
    _warned.clear()
