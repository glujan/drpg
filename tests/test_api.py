import re
from unittest import TestCase, mock
from urllib.parse import urlencode

import respx
from httpx import Response

from drpg import api

from .responses import FileTaskResponse

api_url = api.DrpgApi.API_URL


class DrpgApiTokenTest(TestCase):
    def setUp(self):
        self.login_url = "/api/v1/token?fields=customers_id"
        self.client = api.DrpgApi("token")

    @respx.mock(base_url=api_url)
    def test_login_valid_token(self, respx_mock):
        content = {"message": {"access_token": "some-token", "customers_id": "123"}}
        respx_mock.post(self.login_url).respond(201, json=content)

        login_data = self.client.token()
        self.assertEqual(login_data, content["message"])

    @respx.mock(base_url=api_url)
    def test_login_invalid_token(self, respx_mock):
        respx_mock.post(self.login_url).respond(401)

        with self.assertRaises(AttributeError):
            self.client.token()


class DrpgApiCustomerProductsTest(TestCase):
    def setUp(self):
        customer_id = "123"
        url = f"/api/v1/customers/{customer_id}/products"
        self.products_page = re.compile(f"{url}\\?.+$")
        self.client = api.DrpgApi("token")
        self.client._customer_id = customer_id

    @respx.mock(base_url=api_url)
    def test_one_page(self, respx_mock):
        page_1_products = [{"name": "First Product"}]
        respx_mock.get(self.products_page).mock(
            side_effect=[
                Response(200, json={"message": page_1_products}),
                Response(200, json={"message": []}),
            ]
        )

        products = self.client.customer_products()
        self.assertEqual(list(products), page_1_products)

    @respx.mock(base_url=api_url)
    def test_multiple_pages(self, respx_mock):
        page_1_products = [{"name": "First Product"}]
        page_2_products = [{"name": "Second Product"}]
        respx_mock.get(self.products_page).mock(
            side_effect=[
                Response(200, json={"message": page_1_products}),
                Response(200, json={"message": page_2_products}),
                Response(200, json={"message": []}),
            ]
        )
        products = self.client.customer_products()
        self.assertEqual(list(products), page_1_products + page_2_products)


class DrpgApiFileTaskTest(TestCase):
    def setUp(self):
        file_task_id = 123
        params = urlencode({"fields": "download_url,progress"})
        self.file_task_url = f"/api/v1/file_tasks/{file_task_id}?{params}"
        self.file_tasks_url = f"/api/v1/file_tasks?{params}"

        self.response_preparing = {"message": FileTaskResponse.preparing(file_task_id)}
        self.response_ready = {"message": FileTaskResponse.complete(file_task_id)}

        self.client = api.DrpgApi("token")

    @respx.mock(base_url=api_url)
    def test_immiediate_download_url(self, respx_mock):
        respx_mock.post(self.file_tasks_url).respond(201, json=self.response_ready)

        file_data = self.client.file_task("product_id", "item_id")
        self.assertEqual(file_data, self.response_ready["message"])

    @mock.patch("drpg.api.sleep")
    @respx.mock(base_url=api_url)
    def test_wait_for_download_url(self, _, respx_mock):
        respx_mock.post(self.file_tasks_url).respond(201, json=self.response_preparing)
        respx_mock.get(self.file_task_url).respond(200, json=self.response_ready)

        file_data = self.client.file_task("product_id", "item_id")
        self.assertEqual(file_data, self.response_ready["message"])

    @respx.mock(base_url=api_url)
    def test_unsuccesful_response(self, respx_mock):
        dummy_400_response = {"message": "Invalid product id"}
        respx_mock.post(self.file_tasks_url).respond(400, json=dummy_400_response)

        with self.assertRaises(self.client.FileTaskException) as cm:
            self.client.file_task("product_id", "item_id")
        self.assertTupleEqual(
            cm.exception.args, (self.client.FileTaskException.REQUEST_FAILED,)
        )

    @respx.mock(base_url=api_url)
    def test_unexpected_response_with_string_message(self, respx_mock):
        dummy_unexpected_response = {"message": "Invalid product id"}
        respx_mock.post(self.file_tasks_url).respond(
            201, json=dummy_unexpected_response
        )

        with self.assertRaises(self.client.FileTaskException) as cm:
            self.client.file_task("product_id", "item_id")
        self.assertTupleEqual(
            cm.exception.args, (self.client.FileTaskException.UNEXPECTED_RESPONSE,)
        )

    @respx.mock(base_url=api_url)
    def test_unexpected_response_with_json_message(self, respx_mock):
        dummy_unexpected_response = {"message": {"reason": "Invalid product id"}}
        respx_mock.post(self.file_tasks_url).respond(
            201, json=dummy_unexpected_response
        )

        with self.assertRaises(self.client.FileTaskException) as cm:
            self.client.file_task("product_id", "item_id")
        self.assertTupleEqual(
            cm.exception.args, (self.client.FileTaskException.UNEXPECTED_RESPONSE,)
        )
