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
    # Anchor all path resolution at the discovered project root (U-00) so the
    # console serves the user's project, not the repo checkout fallback.
    from qval.project import find_project_root, set_active_project

    project = find_project_root()
    if project is not None:
        set_active_project(project)

    try:
        create_app = _load_create_app()
    except RuntimeError as exc:
        print(exc)
        return 1

    app = create_app()
    print(f"qval console: http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
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
