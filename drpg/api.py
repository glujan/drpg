import logging
from functools import partial
from time import sleep

import httpx

logger = logging.getLogger("drpg")


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
            },
        ).json()["message"]
