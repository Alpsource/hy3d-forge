"""Entry point: `hy3dforge serve`."""

from __future__ import annotations

import argparse
import logging

import uvicorn

from .api import create_app
from .config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="hy3dforge")
    parser.add_argument("command", choices=["serve"], nargs="?", default="serve")
    parser.add_argument("-c", "--config", default=None, help="path to config.yaml")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    settings = load_settings(args.config)
    uvicorn.run(
        create_app(settings),
        host=args.host or settings.host,
        port=args.port or settings.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
