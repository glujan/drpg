from __future__ import annotations

import functools
import html
import logging
import multiprocessing
import queue
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

    from drpg.config import Config
    from drpg.types import DownloadItem, Product

    NoneCallable = Callable[..., None]
    Decorator = Callable[[NoneCallable], NoneCallable]

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
        self._config = config
        self._api = DrpgApi(config.token)

    def sync(self) -> None:
        """Download all new, updated and not yet synced items to a sync directory."""

        logger.info("Authenticating")
        self._api.token()
        logger.info("Fetching products list")

        product_queue: multiprocessing.JoinableQueue = multiprocessing.JoinableQueue()
        item_queue: multiprocessing.JoinableQueue = multiprocessing.JoinableQueue()

        def put_to_queue(iterator):
            for product in iterator:
                product_queue.put(product)

        put_to_queue(self._api.products(1, 50, recursive=False))

        pool = ThreadPool(self._config.threads)
        fetch_products = pool.apply_async(
            self._api.products,
            (2, 50),
            {"recursive": True},
            callback=put_to_queue,
            error_callback=print,
        )
        pool.apply_async(
            self._process_products,
            (product_queue, item_queue),
            error_callback=print,
        )

        pool.starmap_async(
            self._process_item,
            ((item_queue,) for _ in range(self._config.threads - 2)),
            error_callback=print,
        )

        fetch_products.wait()
        print("fetch_products waited")
        product_queue.join()
        print("product_queue joined")
        item_queue.join()
        print("item_queue joined")
        pool.terminate()
        print("pool terminated")

        logger.info("Done!")

    def _process_products(
        self,
        product_queue: multiprocessing.JoinableQueue,
        item_queue: multiprocessing.JoinableQueue,
    ) -> None:
        while True:
            try:
                product: Product = product_queue.get(block=True, timeout=0.5)
            except queue.Empty:
                continue
            for item in product["files"]:
                item_queue.put((product, item))
            product_queue.task_done()

    #  @suppress_errors(httpx.HTTPError, PermissionError)
    def _process_item(self, item_queue: multiprocessing.JoinableQueue) -> None:
        """Prepare for and download the item to the sync directory."""
        product: Product
        item: DownloadItem
        while True:
            try:
                product, item = item_queue.get(block=True, timeout=0.5)
            except queue.Empty:
                continue

            if not self._need_download(product, item):
                item_queue.task_done()
                continue

            path = self._file_path(product, item)

            if self._config.dry_run:
                logger.info("DRY RUN - would have downloaded file: %s", path)
                item_queue.task_done()
                continue

            logger.info("Processing: %s - %s", product["name"], item["filename"])
            try:
                url_data = self._api.prepare_download_url(product["orderProductId"], item["index"])
            except self._api.PrepareDownloadUrlException:
                logger.warning(
                    "Could not download product: %s - %s",
                    product["name"],
                    item["filename"],
                )
                item_queue.task_done()
                continue  # TODO Maybe retry downloading the item?

            file_response = httpx.get(
                url_data["url"],
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "Accept-Encoding": "gzip, deflate, br",
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "*/*",
                },
            )

            if (
                self._config.validate
                and (api_checksum := _newest_checksum(item))
                and (local_checksum := md5(file_response.content).hexdigest()) != api_checksum
            ):
                logger.error(
                    "ERROR: Invalid checksum for %s - %s, skipping saving file (%s != %s))",
                    product["name"],
                    item["filename"],
                    api_checksum,
                    local_checksum,
                )
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(file_response.content)
                logger.info("Writing to %s", path)
            item_queue.task_done()

    def _need_download(self, product: Product, item: DownloadItem) -> bool:
        """Specify whether or not the item needs to be downloaded."""

        path = self._file_path(product, item)

        if not path.exists():
            logger.debug(
                "Needs download: %s - %s: local file does not exist",
                product["name"],
                item["filename"],
            )
            return True

        remote_time = datetime.fromisoformat(product["fileLastModified"]).utctimetuple()
        local_time = (
            datetime.fromtimestamp(path.stat().st_mtime) + timedelta(seconds=timezone)
        ).utctimetuple()
        if remote_time > local_time:
            logger.debug(
                "Needs download: %s - %s: local file is outdated",
                product["name"],
                item["filename"],
            )
            return True

        if (
            self._config.use_checksums
            and (checksum := _newest_checksum(item))
            and md5(path.read_bytes()).hexdigest() != checksum
        ):
            logger.debug(
                "Needs download: %s - %s: unmatching checksum",
                product["name"],
                item["filename"],
            )
            return True

        logger.info("Up to date: %s - %s", product["name"], item["filename"])
        return False

    def _file_path(self, product: Product, item: DownloadItem) -> Path:
        publishers_name = _normalize_path_part(
            product.get("publisher", {}).get("name", "Others"), self._config.compatibility_mode
        )
        product_name = _normalize_path_part(product["name"], self._config.compatibility_mode)
        item_name = _normalize_path_part(item["filename"], self._config.compatibility_mode)
        if self._config.omit_publisher:
            return self._config.library_path / product_name / item_name
        else:
            return self._config.library_path / publishers_name / product_name / item_name


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
        part = PathNormalizer.normalize_drivethrurpg_compatible(part)
    else:
        part = PathNormalizer.normalize(part)
    return part


def _newest_checksum(item: DownloadItem) -> str | None:
    return max(
        item["checksums"] or [],
        default={"checksum": None},
        key=lambda s: datetime.fromisoformat(s["checksumDate"]),
    )["checksum"]


class PathNormalizer:
    separator_drpg = " - "
    multiple_drpg_separators = f"({separator_drpg})+"
    multiple_whitespaces = re.compile(r"\s+")
    non_standard_characters = re.compile(r"[^a-zA-Z0-9.\s]")

    @classmethod
    def normalize_drivethrurpg_compatible(cls, part: str) -> str:
        separator = "_"
        part = re.sub(cls.non_standard_characters, separator, part)
        part = re.sub(cls.multiple_whitespaces, " ", part)
        return part

    @classmethod
    def normalize(cls, part: str) -> str:
        separator = PathNormalizer.separator_drpg
        part = html.unescape(part)
        part = re.sub(r'[<>:"/\\|?*]', separator, part).strip(separator)
        part = re.sub(PathNormalizer.multiple_drpg_separators, separator, part)
        part = re.sub(PathNormalizer.multiple_whitespaces, " ", part)
        return part
