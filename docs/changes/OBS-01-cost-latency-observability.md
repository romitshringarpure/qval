# OBS-01 · Cost & Latency Observability — Change Record

**Status:** ✅ Done
**Date:** 2026-06-04
**Type:** Enhancement (not a roadmap F-item)

---

## 1. What this is

Per-call token capture, USD cost computation, and latency percentiles, surfaced
through the run summary and reports. Every model call now records prompt /
completion / total tokens and a computed `cost_usd`; each run reports total
tokens, total cost, a `cost_complete` flag, and p50 / p95 / p99 latency.

## 2. Why

A QA / governance tool that cannot answer "what did this eval run cost and how
slow was it?" is incomplete. Cost and latency are first-class quality signals for
release decisions and for comparing models. Capturing them at the source (the
model client) keeps the data accurate and avoids bolt-on estimation later.

## 3. What changed (files)

| File | Change |
|------|--------|
| `src/engine/pricing.py` | **New.** `load_pricing`, `compute_cost`, `reset_warnings`. Lookup rules: `:free` → $0, exact match, OpenRouter `provider/model` prefix strip, miss → warn-once + "unknown". |
| `config/model_config.json` | Added `pricing` block (gpt-4o-mini, gpt-4o, claude-3-5-sonnet, free model). Default model set to `openai/gpt-oss-20b:free`; timeout 30→60s; retry backoff 1→2s. |
| `src/engine/schemas.py` | Token + cost fields on `ModelResponse` and `TestResult`; token, cost, and p50/p95/p99 latency fields on `RunSummary`. |
| `src/engine/model_client.py` | `OpenAIClient` captures usage tokens and computes cost (defensive getattr — free models sometimes omit the usage block). `MockClient` emits deterministic token counts and $0. |
| `src/engine/test_runner.py` | None-aware token/cost summing across primary + paired calls; per-category and run-level rollups; `cost_complete` flag; `_latency_percentiles` with honest max() fallback when N < 5. |
| `src/reports/report_generator.py` | Renders cost and latency in the report. |
| `tests/test_observability.py` | **New.** Pricing lookup, mock determinism, percentile aggregation, summary-population smoke. |
| `.env.example` | Documented `OPENAI_BASE_URL` for the OpenRouter default model. |

## 4. Design choices

- **Pricing as a separate module** — clean test surface; keeps the model client
  focused on transport.
- **`:free` short-circuits to $0** before lookup — a misconfigured price entry on
  a free model can never bill anything.
- **None propagation** — a missing token/cost stays `None` ("unknown") rather
  than silently becoming 0, so partial data is visible, not hidden.
- **`cost_complete`** — only non-errored calls without cost mark a run partial;
  an errored call legitimately has no cost.
- **Percentiles** — refuse to fabricate quantiles from < 5 samples; return max()
  across the board (honest, still non-zero).

## 5. Tests

`tests/test_observability.py` plus the existing suite — 48 tests pass.

## 6. Notes / follow-ups

- Default model is an OpenRouter slug; real (non-mock) runs need
  `OPENAI_BASE_URL` set (see `.env.example`). The OpenAI SDK reads it
  automatically.
- Pricing table is hand-maintained (`_priced_at` documents the date). Refresh
  from provider pricing pages periodically.
