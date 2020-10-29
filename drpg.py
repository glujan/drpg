from datetime import datetime, timedelta
from functools import partial
from hashlib import md5
from multiprocessing.pool import ThreadPool
from os import environ
from pathlib import Path
from time import sleep, timezone
import argparse
import functools
import logging
import re
import signal
import sys

import httpx


logger = logging.getLogger("drpg")

checksum_time_format = "%Y-%m-%d %H:%M:%S"


def suppress_errors(*errors):
    """Silence but log provided errors."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                func(*args, **kwargs)
            except errors as e:
                logger.exception(e)

        return wrapper

    return decorator


class DrpgApi:
    """Low-level REST API client for DriveThruRPG"""

    API_URL = "https://www.drivethrurpg.com"

    def __init__(self, api_key):
        self._client = httpx.Client(base_url=self.API_URL)
        self._api_key = api_key
        self._customer_id = None

    def token(self):
        """
        Update access token and customer's details based on an API key.

        Available "fields" values: first_name, last_name, customers_id
        """
        resp = self._client.post(
            "/api/v1/token",
            params={"fields": "customers_id"},
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

        if resp.status_code == httpx.codes.UNAUTHORIZED:
            raise AttributeError("Provided token is invalid")

        login_data = resp.json()["message"]
        self._customer_id = login_data["customers_id"]
        self._client.headers["Authorization"] = f"Bearer {login_data['access_token']}"
        return login_data

    def customer_products(self, per_page=100):
        """List all not archived customer's products."""

        product_page = partial(
            self._client.get,
            f"/api/v1/customers/{self._customer_id}/products",
            headers={"Content-Type": "application/json"},
        )
        page = 1

        while result := self._product_page(product_page, page, per_page):
            logger.debug("Yielding products page %d", page)
            yield from result
            page += 1

    def file_task(self, product_id, item_id):
        """
        Generate a download link and metadata for a product's item.

        Available "fields" values: products_id, bundle_id, checksums.
        """
        task_params = {"fields": "download_url,progress"}
        resp = self._client.post(
            "/api/v1/file_tasks",
            params=task_params,
            data={"products_id": product_id, "bundle_id": item_id},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        while (data := resp.json()["message"])["progress"].startswith("Preparing"):
            logger.debug("Waiting for download link for: %s - %s", product_id, item_id)
            sleep(3)
            task_id = data["file_tasks_id"]
            resp = self._client.get(f"/api/v1/file_tasks/{task_id}", params=task_params)

        logger.debug("Got download link for: %s - %s", product_id, item_id)
        return data

    def _product_page(self, func, page, per_page):
        """
        List products from a specified page.

        Available "fields" values:
            products_name, cover_url, date_purchased, products_filesize,
            publishers_name, products_thumbnail100
        Available "embed" values:
            files.filename, files.last_modified, files.checksums, files.raw_filesize,
            filters.filters_name, filters.filters_id, filters.parent_id
        """

        return func(
            params={
                "page": page,
                "per_page": per_page,
                "include_archived": 0,
                "fields": "publishers_name,products_name",
                "embed": "files.filename,files.last_modified,files.checksums",
            }
        ).json()["message"]


class DrpgSync:
    """Easily download products from a customer's library."""

    def __init__(self, config):
        self._use_checksums = config.use_checksums
        self._library_path = config.library_path
        self._api = DrpgApi(config.token)

    def sync(self):
        """Download all new, updated and not yet synced items to a sync directory."""

        self._api.token()
        items = (
            (product, item)
            for product in self._api.customer_products()
            for item in product.pop("files")
            if self._need_download(product, item, self._use_checksums)
        )

        with ThreadPool(5) as pool:
            pool.starmap(self._process_item, items)
        logger.info("Done!")

    @suppress_errors(httpx.HTTPError, PermissionError)
    def _process_item(self, product, item):
        """Prepare for and download the item to the sync directory."""

        logger.info("Processing: %s - %s", product["products_name"], item["filename"])

        url_data = self._api.file_task(product["products_id"], item["bundle_id"])
        file_response = httpx.get(url_data["download_url"])

        path = self._file_path(product, item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_response.content)

    def _need_download(self, product, item, use_checksums=False):
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
            use_checksums
            and (checksum := newest_checksum(item))
            and md5(path.read_bytes()).hexdigest() != checksum
        ):
            return True

        logger.debug("Up to date: %s - %s", product["products_name"], item["filename"])
        return False

    def _file_path(self, product, item):
        publishers_name = _escape_path_part(product.get("publishers_name", "Others"))
        product_name = _escape_path_part(product["products_name"])
        item_name = _escape_path_part(item["filename"])
        return self._library_path / publishers_name / product_name / item_name


def _escape_path_part(part: str) -> str:
    separator = " - "
    part = re.sub(r'[<>:"/\\|?*]', separator, part).strip(separator)
    part = re.sub(f"({separator})+", separator, part)
    part = re.sub(r"\s+", " ", part)
    return part


def newest_checksum(item):
    return max(
        item["checksums"],
        default={"checksum": None},
        key=lambda s: datetime.strptime(s["checksum_date"], checksum_time_format),
    )["checksum"]


def _setup(args=None):
    parser = argparse.ArgumentParser(
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
    logger.addHandler(handler)
    logger.setLevel(level)


def signal_handler(sig, frame):
    logger.info("Stopping...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    config = _setup()
    _setup_logger(config.log_level)
    DrpgSync(config).sync()
