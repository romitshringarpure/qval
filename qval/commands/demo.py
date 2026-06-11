"""`qval demo` - run the intentionally flawed local support bot."""

from __future__ import annotations

import argparse

from qval.demo import bot


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "demo",
        help="Start the local intentionally flawed support-bot demo target.",
        description="Start the local intentionally flawed support-bot demo target.",
    )
    sub.add_argument(
        "--port",
        type=int,
        default=bot.DEFAULT_PORT,
        help=f"Local port to bind on 127.0.0.1. Default: {bot.DEFAULT_PORT}.",
    )
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    port = int(args.port)
    server = bot.make_server(port=port)
    url = f"http://{bot.HOST}:{port}/chat"

    bot.print_banner(port)
    print("")
    print("In another terminal, run:")
    print(f"  qval run --suite support_bot_starter --target-url {url}")
    print("")
    print("Press Ctrl-C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down qval demo support bot.")
    finally:
        server.server_close()
    return 0
