from contextlib import closing
from datetime import datetime, timedelta
from functools import partial
from hashlib import md5
from multiprocessing.pool import ThreadPool
from os import environ
from pathlib import Path
from time import sleep, timezone
import argparse
import logging
import re
import sys

from httpx import Client as HttpClient, codes


client = HttpClient(base_url="https://www.drivethrurpg.com")
config = None
logger = logging.getLogger("drpg")

checksum_time_format = "%Y-%m-%d %H:%M:%S"


def setup_logger(level_name):
    level = logging.getLevelName(level_name)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    logger.addHandler(handler)
    logger.setLevel(level)


def login(token):
    # Available "fields" values: first_name, last_name, customers_id
    resp = client.post(
        "/api/v1/token",
        params={"fields": "customers_id"},
        headers={"Authorization": f"Bearer {token}"},
    )

    if resp.status_code == codes.UNAUTHORIZED:
        raise AttributeError("Provided token is invalid")

    return resp.json()["message"]


def get_products(customer_id, per_page=100):
    get_product_page = partial(
        client.get,
        f"/api/v1/customers/{customer_id}/products",
        headers={"Content-Type": "application/json"},
    )
    page = 1

    while result := _get_products_page(get_product_page, page, per_page):
        logger.debug("Yielding products page %d", page)
        yield from result
        page += 1


def _get_products_page(func, page, per_page):
    """
    Available "fields" values:
      products_name, cover_url, date_purchased, products_filesize, publishers_name,
      products_thumbnail100
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


def need_download(product, item, use_checksums=False):
    path = get_file_path(product, item)

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
        and (checksum := get_newest_checksum(item))
        and md5(path.read_bytes()).hexdigest() != checksum
    ):
        return True

    logger.debug("Up to date: %s - %s", product["products_name"], item["filename"])
    return False


def get_download_url(product_id, item_id):
    resp = client.post(
        "/api/v1/file_tasks",
        params={"fields": "download_url,progress,checksums"},
        data={"products_id": product_id, "bundle_id": item_id},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    while (data := resp.json()["message"])["progress"].startswith("Preparing download"):
        logger.info("Waiting to download: %s - %s", product_id, item_id)
        sleep(3)
        task_id = data["file_tasks_id"]
        resp = client.get(
            f"/api/v1/file_tasks/{task_id}",
            params={"fields": "download_url,progress,checksums"},
        )
    return data


def get_file_path(product, item):
    publishers_name = _escape_path_part(product.get("publishers_name", "Others"))
    product_name = _escape_path_part(product["products_name"])
    item_name = _escape_path_part(item["filename"])
    return config.library_path / publishers_name / product_name / item_name


def _escape_path_part(part: str) -> str:
    separator = " - "
    part = re.sub(r'[<>:"/\\|?*]', separator, part).strip(separator)
    part = re.sub(f"({separator})+", separator, part)
    part = re.sub(r"\s+", " ", part)
    return part


def get_newest_checksum(item):
    return max(
        item["checksums"],
        default={"checksum": None},
        key=lambda s: datetime.strptime(s["checksum_date"], checksum_time_format),
    )["checksum"]


def process_item(product, item):
    logger.info("Processing: %s - %s", product["products_name"], item["filename"])
    url_data = get_download_url(product["products_id"], item["bundle_id"])
    file_response = client.get(url_data["download_url"])
    path = get_file_path(product, item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(file_response.content)


def sync():
    login_data = login(config.token)
    client.headers["Authorization"] = f"Bearer {login_data['access_token']}"

    products = get_products(login_data["customers_id"], per_page=100)
    items = (
        (product, item)
        for product in products
        for item in product.pop("files")
        if need_download(product, item, config.use_checksums)
    )

    with ThreadPool(5) as pool:
        pool.starmap(process_item, items)
    logger.info("Done!")


def setup(args=None):
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
    global config
    config = parser.parse_args(args)
    setup_logger(config.log_level)


if __name__ == "__main__":
    setup()
    with closing(client):
        sync()
