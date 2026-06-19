from __future__ import annotations

import functools
import html
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from hashlib import md5
from multiprocessing.pool import ThreadPool
from pathlib import Path
from time import timezone
from typing import TYPE_CHECKING

import httpx

import drpg
from drpg.api import DrpgApi

if TYPE_CHECKING:  # pragma: no cover
    from typing import Any, Callable

    from drpg.config import Config
    from drpg.types import DownloadItem, Product

    NoneCallable = Callable[..., None]
    Decorator = Callable[[NoneCallable], NoneCallable]

logger = logging.getLogger("drpg")

# Tuned for large files: 30s connect/read, but no overall transfer limit.
DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, read=30.0)

RETRYABLE_ERRORS = (httpx.RemoteProtocolError, httpx.NetworkError, httpx.ConnectError)
MAX_RETRIES = int(os.environ.get("DRPG_DOWNLOAD_RETRIES", "5"))
RETRY_DELAY_SECONDS = float(os.environ.get("DRPG_DOWNLOAD_RETRY_DELAY", "2.0"))
CHUNK_SIZE = int(os.environ.get("DRPG_DOWNLOAD_CHUNK_SIZE", "8192"))


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


class DateVersion:
    def __init__(self, raw_date_version: str):
        parts = raw_date_version.split(".")
        assert len(parts) == 3
        self.value = [int(p) for p in parts]

    def __lt__(self, other: DateVersion):
        return self.value < other.value

    def __eq__(self, other: object):
        if not isinstance(other, DateVersion):
            return False
        return self.value == other.value


class DrpgSync:
    """High level DriveThruRPG client that syncs products from a customer's library."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._api = DrpgApi(config.token)
        self._shutdown_event = threading.Event()
        self._download_client = httpx.Client(timeout=DOWNLOAD_TIMEOUT)

    def __enter__(self) -> DrpgSync:
        return self

    def __exit__(self, *args: object) -> None:
        self._download_client.close()

    GITHUB_LATEST_URL = "https://api.github.com/repos/glujan/drpg/releases/latest"

    def update_check(self):
        if self._config.do_check:
            resp = self._download_client.get(self.GITHUB_LATEST_URL)
            if not resp.is_success:
                logger.warning(
                    "Unable to check latest release, continuing: %s %s",
                    resp.status_code,
                    resp.content,
                )
                return
            try:
                data = resp.json()
                version = data["tag_name"]
                if DateVersion(drpg.__version__) < DateVersion(version):
                    logger.warning(
                        "Local version is %s, but %s has been released, so you may see issues when running the tool. Please goto https://github.com/glujan/drpg/releases for new releases",  # noqa: E501
                        drpg.__version__,
                        version,
                    )
                else:
                    logger.debug(
                        "Local version %s is greater than or equal to remote version %s",
                        drpg.__version__,
                        version,
                    )
            except Exception:
                logger.exception("Issue during version checking, continuing")

    def sync(self) -> None:
        """Download all new, updated and not yet synced items to a sync directory."""

        logger.info("Authenticating")
        self._api.token()
        logger.info("Fetching products list")
        process_item_args = (
            (product, item)
            for product in self._api.customer_products()
            for item in product["files"]
            if self._need_download(product, item)
        )

        with ThreadPool(self._config.threads) as pool:
            pool.starmap(self._process_item, process_item_args)
        logger.info("Done!")

    @suppress_errors(httpx.HTTPError, PermissionError)
    def _process_item(self, product: Product, item: DownloadItem) -> None:
        """Prepare for and download the item to the sync directory."""

        if self._shutdown_event.is_set():
            return

        path = self._file_path(product, item)

        if self._config.dry_run:
            logger.info("DRY RUN - would have downloaded file: %s", path)
        else:
            logger.info("Processing: %s - %s", product["name"], item["filename"])

            try:
                url_data = self._api.prepare_download_url(product["orderProductId"], item["index"])
            except self._api.PrepareDownloadUrlException:
                logger.warning(
                    "Could not download product: %s - %s",
                    product["name"],
                    item["filename"],
                )
                return

            self._download_with_resume_and_retry(
                url_data["url"],
                path,
                product,
                item,
            )

    def _download_with_resume_and_retry(
        self,
        url: str,
        path: Path,
        product: Product,
        item: DownloadItem,
    ) -> None:
        """Stream-download a file with HTTP Range resume and retry on transient errors.

        Writes to a .part file next to the destination and renames it into place
        only after the full download completes.
        """
        part_path = _part_path_for(path)
        start_offset = _part_file_offset(part_path)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._stream_download(url, part_path, start_offset)
                _commit_download(part_path, path, product, item, self._config.validate)
                return
            except RETRYABLE_ERRORS as exc:
                start_offset = _part_file_offset(part_path)
                logger.warning(
                    "Download attempt %d/%d failed for %s - %s: %s. Resuming from %d bytes.",
                    attempt,
                    MAX_RETRIES,
                    product["name"],
                    item["filename"],
                    exc,
                    start_offset,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)
                else:
                    logger.error(
                        "Giving up on %s - %s after %d attempts",
                        product["name"],
                        item["filename"],
                        MAX_RETRIES,
                    )
                    raise

    def _stream_download(self, url: str, part_path: Path, start_offset: int) -> None:
        """Stream a (possibly resumed) download into the .part file."""
        headers = {
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
        }
        if start_offset > 0:
            headers["Range"] = f"bytes={start_offset}-"
            logger.info("Resuming download from %d bytes", start_offset)

        part_path.parent.mkdir(parents=True, exist_ok=True)
        with self._download_client.stream(
            "GET",
            url,
            follow_redirects=True,
            headers=headers,
        ) as response:
            response.raise_for_status()
            
            # Check if server honored our Range request
            content_range = response.headers.get("content-range", "")
            content_length = response.headers.get("content-length")
            
            # If we requested a range but got a full response, server doesn't support Range
            if start_offset > 0 and response.status_code == 200 and content_length:
                try:
                    full_size = int(content_length)
                    if full_size > start_offset:
                        logger.warning(
                            "Server does not support Range requests, restarting download"
                        )
                        # Truncate the file and restart from the beginning
                        with open(part_path, "wb") as f:
                            pass  # This truncates the file
                        start_offset = 0
                        # Retry the request without the Range header
                        headers.pop("Range", None)
                        with self._download_client.stream(
                            "GET",
                            url,
                            follow_redirects=True,
                            headers=headers,
                        ) as retry_response:
                            retry_response.raise_for_status()
                            response = retry_response
                except ValueError:
                    pass  # content-length wasn't an integer

            mode = "ab" if start_offset > 0 else "wb"
            total_size = _response_total_size(response)
            with open(part_path, mode) as f:
                for chunk in response.iter_bytes(CHUNK_SIZE):
                    if self._shutdown_event.is_set():
                        return
                    f.write(chunk)

        # If the server advertised a full size and we did not resume, verify it.
        if total_size is not None and start_offset == 0:
            got = part_path.stat().st_size
            if got != total_size:
                raise httpx.RemoteProtocolError(
                    f"Incomplete download: got {got} bytes, expected {total_size}"
                )

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


def _response_total_size(response: httpx.Response) -> int | None:
    """Return the total expected size for a response, accounting for ranges."""
    # Content-Range: bytes 1234-5678/9999
    content_range = response.headers.get("content-range", "")
    if content_range and "/" in content_range:
        try:
            return int(content_range.split("/")[-1])
        except (ValueError, IndexError):
            pass
    # Standard full download.
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            return int(content_length)
        except ValueError:
            pass
    return None


def _part_file_offset(part_path: Path) -> int:
    """Return the byte offset of an existing partial download, or 0."""
    try:
        return part_path.stat().st_size
    except (FileNotFoundError, OSError):
        return 0


def _part_path_for(path: Path) -> Path:
    """Return the .part sidecar path for a destination file."""
    # Use Path arithmetic to avoid depending on a real Path.suffix when mocked.
    return path.parent / (path.name + ".part")


def _commit_download(
    part_path: Path,
    path: Path,
    product: Product,
    item: DownloadItem,
    validate: bool,
) -> None:
    """Validate checksum and atomically move the .part file into place."""
    if (
        validate
        and (api_checksum := _newest_checksum(item))
        and (local_checksum := md5(part_path.read_bytes()).hexdigest()) != api_checksum
    ):
        logger.error(
            "ERROR: Invalid checksum for %s - %s, skipping saving file (%s != %s)",
            product["name"],
            item["filename"],
            api_checksum,
            local_checksum,
        )
        return

    os.replace(part_path, path)


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
