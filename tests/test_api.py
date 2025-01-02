import re
from functools import partial
from unittest import TestCase
from urllib.parse import urlencode, urlparse

import respx
from httpx import Response

from drpg import api

from .fixtures import DownloadUrlResponseFixture

_api_url = urlparse(api.DrpgApi.API_URL)
api_base_url = f"{_api_url.scheme}://{_api_url.hostname}"

# Workaround for https://github.com/lundberg/respx/issues/277
tmp_respx_mock = partial(respx.mock, using="httpx")


class DrpgApiTokenTest(TestCase):
    def setUp(self):
        self.login_url = "api/vBeta/auth_key"
        self.client = api.DrpgApi("token")

    @tmp_respx_mock(base_url=api_base_url)
    def test_login_valid_token(self, respx_mock):
        content = {"token": "some-token", "refreshToken": "123", "refreshTokenTTL": 171235}
        respx_mock.post(self.login_url).respond(200, json=content)

        login_data = self.client.token()
        self.assertEqual(login_data, content)

    @tmp_respx_mock(base_url=api_base_url)
    def test_login_invalid_token(self, respx_mock):
        respx_mock.post(self.login_url).respond(401)

        with self.assertRaises(AttributeError):
            self.client.token()


class DrpgApiProductsTest(TestCase):
    def setUp(self):
        url = "api/vBeta/order_products"
        self.products_page = re.compile(f"{url}\\?.+$")
        self.client = api.DrpgApi("token")

    @tmp_respx_mock(base_url=api_base_url)
    def test_products(self, respx_mock):
        page_1_products = [{"name": "First Product"}]
        respx_mock.get(self.products_page).mock(
            side_effect=[
                Response(200, json=page_1_products),
                Response(200, json=[]),
            ]
        )

        page_1 = self.client.products(1, 50)
        page_2 = self.client.products(2, 50)
        self.assertEqual(list(page_1), page_1_products)
        self.assertEqual(list(page_2), [])


class DrpgApiPrepareDownloadUrlTest(TestCase):
    def setUp(self):
        self.order_product_id = 123
        params = urlencode({"siteId": 10, "index": 0, "getChecksums": 1})
        self.prepare_download_url = (
            f"/api/vBeta/order_products/{self.order_product_id}/prepare?{params}"
        )
        self.check_download_url = (
            f"/api/vBeta/order_products/{self.order_product_id}/check?{params}"
        )

        self.response_preparing = DownloadUrlResponseFixture.preparing()
        self.response_ready = DownloadUrlResponseFixture.complete()

        self.client = api.DrpgApi("token")

    @tmp_respx_mock(base_url=api_base_url)
    def test_immiediate_download_url(self, respx_mock):
        respx_mock.get(self.prepare_download_url).respond(200, json=self.response_ready)

        file_data = self.client.prepare_download_url(self.order_product_id, 0)
        self.assertEqual(file_data, self.response_ready)

    @tmp_respx_mock(base_url=api_base_url)
    def test_wait_for_download_url(self, respx_mock):
        respx_mock.get(self.prepare_download_url).respond(200, json=self.response_preparing)
        respx_mock.get(self.check_download_url).respond(200, json=self.response_ready)

        file_data = self.client.prepare_download_url(self.order_product_id, 0)
        self.assertEqual(file_data, self.response_preparing)

        file_data = self.client.check_download_url(self.order_product_id, 0)
        self.assertEqual(file_data, self.response_ready)

    @tmp_respx_mock(base_url=api_base_url)
    def test_unsuccesful_response(self, respx_mock):
        dummy_400_response = {"message": "Invalid product id"}
        respx_mock.get(self.prepare_download_url).respond(400, json=dummy_400_response)

        with self.assertRaises(self.client.PrepareDownloadUrlException) as cm:
            self.client.prepare_download_url(self.order_product_id, 0)
        self.assertTupleEqual(
            cm.exception.args, (self.client.PrepareDownloadUrlException.REQUEST_FAILED,)
        )

    @tmp_respx_mock(base_url=api_base_url)
    def test_unexpected_response_with_string_message(self, respx_mock):
        dummy_unexpected_response = {"message": "Invalid product id"}
        respx_mock.get(self.prepare_download_url).respond(200, json=dummy_unexpected_response)

        with self.assertRaises(self.client.PrepareDownloadUrlException) as cm:
            self.client.prepare_download_url(self.order_product_id, 0)
        self.assertTupleEqual(
            cm.exception.args, (self.client.PrepareDownloadUrlException.UNEXPECTED_RESPONSE,)
        )

    @tmp_respx_mock(base_url=api_base_url)
    def test_unexpected_response_with_json_message(self, respx_mock):
        dummy_unexpected_response = {"message": {"reason": "Invalid product id"}}
        respx_mock.get(self.prepare_download_url).respond(200, json=dummy_unexpected_response)

        with self.assertRaises(self.client.PrepareDownloadUrlException) as cm:
            self.client.prepare_download_url(self.order_product_id, 0)
        self.assertTupleEqual(
            cm.exception.args, (self.client.PrepareDownloadUrlException.UNEXPECTED_RESPONSE,)
        )
