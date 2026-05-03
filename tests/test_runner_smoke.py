"""End-to-end smoke test for the framework using the offline mock provider.

Why a smoke test? Because a clean clone of this repo should be able to run
the entire pipeline without an API key. If this test fails, the portfolio
demo is broken — and that is the most important thing for a clean clone
to verify.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.main import main  # noqa: E402
from src.utils.file_loader import OUTPUTS_DIR  # noqa: E402


def test_mock_run_produces_complete_evidence_pack(tmp_path):
    # Run a small mock evaluation across all suites with a tight cap so the
    # smoke test stays fast.
    exit_code = main(["--mock", "--suite", "all", "--limit", "3"])
    # Mock is deterministic but does sometimes flip a "force_bad" output for
    # privacy prompts; either exit code 0 or 1 is acceptable here. We only
    # care that the pipeline did not crash.
    assert exit_code in (0, 1)

    # Find the most recent evidence dir.
    evidence_root = OUTPUTS_DIR / "evidence"
    runs = sorted([p for p in evidence_root.iterdir() if p.is_dir()])
    assert runs, "no evidence pack was created"
    latest = runs[-1]

    expected_files = [
        "raw_prompts.json",
        "raw_responses.json",
        "scored_results.json",
        "manual_review_items.csv",
        "summary.json",
        "summary_report.md",
        "summary_report.html",
    ]
    for name in expected_files:
        assert (latest / name).exists(), f"missing evidence file: {name}"


def test_mock_run_single_suite():
    exit_code = main(["--mock", "--suite", "instruction_following", "--limit", "2"])
    assert exit_code == 0
