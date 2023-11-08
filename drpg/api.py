from __future__ import annotations

import logging
from time import sleep
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:  # pragma: no cover
    from typing import Iterator, TypedDict

    class TokenResponse(TypedDict):
        customers_id: str

    class FileTasksResponse(TypedDict):
        file_tasks_id: str
        message: str
        download_url: str

    class Product(TypedDict):
        products_id: str
        publishers_name: str
        products_name: str
        files: list[DownloadItem]

    class DownloadItem(TypedDict):
        filename: str
        last_modified: str
        bundle_id: str
        checksums: list[Checksum]

    class Checksum(TypedDict):
        checksum: str
        checksum_date: str


logger = logging.getLogger("drpg")


class DrpgApi:
    """Low-level REST API client for DriveThruRPG"""

    API_URL = "https://www.drivethrurpg.com"

    class FileTaskException(Exception):
        UNEXPECTED_RESPONSE = "Got response with unexpected schema"
        REQUEST_FAILED = "Got non 2xx response"

    def __init__(self, api_key: str):
        self._client = httpx.Client(base_url=self.API_URL, timeout=30.0)
        self._api_key = api_key
        self._customer_id = None

    def token(self) -> TokenResponse:
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

    def customer_products(self, per_page: int = 100) -> Iterator[Product]:
        """List all not archived customer's products."""

        page = 1

        while result := self._product_page(page, per_page):
            logger.debug("Yielding products page %d", page)
            yield from result
            page += 1

    def file_task(self, product_id: str, item_id: str) -> FileTasksResponse:
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
            resp = self._client.get(f"/api/v1/file_tasks/{task_id}", params=task_params)

        logger.debug("Got download link for: %s - %s", product_id, item_id)
        return data

    def _product_page(self, page: int, per_page: int) -> list[Product]:
        """
        List products from a specified page.

        Available "fields" values:
            products_name, cover_url, date_purchased, products_filesize,
            publishers_name, products_thumbnail100
        Available "embed" values:
            files.filename, files.last_modified, files.checksums, files.raw_filesize,
            filters.filters_name, filters.filters_id, filters.parent_id
        """

        return self._client.get(
            f"/api/v1/customers/{self._customer_id}/products",
            headers={"Content-Type": "application/json"},
            params={
                "page": page,
                "per_page": per_page,
                "include_archived": 0,
                "fields": "publishers_name,products_name",
                "embed": "files.filename,files.last_modified,files.checksums",
            },
        ).json()["message"]
