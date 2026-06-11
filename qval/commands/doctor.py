"""qval doctor — validate environment and project configuration."""
from __future__ import annotations

import argparse
import importlib
import os
import sys

from qval.config import find_config_file, load_project_config, ProjectConfigError
from qval.project import find_project_root, NO_PROJECT_MESSAGE

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

# import name -> pip install name (when they differ)
DEP_INSTALL = {"yaml": "pyyaml"}


def _line(status: str, msg: str) -> None:
    print(f"[{status}] {msg}")


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser("doctor", help="Check environment and config")
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    failed = False

    # Python version (project supports >= 3.9)
    if sys.version_info >= (3, 9):
        _line(PASS, f"Python {sys.version_info.major}.{sys.version_info.minor}")
    else:
        _line(FAIL, "Python >= 3.9 required")
        failed = True

    # Dependencies
    for mod in ("openai", "yaml", "requests"):
        try:
            importlib.import_module(mod)
            _line(PASS, f"dependency '{mod}' importable")
        except ImportError:
            hint = DEP_INSTALL.get(mod, mod)
            _line(FAIL, f"dependency '{mod}' missing (pip install {hint})")
            failed = True

    # Project discovery. No project is a hard FAIL with an actionable message;
    # everything downstream depends on a resolved root (U-00).
    project = find_project_root()
    if project is None:
        _line(FAIL, NO_PROJECT_MESSAGE)
        print()
        print("doctor: one or more checks FAILED")
        return 1
    _line(PASS, f"project root: {project.root}")
    _line(PASS, f"  config dir:     {project.config_dir}")
    _line(PASS, f"  test cases dir: {project.test_cases_dir}")
    _line(PASS, f"  outputs dir:    {project.outputs_dir}")
    _line(PASS, f"  policy:         {project.policy_path}")

    # Project config. Present-but-unparseable is a FAIL and we then skip checks
    # that depend on config values.
    cfg_path = find_config_file()
    config_ok = True
    cfg: dict = {}
    if cfg_path is None:
        _line(WARN, "no qval.yaml found (run `qval init`)")
    else:
        try:
            cfg = load_project_config(cfg_path)
            _line(PASS, f"config parsed: {cfg_path}")
        except ProjectConfigError as exc:
            _line(FAIL, f"config error: {exc}")
            failed = True
            config_ok = False

    # Provider readiness
    if not config_ok:
        _line(WARN, "provider check skipped (config did not parse)")
    else:
        provider = cfg.get("provider", "mock")
        if provider == "mock":
            _line(PASS, "provider 'mock' (no API key needed)")
        elif provider == "openai":
            if os.environ.get("OPENAI_API_KEY"):
                _line(PASS, "OPENAI_API_KEY present")
            else:
                _line(FAIL, "OPENAI_API_KEY not set (required for provider 'openai')")
                failed = True
        elif provider == "http":
            target = cfg.get("target")
            if isinstance(target, dict) and target.get("url"):
                _line(PASS, f"provider 'http' target: {target['url']}")
            else:
                _line(FAIL, "provider 'http' requires a 'target' with a 'url'")
                failed = True
        else:
            _line(WARN, f"unknown provider '{provider}'")

    # Outputs dir writable
    if not config_ok:
        _line(WARN, "outputs dir check skipped (config did not parse)")
    else:
        outputs = project.outputs_dir
        try:
            outputs.mkdir(parents=True, exist_ok=True)
            probe = outputs / ".doctor_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            _line(PASS, f"outputs dir writable: {outputs}")
        except OSError as exc:
            _line(FAIL, f"outputs dir not writable: {exc}")
            failed = True

    print()
    if failed:
        print("doctor: one or more checks FAILED")
        return 1
    print("doctor: all checks passed")
    return 0
