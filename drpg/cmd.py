from __future__ import annotations

import argparse
import configparser
import logging
import os.path
import platform
import signal
import sys
from os import environ
from pathlib import Path
from traceback import format_exception
from typing import TYPE_CHECKING

from drpg import DrpgSync
from drpg.config import Config

if TYPE_CHECKING:  # pragma: no cover
    from types import FrameType, TracebackType

    CliArgs = list[str]

__all__ = ["run"]


def run() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    sys.excepthook = _excepthook
    config = _parse_cli()
    _setup_logger(config.log_level)

    DrpgSync(config).sync()


def _parse_cli(args: CliArgs | None = None) -> Config:
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
        default=environ.get("DRPG_LIBRARY_PATH", _default_dir()),
        type=Path,
        help=f"Path to your downloads. Defaults to {_default_dir()}",
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=environ.get("DRPG_DRY_RUN", "false").lower() == "true",
        help="Determine what should be downloaded, but do not download it. Defaults to false",
    )
    parser.add_argument(
        "--compatibility-mode",
        action="store_true",
        default=environ.get("DRPG_COMPATIBILITY_MODE", "false").lower() == "true",
        help="Name files and directories the way that DriveThruRPG's client app does.",
    )

    return parser.parse_args(args, namespace=Config())


def _default_dir() -> Path:
    os_name = platform.system()
    if os_name == "Linux":
        xdg_config = Path(environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
        try:
            with open(xdg_config / "user-dirs.dirs") as f:
                raw_config = "[xdg]\n" + f.read().replace('"', "")
            config = configparser.ConfigParser()
            config.read_string(raw_config)
            raw_dir = config["xdg"]["xdg_documents_dir"]
        except (FileNotFoundError, KeyError):
            raw_dir = "$HOME/Documents"
        finally:
            dir = Path(os.path.expandvars(raw_dir))
    elif os_name == "Windows":
        dir = Path.home()
    else:
        dir = Path.cwd()
    return dir / "DRPG"


def _setup_logger(level_name: str) -> None:
    level = logging.getLevelName(level_name)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    logging.basicConfig(
        format="%(message)s",
        handlers=[handler],
        level=level,
    )


def _handle_signal(sig: int, frame: FrameType | None) -> None:
    logging.getLogger("drpg").info("Stopping...")
    sys.exit(0)


def _excepthook(
    exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
) -> None:
    logger = logging.getLogger("drpg")
    logger.error("Unexpected error occurred, stopping!")
    logger.debug("".join(format_exception(exc_type, exc, tb)))
