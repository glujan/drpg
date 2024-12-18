from __future__ import annotations

import logging
from time import sleep
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator
    from typing import TypedDict

    class TokenResponse(TypedDict):
        token: str
        refreshToken: str
        refreshTokenTTL: int

    class FileTasksResponse(TypedDict):
        file_tasks_id: str
        message: str
        download_url: str

    class Product(TypedDict):
        productId: str
        publisher: Publisher
        name: str
        bundleId: int
        orderProductId: str  # Used to generate download file
        fileLastModified: str
        files: list[DownloadItem]

    class Publisher(TypedDict):
        name: str

    class DownloadItem(TypedDict):
        index: int
        filename: str
        orderProductDownloadId: int
        checksums: list[Checksum]

    class Checksum(TypedDict):
        checksum: str
        checksumDate: str


logger = logging.getLogger("drpg")
JSON_MIME = "application/json"


class DrpgApi:
    """Low-level REST API client for DriveThruRPG"""

    API_URL = "https://api.drivethrurpg.com/api/vBeta/"

    class FileTaskException(Exception):
        UNEXPECTED_RESPONSE = "Got response with unexpected schema"
        REQUEST_FAILED = "Got non 2xx response"

    def __init__(self, api_key: str):
        self._client = httpx.Client(base_url=self.API_URL, timeout=30.0)
        self._api_key = api_key
        self._customer_id = None  # TODO Unused?

    def token(self) -> TokenResponse:
        """
        Update access token and customer's details based on an API key.
        """
        resp = self._client.post(
            "auth_key",
            params={"applicationKey": self._api_key},
            headers={
                "Content-Type": JSON_MIME,
                "Accept": JSON_MIME,
                "Accept-Encoding": "gzip, deflate",
                "User-Agent": "Mozilla/5.0",
            },
        )

        if resp.status_code == httpx.codes.UNAUTHORIZED:
            raise AttributeError("Provided token is invalid")

        login_data: TokenResponse = resp.json()
        self._client.headers["Authorization"] = login_data["token"]
        return login_data

    def customer_products(self, per_page: int = 50) -> Iterator[Product]:
        """List all not archived customer's products."""

        page = 1

        while result := self._product_page(page, per_page):
            logger.debug("Yielding products page %d", page)
            yield from result
            page += 1

    def file_task(self, product_id: str, item_id: int) -> FileTasksResponse:
        """
        Generate a download link and metadata for a product's item.
        """
        task_params = {
            "siteId": 10,  # Magic number, probably something like storefront ID
            "index": 0,
            "getChecksums": 0,  # Official clients defaults to 1
        }
        resp = self._client.post(  # TODO Outdated
            f"order_products/{product_id}/prepare",
            params=task_params,
            headers={
                "Content-Type": JSON_MIME,
                "Accept": JSON_MIME,
                "Accept-Encoding": "gzip, deflate",
                "User-Agent": "Mozilla/5.0",
            },
        )

        def _parse_message(resp):
            message = resp.json()["message"]
            if resp.is_success:
                expected_keys = {"progress", "file_tasks_id", "download_url"}
                if isinstance(message, dict) and expected_keys.issubset(message.keys()):
                    logger.debug("Got download url for %s - %s: %s", product_id, item_id, message)
                else:
                    logger.debug(
                        "Got unexpected message when getting download url for %s - %s: %s",
                        product_id,
                        item_id,
                        message,
                    )
                    raise self.FileTaskException(self.FileTaskException.UNEXPECTED_RESPONSE)
            else:
                logger.debug(
                    "Could not get download link for %s - %s: %s",
                    product_id,
                    item_id,
                    message,
                )
                raise self.FileTaskException(self.FileTaskException.REQUEST_FAILED)
            return message

        while (data := _parse_message(resp))["progress"].startswith("Preparing"):
            logger.debug("Waiting for download link for: %s - %s", product_id, item_id)
            sleep(3)
            task_id = data["file_tasks_id"]
            resp = self._client.get(f"file_tasks/{task_id}", params=task_params)  # TODO Outdated

        logger.debug("Got download link for: %s - %s", product_id, item_id)
        return data

    def _product_page(self, page: int, per_page: int) -> list[Product]:
        """
        List products from a specified page.
        """

        return self._client.get(
            "order_products",
            headers={
                "Content-Type": JSON_MIME,
                "Accept": JSON_MIME,
                "Accept-Encoding": "gzip, deflate",
                "User-Agent": "Mozilla/5.0",
            },
            params={
                "getChecksum": 1,
                "getFilters": 0,  # Official clients defaults to 1
                "page": page,
                "pageSize": per_page,
                "library": 1,
                "archived": 0,
            },
        ).json()
