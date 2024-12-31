from __future__ import annotations

import dataclasses
import enum
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
from typing import TYPE_CHECKING, Any

import httpx

from drpg.api import DrpgApi

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator
    from pathlib import Path
    from typing import Callable

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

        q = queue.PriorityQueue()

        for product in self._api.products(1):
            q.put(QueueItem(QueueItemType.EXTRACT_ITEMS, (product,)))

        pool = ThreadPool(self._config.threads)
        q.put(QueueItem(QueueItemType.GET_PAGE, (2,)))

        pool.starmap_async(
            self._process,
            ((q,) for _ in range(self._config.threads)),
            error_callback=print,  # TODO Add a real errback
        )

        q.join()
        pool.terminate()

        logger.info("Done!")

    def _process(self, q: queue.PriorityQueue) -> None:
        while True:
            try:
                queue_item: QueueItem = q.get(block=True, timeout=0.5)
            except queue.Empty:
                continue

            if queue_item.action == QueueItemType.GET_PAGE:
                page, *_ = queue_item.args
                products = self._api.products(page)
                product = next(products, None)
                if product:
                    q.put(QueueItem(QueueItemType.EXTRACT_ITEMS, (product,)))
                    q.put(QueueItem(QueueItemType.GET_PAGE, (page + 1,)))

                for product in products:
                    q.put(QueueItem(QueueItemType.EXTRACT_ITEMS, (product,)))

            elif queue_item.action == QueueItemType.EXTRACT_ITEMS:
                product, *_ = queue_item.args
                for item in product["files"]:
                    q.put(QueueItem(QueueItemType.PREPARE_DOWNLOAD_URL, (product, item)))
            elif queue_item.action == QueueItemType.PREPARE_DOWNLOAD_URL:
                product, item, *_ = queue_item.args
                ready, url = self._prepare_download_url(product, item)
                if ready:
                    if url is None:
                        logger.info("Skipping, not nee")
                    q.put(QueueItem(QueueItemType.DOWNLOAD, (url,)))
            elif queue_item.action == QueueItemType.DOWNLOAD:
                download_url, *_ = queue_item.args
                # TODO
            q.task_done()

    #  @suppress_errors(httpx.HTTPError, PermissionError)
    def _prepare_download_url(
        self, product: Product, item: DownloadItem
    ) -> tuple[bool, str | None]:
        """Prepare for and download the item to the sync directory."""
        if not self._need_download(product, item):
            return True, None

        path = self._file_path(product, item)

        if self._config.dry_run:
            logger.info("DRY RUN - would have downloaded file: %s", path)
            return True, None

        logger.info("Processing: %s - %s", product["name"], item["filename"])
        try:
            url_data = self._api.prepare_download_url(product["orderProductId"], item["index"])
        except self._api.PrepareDownloadUrlException:
            logger.warning(
                "Could not download product: %s - %s",
                product["name"],
                item["filename"],
            )
            return True, None  # TODO Maybe retry downloading the item?

        if url_data["status"].startswith("Preparing"):
            logger.debug("Waiting for download link for: %s - %s", product_id, item_id)
            return False, None
        return True, url_data["url"]

    def _download_from_url(self, url):
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


class QueueItemType(enum.IntEnum):
    GET_PAGE = 1
    EXTRACT_ITEMS = 2
    PREPARE_DOWNLOAD_URL = 3
    CHECK_DOWNLOAD_URL = 3
    DOWNLOAD = 4


@dataclasses.dataclass(order=True)
class QueueItem:
    action: QueueItemType
    args: tuple[Any, ...] = dataclasses.field(compare=False, default_factory=tuple)
