from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import httpx

from drpg.types import DownloadUrlResponse

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from drpg.types import Product, TokenResponse

logger = logging.getLogger("drpg")
JSON_MIME = "application/json"


class DrpgApi:
    """Low-level REST API client for DriveThruRPG"""

    API_URL = "https://api.drivethrurpg.com/api/vBeta/"

    class ApiException(Exception):
        pass

    class PrepareDownloadUrlException(ApiException):
        UNEXPECTED_RESPONSE = "Got response with unexpected schema"
        REQUEST_FAILED = "Got non 2xx response"

    def __init__(self, api_key: str):
        logger.debug("Preparing httpx client")
        self._client = httpx.Client(
            base_url=self.API_URL,
            http1=False,
            http2=True,
            timeout=30.0,
            headers={
                "Content-Type": JSON_MIME,
                "Accept": JSON_MIME,
                "Accept-Encoding": "gzip, deflate",
                "User-Agent": "Mozilla/5.0",
                "Connection": "keep-alive",
            },
        )
        self._api_key = api_key

    def token(self) -> TokenResponse:
        """Authenticate http client with access token based on an API key."""
        resp = self._client.post(
            "auth_key",
            params={"applicationKey": self._api_key},
        )

        if resp.status_code == httpx.codes.UNAUTHORIZED:
            raise AttributeError("Provided token is invalid")
        if not resp.is_success:
            raise self.ApiException(resp.content)

        login_data: TokenResponse = resp.json()
        self._client.headers["Authorization"] = login_data["token"]
        return login_data

    def products(self, page: int = 1, per_page: int = 50) -> Iterator[Product]:
        """List products from a specified page."""
        logger.debug("Yielding products page %d", page)
        resp = self._client.get(
            "order_products",
            params={
                "getChecksum": 1,
                "getFilters": 0,  # Official clients defaults to 1
                "page": page,
                "pageSize": per_page,
                "library": 1,
                "archived": 0,
            },
        )
        if not resp.is_success:
            raise self.ApiException(resp.content)

        yield from resp.json()

    def prepare_download_url(self, product_id: int, item_id: int) -> DownloadUrlResponse:
        """
        Prepare a download link and metadata for a product's item.

        Download link does not need to be ready immediately - if it's not,
        run check_download_url until it's ready.
        """

        task_params = {
            "siteId": 10,  # Magic number, probably something like storefront ID
            "index": item_id,
            "getChecksums": 1,
        }
        resp = self._client.get(f"order_products/{product_id}/prepare", params=task_params)

        logger.debug("Got download link for: %s - %s", product_id, item_id)
        return self._parse_message(resp, product_id, item_id)

    def check_download_url(self, product_id: int, item_id: int) -> DownloadUrlResponse:
        task_params = {
            "siteId": 10,  # Magic number, probably something like storefront ID
            "index": item_id,
            "getChecksums": 1,
        }
        resp = self._client.get(f"order_products/{product_id}/check", params=task_params)
        logger.debug("Checked download link for: %s - %s", product_id, item_id)
        return self._parse_message(resp, product_id, item_id)

    def _parse_message(
        self, resp: httpx.Response, product_id: int, item_id: int
    ) -> DownloadUrlResponse:
        message: DownloadUrlResponse = resp.json()
        if resp.is_success:
            expected_keys = DownloadUrlResponse.__required_keys__
            if isinstance(message, dict) and expected_keys.issubset(message.keys()):
                logger.debug(
                    "Got download url for %s - %s, status='%s'",
                    product_id,
                    item_id,
                    message["status"],
                )
            else:
                logger.debug(
                    "Got unexpected message when getting download url for %s - %s: %s",
                    product_id,
                    item_id,
                    message,
                )
                raise self.PrepareDownloadUrlException(
                    self.PrepareDownloadUrlException.UNEXPECTED_RESPONSE
                )
        else:
            logger.debug(
                "Could not get download link for %s - %s: %s",
                product_id,
                item_id,
                message,
            )
            raise self.PrepareDownloadUrlException(self.PrepareDownloadUrlException.REQUEST_FAILED)
        return cast(DownloadUrlResponse, message)
