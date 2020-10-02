from datetime import datetime
from typing import List, Optional
from unittest import TestCase, mock
from urllib.parse import urlencode
import dataclasses
import re
import string

import respx

import drpg


api_url = str(drpg.client.base_url)


def checksum_date_now():
    return datetime.now().strftime(drpg.checksum_time_format)


@dataclasses.dataclass
class FileTaskResponse:
    @dataclasses.dataclass
    class _Checksum:
        checksum: str
        checksum_date: str = dataclasses.field(default_factory=checksum_date_now)

    file_tasks_id: int
    download_url: Optional[str]
    progress: Optional[str]
    checksums: List[_Checksum]

    @classmethod
    def complete(cls, file_task_id, checksums_count=1):
        instance = cls(
            file_task_id,
            "https://example.com/file.pdf",
            "Complete",
            [cls._Checksum("md5hash") for _ in range(checksums_count)],
        )
        return dataclasses.asdict(instance)

    @classmethod
    def preparing(cls, file_task_id):
        instance = cls(
            file_task_id, "https://example.com/file.pdf", "Preparing download...", []
        )
        return dataclasses.asdict(instance)


class LoginTest(TestCase):
    def setUp(self):
        self.login_url = "/api/v1/token?fields=customers_id"

    @respx.mock(base_url=api_url)
    def test_login_valid_token(self, respx_mock):
        content = {"message": {"access_token": "some-token", "customers_id": "123"}}
        respx_mock.post(self.login_url, content=content, status_code=201)

        login_data = drpg.login("token")
        self.assertEqual(login_data, content["message"])

    @respx.mock(base_url=api_url)
    def test_login_invalid_token(self, respx_mock):
        respx_mock.post(self.login_url, status_code=401)

        with self.assertRaises(AttributeError):
            drpg.login("token")


class GetProductsTest(TestCase):
    def setUp(self):
        self.customer_id = "123"
        self.access_token = "access_token"
        url = f"/api/v1/customers/{self.customer_id}/products"
        self.products_page = re.compile(f"{url}\\?.+$")

    @respx.mock(base_url=api_url)
    def test_one_page(self, respx_mock):
        page_1_products = [{"name": "First Product"}]
        respx_mock.get(self.products_page, content={"message": page_1_products})
        respx_mock.get(self.products_page, content={"message": []})

        products = drpg.get_products(self.customer_id, self.access_token)
        self.assertEqual(list(products), page_1_products)

    @respx.mock(base_url=api_url)
    def test_multiple_pages(self, respx_mock):
        page_1_products = [{"name": "First Product"}]
        page_2_products = [{"name": "Second Product"}]
        respx_mock.get(self.products_page, content={"message": page_1_products})
        respx_mock.get(self.products_page, content={"message": page_2_products})
        respx_mock.get(self.products_page, content={"message": []})

        products = drpg.get_products(self.customer_id, self.access_token)
        self.assertEqual(list(products), page_1_products + page_2_products)


class GetDownloadUrlTest(TestCase):
    def setUp(self):
        file_task_id = 123
        params = urlencode({"fields": "download_url,progress,checksums"})
        self.file_task_url = f"/api/v1/file_tasks/{file_task_id}?{params}"
        self.file_tasks_url = f"/api/v1/file_tasks?{params}"

        self.response_preparing = {"message": FileTaskResponse.preparing(file_task_id)}
        self.response_ready = {"message": FileTaskResponse.complete(file_task_id)}

    @respx.mock(base_url=api_url)
    def test_immiediate_download_url(self, respx_mock):
        respx_mock.post(self.file_tasks_url, content=self.response_ready)

        file_data = drpg.get_download_url("product_id", "item_id", "access_token")
        self.assertEqual(file_data, self.response_ready["message"])

    @mock.patch("drpg.sleep")
    @respx.mock(base_url=api_url)
    def test_wait_for_download_url(self, _, respx_mock):
        respx_mock.post(self.file_tasks_url, content=self.response_preparing)
        respx_mock.get(self.file_task_url, content=self.response_ready)

        file_data = drpg.get_download_url("product_id", "item_id", "access_token")
        self.assertEqual(file_data, self.response_ready["message"])


class GetFilePathTest(TestCase):
    def test_product_starts_with_slash(self):
        product = {
            "publishers_name": "/Slash Publishing",
            "products_name": "Rulebook - 2. ed",
        }
        item = {"filename": "filename.pdf"}

        path = drpg.get_file_path(product, item)
        try:
            path.relative_to("repository/Slash Publishing/")
        except ValueError as e:
            self.fail(e)


class EscapePathTest(TestCase):
    def test_escapes_invalid_characters(self):
        self.assert_removes_invalid_characters("/")

    def test_escapes_invalid_windows_characters(self):
        self.assert_removes_invalid_characters(r'<>:"/\|?*')

    def test_strips_invalid_characters(self):
        name = "<name>"
        self.assertEqual(drpg._escape_path_part(name), "name")

    def test_substitue_whitespaces(self):
        for whitespace in string.whitespace:
            name = f"some{whitespace}name"
            self.assertEqual(drpg._escape_path_part(name), "some name")

    def assert_removes_invalid_characters(self, characters):
        name = f"some{characters}name"
        self.assertEqual(drpg._escape_path_part(name), "some - name")


class GetNewestChecksum(TestCase):
    def test_no_checksums(self):
        checksum = drpg.get_newest_checksum({"checksums": []})
        self.assertIsNone(checksum)
