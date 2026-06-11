"""`qval ui` - launch the local-first web console."""

from __future__ import annotations

import argparse


INSTALL_HINT = "pip install qval[ui]"


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "ui",
        help="Start the local Qval web console.",
        description="Start the local-first Qval web console on 127.0.0.1.",
    )
    sub.add_argument(
        "--port",
        type=int,
        default=8642,
        help="Port to bind on 127.0.0.1. Default: 8642.",
    )
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    try:
        create_app = _load_create_app()
    except RuntimeError as exc:
        print(exc)
        return 1

    app = create_app()
    app.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


def _load_create_app():
    try:
        from qval.ui.server import create_app
    except ModuleNotFoundError as exc:
        if exc.name == "flask":
            raise RuntimeError(INSTALL_HINT) from exc
        raise
    except RuntimeError as exc:
        if INSTALL_HINT in str(exc):
            raise
        raise
    return create_app
