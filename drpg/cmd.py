import argparse
import logging
import signal
import sys
from os import environ
from pathlib import Path

from drpg import DrpgSync

__all__ = ["run"]


def run():
    signal.signal(signal.SIGINT, _handle_signal)
    config = _parse_cli()
    _setup_logger(config.log_level)
    DrpgSync(config).sync()


def _parse_cli(args=None):
    parser = argparse.ArgumentParser(
        prog="drpg",
        description="Download and keep up to date your purchases from DriveThruRPG",
        epilog="""
            Instead of parameters you can use environment variables. Prefix
            an option with DRPG_, capitalize it and replace '-' with '_'.
            For instance '--use-checksums' becomes 'DRPG_USE_CHECKSUMS=true'.
        """,
    )
    parser.add_argument(
        "--token",
        "-t",
        required="DRPG_TOKEN" not in environ,
        help="Required. Your DriveThruRPG API token",
        default=environ.get("DRPG_TOKEN"),
    )
    parser.add_argument(
        "--library-path",
        "-p",
        default=environ.get("DRPG_LIBRARY_PATH", "repository"),
        type=Path,
        help="Path to your downloads. Defaults to './repository'",
    )
    parser.add_argument(
        "--use-checksums",
        "-c",
        action="store_true",
        default=environ.get("DRPG_USE_CHECKSUMS", "false").lower() == "true",
        help="Calculate checksums for all files. Slower but possibly more precise",
    )
    parser.add_argument(
        "--log-level",
        default=environ.get("DRPG_LOG_LEVEL", "INFO"),
        choices=[logging.getLevelName(i) for i in range(10, 60, 10)],
        help="How verbose the output should be. Defaults to 'INFO'",
    )

    return parser.parse_args(args)


def _setup_logger(level_name):
    level = logging.getLevelName(level_name)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    logging.basicConfig(
        format="%(message)s",
        handlers=[handler],
        level=level,
    )


def _handle_signal(sig, frame):
    logging.getLogger("drpg").info("Stopping...")
    sys.exit(0)
