"""Policy-as-code: build a ``GateThresholds`` from a ``policy.yaml`` (F-06).

The gate decision engine (F-04) was written against ``GateThresholds`` as the
seam: built-in defaults today, a policy file tomorrow. F-06 fills that seam. A
``policy.yaml`` lets a team version its release rules in git — reviewed,
diffable, audited — instead of hard-coding thresholds or passing CLI flags.

Schema (all keys optional; an empty/absent policy falls back to built-in rules)::

    version: "1.0"               # stamped into Decision.policy_version
    release_policy:
      block_on:                  # NEW failures at these severities -> NO-GO
        - severity: critical
        - severity: high
      critical_floor: true       # any current critical failure -> NO-GO
      pass_rate_floor: 0.90       # current pass-rate below this -> NO-GO
      require_review:            # failures here -> CONDITIONAL-GO (sign-off)
        - severity: high

The loader is strict about *shape* (wrong types raise ``PolicyError``) but
lenient about *omission* (missing keys take the built-in default), so a partial
policy is valid and a malformed one fails loudly instead of mis-gating.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from qval.canonical import ALL_SEVERITIES
from .decision import GateThresholds

# Project-root policy filenames, checked in order (mirrors config.CONFIG_NAMES).
POLICY_NAMES = ("policy.yaml", "policy.yml")


class PolicyError(Exception):
    """Raised when a policy file is missing, unparseable, or malformed."""


@dataclass
class LoadedPolicy:
    """A policy file resolved into engine inputs."""

    thresholds: GateThresholds
    version: str                 # provenance stamp for Decision.policy_version


def load_policy(path) -> LoadedPolicy:
    """Read and validate a ``policy.yaml`` into a :class:`LoadedPolicy`."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PolicyError(f"policy file not found: {path}")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyError(f"could not parse {path}: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise PolicyError(
            f"policy in {path} must be a mapping, got {type(raw).__name__}"
        )
    return _build(raw, _stamp(raw, text))


def discover_policy(start: Path | None = None) -> Path | None:
    """Find a ``policy.yaml`` at/above ``start`` (default cwd), or None.

    Walks up like project-config discovery so ``qval gate`` picks up a repo's
    policy automatically, without a flag, when one exists.
    """
    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        for name in POLICY_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


# --- internals --------------------------------------------------------------

def _build(raw: dict, version: str) -> LoadedPolicy:
    policy = raw.get("release_policy", {})
    if not isinstance(policy, dict):
        raise PolicyError(
            f"'release_policy' must be a mapping, got {type(policy).__name__}"
        )

    kwargs: dict = {}

    block = _severities(policy.get("block_on"), "block_on")
    if block is not None:
        kwargs["block_new_severities"] = block

    review = _severities(policy.get("require_review"), "require_review")
    if review is not None:
        kwargs["require_review_severities"] = review

    floor = policy.get("pass_rate_floor")
    if floor is not None:
        if not isinstance(floor, (int, float)) or isinstance(floor, bool):
            raise PolicyError(f"'pass_rate_floor' must be a number, got {floor!r}")
        if not 0.0 <= float(floor) <= 1.0:
            raise PolicyError(f"'pass_rate_floor' must be between 0 and 1, got {floor}")
        kwargs["min_pass_rate"] = float(floor)

    if "critical_floor" in policy:
        cf = policy["critical_floor"]
        if not isinstance(cf, bool):
            raise PolicyError(f"'critical_floor' must be a boolean, got {cf!r}")
        kwargs["critical_floor"] = cf

    return LoadedPolicy(thresholds=GateThresholds(**kwargs), version=version)


def _severities(entries, key: str) -> frozenset[str] | None:
    """Parse a ``[{severity: critical}, ...]`` list into a severity set.

    Returns None when the key is absent (so the GateThresholds default stands).
    An empty list is meaningful (disables that rule) and yields an empty set.
    """
    if entries is None:
        return None
    if not isinstance(entries, list):
        raise PolicyError(f"'{key}' must be a list, got {type(entries).__name__}")
    out: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or "severity" not in entry:
            raise PolicyError(f"'{key}' entries must be mappings with a 'severity' key")
        sev = entry["severity"]
        if sev not in ALL_SEVERITIES:
            raise PolicyError(
                f"'{key}' has unknown severity {sev!r}; choose from {ALL_SEVERITIES}"
            )
        out.add(sev)
    return frozenset(out)


def _stamp(raw: dict, text: str) -> str:
    """Provenance string for the verdict: explicit version, else a content hash."""
    version = raw.get("version")
    if version is not None:
        return f"policy:{version}"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"policy:sha256:{digest}"
