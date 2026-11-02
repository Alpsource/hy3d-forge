"""Entry point: `hy3dforge serve`."""

from __future__ import annotations

import argparse
import logging

import uvicorn
import yaml

from . import __version__
from .api import create_app
from .bootstrap import setup
from .config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="hy3dforge")
    parser.add_argument("--version", action="version",
                        version=f"hy3dforge {__version__}")
    parser.add_argument("command", choices=["serve", "setup"], nargs="?", default="serve")
    parser.add_argument("-c", "--config", default=None, help="path to config.yaml")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--backend", action="append", dest="backends",
                        help="setup: only this backend (repeatable)")
    parser.add_argument("--accept-licenses", action="store_true",
                        help="setup: accept the backends' third-party licences without "
                             "prompting, for a scripted install")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        settings = load_settings(args.config)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as error:
        # A missing or malformed config is the ordinary first-run mistake, not a bug. A
        # traceback buries the one sentence that says what to do about it.
        raise SystemExit(f"hy3dforge: {error}")

    if args.command == "setup":
        raise SystemExit(setup(settings, args.backends, args.accept_licenses))

    if args.host:
        settings.host = args.host
    try:
        settings.check_exposure()
    except ValueError as error:
        raise SystemExit(f"hy3dforge: {error}")
    if not settings.auth_enabled:
        logging.getLogger(__name__).warning(
            "no api_keys configured - the API is unauthenticated (fine on localhost)")
    uvicorn.run(
        create_app(settings),
        host=args.host or settings.host,
        port=args.port or settings.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
