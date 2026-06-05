"""Unit tests for cost + latency observability (B.1).

Covers pricing lookup, mock determinism, percentile aggregation, and the
end-to-end smoke that summary fields are populated.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qval.engine import pricing as pricing_mod  # noqa: E402
from qval.engine.model_client import MockClient  # noqa: E402
from qval.engine.test_runner import _latency_percentiles  # noqa: E402


PRICING = {
    "gpt-4o-mini": {"prompt_per_1k": 0.00015, "completion_per_1k": 0.0006},
    "openai/gpt-oss-20b:free": {"prompt_per_1k": 0.0, "completion_per_1k": 0.0},
}


# ---------------------------------------------------------------------------
# pricing.compute_cost
# ---------------------------------------------------------------------------

def test_cost_plain_slug():
    pricing_mod.reset_warnings()
    cost, status = pricing_mod.compute_cost("gpt-4o-mini", 1000, 500, PRICING)
    assert status == "priced"
    assert abs(cost - (0.00015 + 0.0003)) < 1e-12


def test_cost_openrouter_slug_strips_prefix():
    pricing_mod.reset_warnings()
    cost, status = pricing_mod.compute_cost(
        "openai/gpt-4o-mini", 1000, 500, PRICING,
    )
    assert status == "priced"
    assert abs(cost - (0.00015 + 0.0003)) < 1e-12


def test_cost_free_suffix_wins_even_if_entry_present():
    pricing_mod.reset_warnings()
    cost, status = pricing_mod.compute_cost(
        "openai/gpt-oss-20b:free", 999, 999, PRICING,
    )
    assert status == "free"
    assert cost == 0.0


def test_cost_unknown_model_warns_once(capsys):
    pricing_mod.reset_warnings()
    cost1, status1 = pricing_mod.compute_cost("made-up", 100, 100, {})
    cost2, status2 = pricing_mod.compute_cost("made-up", 100, 100, {})
    assert (cost1, status1) == (None, "unknown")
    assert (cost2, status2) == (None, "unknown")
    captured = capsys.readouterr()
    assert captured.err.count("no entry for model 'made-up'") == 1


# ---------------------------------------------------------------------------
# Mock token determinism
# ---------------------------------------------------------------------------

def test_mock_tokens_deterministic():
    a = MockClient(seed=42)
    b = MockClient(seed=42)
    ra = a.complete("Hello there general kenobi")
    rb = b.complete("Hello there general kenobi")
    assert ra.prompt_tokens == rb.prompt_tokens
    assert ra.completion_tokens == rb.completion_tokens
    assert ra.cost_usd == 0.0 == rb.cost_usd


# ---------------------------------------------------------------------------
# Latency percentiles
# ---------------------------------------------------------------------------

def test_percentiles_known_list():
    p50, p95, p99 = _latency_percentiles(list(range(1, 101)))
    # statistics.quantiles(n=100, method="inclusive") on 1..100 yields whole
    # numbers at indices 49 / 94 / 98 -> P50=50, P95=95, P99=99.
    assert (p50, p95, p99) == (50, 95, 99)


def test_percentiles_small_n_falls_back_to_max():
    p50, p95, p99 = _latency_percentiles([120, 50, 80])
    assert p50 == p95 == p99 == 120


def test_percentiles_empty():
    assert _latency_percentiles([]) == (0, 0, 0)


# ---------------------------------------------------------------------------
# End-to-end: summary fields populated under mock
# ---------------------------------------------------------------------------

def test_summary_token_totals_under_mock():
    from qval.main import main
    from qval.utils.file_loader import OUTPUTS_DIR
    import json

    exit_code = main([
        "--mock", "--suite", "instruction_following", "--limit", "3",
    ])
    assert exit_code in (0, 1)

    evidence_root = OUTPUTS_DIR / "evidence"
    latest = sorted([p for p in evidence_root.iterdir() if p.is_dir()])[-1]
    summary = json.loads((latest / "summary.json").read_text(encoding="utf-8"))

    assert summary["total_tokens"] > 0
    assert summary["total_cost_usd"] == 0.0
    assert summary["cost_complete"] is True
    assert "p95_latency_ms" in summary
