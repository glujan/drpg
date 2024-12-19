import re
from functools import partial
from unittest import TestCase, mock
from urllib.parse import urlencode, urlparse

import respx
from httpx import Response

from drpg import api

from .responses import FileTaskResponse

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


class DrpgApiCustomerProductsTest(TestCase):
    def setUp(self):
        url = "api/vBeta/order_products"
        self.products_page = re.compile(f"{url}\\?.+$")
        self.client = api.DrpgApi("token")

    @tmp_respx_mock(base_url=api_base_url)
    def test_one_page(self, respx_mock):
        page_1_products = [{"name": "First Product"}]
        respx_mock.get(self.products_page).mock(
            side_effect=[
                Response(200, json=page_1_products),
                Response(200, json=[]),
            ]
        )

        products = self.client.customer_products()
        self.assertEqual(list(products), page_1_products)

    @tmp_respx_mock(base_url=api_base_url)
    def test_multiple_pages(self, respx_mock):
        page_1_products = [{"name": "First Product"}]
        page_2_products = [{"name": "Second Product"}]
        respx_mock.get(self.products_page).mock(
            side_effect=[
                Response(200, json=page_1_products),
                Response(200, json=page_2_products),
                Response(200, json=[]),
            ]
        )
        products = self.client.customer_products()
        self.assertEqual(list(products), page_1_products + page_2_products)


class DrpgApiFileTaskTest(TestCase):
    def setUp(self):
        self.product_id = "test-product-id"
        file_task_id = 123
        params = urlencode({"siteId": 10, "index": 0, "getChecksums": 0})
        self.file_tasks_url = f"/api/vBeta/order_products/{self.product_id}/prepare?{params}"

        self.response_preparing = FileTaskResponse.preparing(file_task_id)
        self.response_ready = FileTaskResponse.complete(file_task_id)

        self.client = api.DrpgApi("token")

    @tmp_respx_mock(base_url=api_base_url)
    def test_immiediate_download_url(self, respx_mock):
        respx_mock.post(self.file_tasks_url).respond(201, json=self.response_ready)

        file_data = self.client.file_task(self.product_id, "item_id")
        self.assertEqual(file_data, self.response_ready)

    @mock.patch("drpg.api.sleep")
    @tmp_respx_mock(base_url=api_base_url)
    def test_wait_for_download_url(self, _, respx_mock):
        respx_mock.post(self.file_tasks_url).respond(201, json=self.response_preparing)
        respx_mock.get(self.file_tasks_url).respond(200, json=self.response_ready)

        file_data = self.client.file_task(self.product_id, "item_id")
        self.assertEqual(file_data, self.response_ready)

    @tmp_respx_mock(base_url=api_base_url)
    def test_unsuccesful_response(self, respx_mock):
        dummy_400_response = {"message": "Invalid product id"}
        respx_mock.post(self.file_tasks_url).respond(400, json=dummy_400_response)

        with self.assertRaises(self.client.FileTaskException) as cm:
            self.client.file_task(self.product_id, "item_id")
        self.assertTupleEqual(cm.exception.args, (self.client.FileTaskException.REQUEST_FAILED,))

    @tmp_respx_mock(base_url=api_base_url)
    def test_unexpected_response_with_string_message(self, respx_mock):
        dummy_unexpected_response = {"message": "Invalid product id"}
        respx_mock.post(self.file_tasks_url).respond(201, json=dummy_unexpected_response)

        with self.assertRaises(self.client.FileTaskException) as cm:
            self.client.file_task(self.product_id, "item_id")
        self.assertTupleEqual(
            cm.exception.args, (self.client.FileTaskException.UNEXPECTED_RESPONSE,)
        )

    @tmp_respx_mock(base_url=api_base_url)
    def test_unexpected_response_with_json_message(self, respx_mock):
        dummy_unexpected_response = {"message": {"reason": "Invalid product id"}}
        respx_mock.post(self.file_tasks_url).respond(201, json=dummy_unexpected_response)

        with self.assertRaises(self.client.FileTaskException) as cm:
            self.client.file_task(self.product_id, "item_id")
        self.assertTupleEqual(
            cm.exception.args, (self.client.FileTaskException.UNEXPECTED_RESPONSE,)
        )
