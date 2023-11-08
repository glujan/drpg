from __future__ import annotations

import functools
import html
import logging
import re
from datetime import datetime, timedelta
from hashlib import md5
from multiprocessing.pool import ThreadPool
from time import timezone
from typing import TYPE_CHECKING

import httpx

from drpg.api import DrpgApi

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path
    from typing import Any, Callable

    from drpg.api import DownloadItem, Product
    from drpg.config import Config

    NoneCallable = Callable[..., None]
    Decorator = Callable[[NoneCallable], NoneCallable]

_checksum_time_format = "%Y-%m-%d %H:%M:%S"
logger = logging.getLogger("drpg")


def suppress_errors(*errors: type[Exception]) -> Decorator:
    """Silence but log provided errors."""

    def decorator(func: NoneCallable) -> NoneCallable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> None:
            try:
                return func(*args, **kwargs)
            except errors as e:
                logger.exception(e)

        return wrapper

    return decorator


class DrpgSync:
    """High level DriveThruRPG client that syncs products from a customer's library."""

    def __init__(self, config: Config) -> None:
        self._use_checksums = config.use_checksums
        self._library_path = config.library_path
        self._dry_run = config.dry_run
        self._compatibility_mode = config.compatibility_mode
        self._api = DrpgApi(config.token)

    def sync(self) -> None:
        """Download all new, updated and not yet synced items to a sync directory."""

        self._api.token()
        process_item_args = (
            (product, item)
            for product in self._api.customer_products()
            for item in product["files"]
            if self._need_download(product, item)
        )

        with ThreadPool(5) as pool:
            pool.starmap(self._process_item, process_item_args)
        logger.info("Done!")

    @suppress_errors(httpx.HTTPError, PermissionError)
    def _process_item(self, product: Product, item: DownloadItem) -> None:
        """Prepare for and download the item to the sync directory."""

        path = self._file_path(product, item)

        if self._dry_run:
            logger.info("DRY RUN - would have downloaded file: %s", path)
        else:
            logger.info("Processing: %s - %s", product["products_name"], item["filename"])

            try:
                url_data = self._api.file_task(product["products_id"], item["bundle_id"])
            except self._api.FileTaskException:
                logger.warning(
                    "Could not download product: %s - %s",
                    product["products_name"],
                    item["filename"],
                )
                return

            file_response = httpx.get(url_data["download_url"], timeout=30.0, follow_redirects=True)

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(file_response.content)

    def _need_download(self, product: Product, item: DownloadItem) -> bool:
        """Specify whether or not the item needs to be downloaded."""

        path = self._file_path(product, item)

        if not path.exists():
            return True

        remote_time = datetime.fromisoformat(item["last_modified"]).utctimetuple()
        local_time = (
            datetime.fromtimestamp(path.stat().st_mtime) + timedelta(seconds=timezone)
        ).utctimetuple()
        if remote_time > local_time:
            return True

        if (
            self._use_checksums
            and (checksum := _newest_checksum(item))
            and md5(path.read_bytes()).hexdigest() != checksum
        ):
            return True

        logger.debug("Up to date: %s - %s", product["products_name"], item["filename"])
        return False

    def _file_path(self, product: Product, item: DownloadItem) -> Path:
        publishers_name = _normalize_path_part(
            product.get("publishers_name", "Others"), self._compatibility_mode
        )
        product_name = _normalize_path_part(product["products_name"], self._compatibility_mode)
        item_name = _normalize_path_part(item["filename"], self._compatibility_mode)
        return self._library_path / publishers_name / product_name / item_name


def _normalize_path_part(part: str, compatibility_mode: bool) -> str:
    """
    Strip out unwanted characters in parts of the path to the downloaded file representing
    publisher's name, product name, and item name.
    """

    # There are two algorithms for normalizing names. One is the drpg way, and the other
    # is the DriveThruRPG way.
    #
    # Normalization algorithm for DriveThruRPG's client:
    # 1. Replace any characters that are not alphanumeric, period, or space with "_"
    # 2. Replace repeated whitespace with a single space
    # # NOTE: I don't know for sure that step 2 is how their client handles it. I'm guessing.
    #
    # Normalization algorithm for drpg:
    # 1. Unescape any HTML-escaped characters (for example, convert &nbsp; to a space)
    # 2. Replace any of the characters <>:"/\|?* with " - "
    # 3. Replace any repeated " - " separators with a single " - "
    # 4. Replace repeated whitespace with a single space
    #
    # For background, this explains what characters are not allowed in filenames on Windows:
    # https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file#naming-conventions
    # Since Windows is the lowest common denominator, we use its restrictions on all platforms.

    if compatibility_mode:
        separator = "_"
        part = re.sub(r"[^a-zA-Z0-9.\s]", separator, part)
        part = re.sub(r"\s+", " ", part)
    else:
        separator = " - "
        part = html.unescape(part)
        part = re.sub(r'[<>:"/\\|?*]', separator, part).strip(separator)
        part = re.sub(f"({separator})+", separator, part)
        part = re.sub(r"\s+", " ", part)
    return part


def _newest_checksum(item: DownloadItem) -> str | None:
    return max(
        item["checksums"],
        default={"checksum": None},
        key=lambda s: datetime.strptime(s["checksum_date"], _checksum_time_format),
    )["checksum"]
