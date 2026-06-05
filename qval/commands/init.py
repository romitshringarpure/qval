"""qval init — scaffold a new Qval project (config, policy, example suite)."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# (template relative path -> destination relative path)
SCAFFOLD = [
    ("qval.yaml", "qval.yaml"),
    ("policy.yaml", "policy.yaml"),
    ("suites/example.json", "suites/example.json"),
]


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser("init", help="Scaffold a new Qval project")
    sub.add_argument("--path", default=".", help="Target directory (default: .)")
    sub.add_argument("--force", action="store_true", help="Overwrite existing files")
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    target = Path(args.path).resolve()
    planned = [(TEMPLATES_DIR / src, target / dst) for src, dst in SCAFFOLD]

    if not args.force:
        clashes = [str(dst) for _, dst in planned if dst.exists()]
        if clashes:
            print("Refusing to overwrite existing files (use --force):")
            for c in clashes:
                print(f"  {c}")
            return 1

    for src, dst in planned:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        print(f"created {dst}")

    print("\nDone. Next: `qval doctor`, then `qval run --mock`.")
    return 0
