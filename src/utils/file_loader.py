"""I/O helpers for loading configs and test cases and writing artifacts.

Centralizing file I/O keeps the runner small and makes it easy to swap
storage later (e.g. S3, a database) without touching domain logic.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
TEST_CASES_DIR = PROJECT_ROOT / "test_cases"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


SUITE_FILE_MAP = {
    "instruction_following": "instruction_following_tests.json",
    "bias": "bias_tests.json",
    "toxicity": "toxicity_tests.json",
    "hallucination": "hallucination_tests.json",
    "safety": "safety_tests.json",
    "robustness": "robustness_tests.json",
    "privacy": "privacy_tests.json",
}

ALL_SUITES = list(SUITE_FILE_MAP.keys())


def load_json(path: Path) -> Any:
    """Read and parse a UTF-8 JSON file."""
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> None:
    """Write `data` as pretty-printed UTF-8 JSON, creating parents if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(text)


def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_model_config() -> dict:
    return load_json(CONFIG_DIR / "model_config.json")


def load_scoring_config() -> dict:
    return load_json(CONFIG_DIR / "scoring_config.json")


def load_risk_matrix() -> dict:
    return load_json(CONFIG_DIR / "risk_matrix.json")


def load_test_suite(suite: str) -> list[dict]:
    """Load a single suite of test cases by name."""
    if suite not in SUITE_FILE_MAP:
        raise ValueError(f"Unknown suite: {suite!r}. Valid: {ALL_SUITES}")
    path = TEST_CASES_DIR / SUITE_FILE_MAP[suite]
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"Test suite file {path} must contain a JSON list")
    return data


def load_all_suites() -> list[dict]:
    """Load every suite, in deterministic order."""
    cases: list[dict] = []
    for suite in ALL_SUITES:
        cases.extend(load_test_suite(suite))
    return cases


def get_env(name: str, default: str | None = None) -> str | None:
    """Read an environment variable with optional default. We never log values."""
    return os.environ.get(name, default)
