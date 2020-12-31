from datetime import datetime, timedelta
from functools import partial
from hashlib import md5
from inspect import currentframe
from os import stat_result
from pathlib import Path
from random import randint
from signal import SIGTERM
from typing import List, Optional
from unittest import TestCase, mock
from urllib.parse import urlencode
import dataclasses
import re
import string

from httpx import HTTPError
import respx

import drpg
import drpg.api
import drpg.cmd
import drpg.sync


api_url = drpg.api.DrpgApi.API_URL
test_cli_params = "-t private-token --log-level CRITICAL".split()

PathMock = partial(mock.Mock, spec=Path)


def checksum_date_now():
    return datetime.now().strftime(drpg.sync._checksum_time_format)


def random_id():
    return str(randint(100, 1000))


@dataclasses.dataclass
class _Checksum:
    checksum: str
    checksum_date: str = dataclasses.field(default_factory=checksum_date_now)


@dataclasses.dataclass
class FileTaskResponse:
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
            [_Checksum("md5hash") for _ in range(checksums_count)],
        )
        return dataclasses.asdict(instance)

    @classmethod
    def preparing(cls, file_task_id):
        instance = cls(
            file_task_id, "https://example.com/file.pdf", "Preparing download...", []
        )
        return dataclasses.asdict(instance)


@dataclasses.dataclass
class FileResponse:
    filename: str
    last_modified: str
    checksums: List[_Checksum]
    bundle_id: str = dataclasses.field(default_factory=random_id)


@dataclasses.dataclass
class ProductResponse:
    products_name: str
    publishers_name: str
    files: List[FileResponse]
    products_id: str = dataclasses.field(default_factory=random_id)


class SuppressErrorsTest(TestCase):
    def test_logs_error(self):
        error_classes = [KeyError, ValueError]

        @drpg.sync.suppress_errors(*error_classes)
        def func_that_raises(error):
            raise error()

        for error in error_classes:
            with self.subTest(error=error), mock.patch("drpg.sync.logger") as logger:
                try:
                    func_that_raises(error)
                except error as e:
                    self.fail(e)
                logger.exception.assert_called_once()


class DrpgApiTokenTest(TestCase):
    def setUp(self):
        self.login_url = "/api/v1/token?fields=customers_id"
        self.client = drpg.api.DrpgApi("token")

    @respx.mock(base_url=api_url)
    def test_login_valid_token(self, respx_mock):
        content = {"message": {"access_token": "some-token", "customers_id": "123"}}
        respx_mock.post(self.login_url, content=content, status_code=201)

        login_data = self.client.token()
        self.assertEqual(login_data, content["message"])

    @respx.mock(base_url=api_url)
    def test_login_invalid_token(self, respx_mock):
        respx_mock.post(self.login_url, status_code=401)

        with self.assertRaises(AttributeError):
            self.client.token()


class DrpgApiCustomerProductsTest(TestCase):
    def setUp(self):
        customer_id = "123"
        url = f"/api/v1/customers/{customer_id}/products"
        self.products_page = re.compile(f"{url}\\?.+$")
        self.client = drpg.api.DrpgApi("token")
        self.client._customer_id = customer_id

    @respx.mock(base_url=api_url)
    def test_one_page(self, respx_mock):
        page_1_products = [{"name": "First Product"}]
        respx_mock.get(self.products_page, content={"message": page_1_products})
        respx_mock.get(self.products_page, content={"message": []})

        products = self.client.customer_products()
        self.assertEqual(list(products), page_1_products)

    @respx.mock(base_url=api_url)
    def test_multiple_pages(self, respx_mock):
        page_1_products = [{"name": "First Product"}]
        page_2_products = [{"name": "Second Product"}]
        respx_mock.get(self.products_page, content={"message": page_1_products})
        respx_mock.get(self.products_page, content={"message": page_2_products})
        respx_mock.get(self.products_page, content={"message": []})

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

        self.client = drpg.api.DrpgApi("token")

    @respx.mock(base_url=api_url)
    def test_immiediate_download_url(self, respx_mock):
        respx_mock.post(self.file_tasks_url, content=self.response_ready)

        file_data = self.client.file_task("product_id", "item_id")
        self.assertEqual(file_data, self.response_ready["message"])

    @mock.patch("drpg.api.sleep")
    @respx.mock(base_url=api_url)
    def test_wait_for_download_url(self, _, respx_mock):
        respx_mock.post(self.file_tasks_url, content=self.response_preparing)
        respx_mock.get(self.file_task_url, content=self.response_ready)

        file_data = self.client.file_task("product_id", "item_id")
        self.assertEqual(file_data, self.response_ready["message"])


class DrpgSyncNeedDownloadTest(TestCase):
    new_date = datetime.now()
    old_date = new_date - timedelta(days=100)
    file_content = b"some file content"

    no_file_kwargs = {
        "exists.return_value": False,
        "read_bytes.side_effect": FileNotFoundError,
        "stat.side_effect": FileNotFoundError,
    }
    old_file_kwargs = {
        "exists.return_value": True,
        "read_bytes.return_value": file_content,
        "stat.return_value": mock.Mock(spec=stat_result, st_mtime=old_date.timestamp()),
    }
    new_file_kwargs = {
        "exists.return_value": True,
        "read_bytes.return_value": file_content,
        "stat.return_value": mock.Mock(spec=stat_result, st_mtime=new_date.timestamp()),
    }

    def setUp(self):
        self.sync = drpg.DrpgSync(drpg.cmd._parse_cli(test_cli_params))

    @mock.patch("drpg.DrpgSync._file_path", return_value=PathMock(**no_file_kwargs))
    def test_no_local_file(self, _):
        item = self.dummy_item(self.old_date)
        product = self.dummy_product(item)

        need = self.sync._need_download(product, item)
        self.assertTrue(need)

    @mock.patch("drpg.DrpgSync._file_path", return_value=PathMock(**old_file_kwargs))
    def test_local_last_modified_older(self, _):
        item = self.dummy_item(self.new_date)
        product = self.dummy_product(item)

        need = self.sync._need_download(product, item)
        self.assertTrue(need)

    @mock.patch("drpg.DrpgSync._file_path", return_value=PathMock(**new_file_kwargs))
    def test_local_last_modified_newer(self, _):
        item = self.dummy_item(self.old_date)
        product = self.dummy_product(item)

        need = self.sync._need_download(product, item)
        self.assertFalse(need)

    @mock.patch("drpg.DrpgSync._file_path", return_value=PathMock(**new_file_kwargs))
    def test_md5_check(self, _):
        with self.subTest("same md5"):
            item = self.dummy_item(self.old_date)
            product = self.dummy_product(item)

            need = self.sync._need_download(product, item, use_checksums=True)
            self.assertFalse(need)

        with self.subTest("different md5"):
            item = self.dummy_item(self.old_date)
            item["checksums"][0]["checksum"] += "not matching"
            product = self.dummy_product(item)

            need = self.sync._need_download(product, item, use_checksums=True)
            self.assertTrue(need)

        with self.subTest("remote file has no checksum"):
            item = self.dummy_item(self.old_date)
            item["checksums"] = []
            product = self.dummy_product(item)

            need = self.sync._need_download(product, item, use_checksums=True)
            self.assertFalse(need)

    def dummy_item(self, date):
        file_md5 = md5(self.file_content).hexdigest()
        return dataclasses.asdict(
            FileResponse("file.pdf", date.isoformat(), [_Checksum(file_md5)])
        )

    def dummy_product(self, *files):
        return dataclasses.asdict(
            ProductResponse("Test rule book", "Test Publishing", files=files)
        )


class DrpgSyncFilePathTest(TestCase):
    def setUp(self):
        self.sync = drpg.DrpgSync(drpg.cmd._parse_cli(test_cli_params))

    def test_product_starts_with_slash(self):
        product = {
            "publishers_name": "/Slash Publishing",
            "products_name": "Rulebook - 2. ed",
        }
        item = {"filename": "filename.pdf"}

        path = self.sync._file_path(product, item)
        try:
            path.relative_to("repository/Slash Publishing/")
        except ValueError as e:
            self.fail(e)


class DrpgSyncProcessItemTest(TestCase):
    file_task = FileTaskResponse.complete("123")
    content = b"content"

    def setUp(self):
        item = FileResponse("file.pdf", datetime.now().isoformat(), [_Checksum("md5")])
        self.item = dataclasses.asdict(item)
        self.product = dataclasses.asdict(
            ProductResponse("Test rule book", "Test Publishing", files=[item])
        )
        self.sync = drpg.DrpgSync(drpg.cmd._parse_cli(test_cli_params))

    @respx.mock(base_url=api_url)
    @mock.patch("drpg.DrpgSync._file_path", return_value=PathMock())
    @mock.patch("drpg.api.DrpgApi.file_task", return_value=file_task)
    def test_writes_to_file(self, _, m_file_path, respx_mock):
        respx_mock.get(self.file_task["download_url"], content=self.content)

        path = m_file_path.return_value
        type(path).parent = mock.PropertyMock(return_value=PathMock())

        self.sync._process_item(self.product, self.item)

        path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        path.write_bytes.assert_called_once_with(self.content)

    @mock.patch("drpg.sync.logger")
    @mock.patch("drpg.api.DrpgApi.file_task")
    def test_error_occurs(self, m_file_task, _):
        class TestHTTPError(HTTPError):
            def __init__(self):
                "Helper error to easier make an instance of HTTPError"

        for error_class in [TestHTTPError, PermissionError]:
            with self.subTest(error_class=error_class):
                m_file_task.side_effect = error_class
                try:
                    self.sync._process_item(self.product, self.item)
                except error_class as e:
                    self.fail(e)


class DrpgSyncTest(TestCase):
    def setUp(self):
        self.sync = drpg.DrpgSync(drpg.cmd._parse_cli(test_cli_params))

    @mock.patch("drpg.api.DrpgApi.token", return_value={"access_token": "t"})
    @mock.patch("drpg.DrpgSync._need_download", return_value=True)
    @mock.patch("drpg.api.DrpgApi.customer_products")
    @mock.patch("drpg.DrpgSync._process_item")
    def test_processes_each_item(self, process_item_mock, customer_products_mock, *_):
        files_count = 5
        products_count = 3
        customer_products_mock.return_value = [
            self.dummy_product(f"Rule Book {i}", files_count)
            for i in range(products_count)
        ]
        self.sync.sync()
        self.assertEqual(process_item_mock.call_count, files_count * products_count)

    def dummy_product(self, name, files_count):
        return dataclasses.asdict(
            ProductResponse(
                name,
                "Test Publishing",
                files=[
                    FileResponse(f"file{i}.pdf", datetime.now().isoformat(), [])
                    for i in range(files_count)
                ],
            )
        )


class EscapePathTest(TestCase):
    def test_escapes_invalid_characters(self):
        self.assert_removes_invalid_characters("/")

    def test_escapes_invalid_windows_characters(self):
        self.assert_removes_invalid_characters(r'<>:"/\|?*')

    def test_strips_invalid_characters(self):
        name = "<name>"
        self.assertEqual(drpg.sync._escape_path_part(name), "name")

    def test_substitue_whitespaces(self):
        for whitespace in string.whitespace:
            name = f"some{whitespace}name"
            self.assertEqual(drpg.sync._escape_path_part(name), "some name")

    def assert_removes_invalid_characters(self, characters):
        name = f"some{characters}name"
        self.assertEqual(drpg.sync._escape_path_part(name), "some - name")


class NewestChecksumTest(TestCase):
    def test_no_checksums(self):
        checksum = drpg.sync._newest_checksum({"checksums": []})
        self.assertIsNone(checksum)


class SetupTest(TestCase):
    @mock.patch("drpg.cmd.argparse.ArgumentParser.error")
    def test_has_required_params(self, error_mock):
        drpg.cmd._parse_cli([])
        error_mock.assert_called_once()

    def test_defaults_from_env(self):
        env = {
            "DRPG_TOKEN": "env-token",
            "DRPG_LIBRARY_PATH": "env/path",
            "DRPG_LOG_LEVEL": "DEBUG",
            "DRPG_USE_CHECKSUMS": "true",
        }

        with mock.patch.dict(drpg.cmd.environ, env):
            config = drpg.cmd._parse_cli([])

        self.assertEqual(config.token, env["DRPG_TOKEN"])
        self.assertEqual(config.library_path, Path(env["DRPG_LIBRARY_PATH"]))
        self.assertEqual(config.log_level, env["DRPG_LOG_LEVEL"])
        self.assertTrue(config.use_checksums)


class SignalHandlerTest(TestCase):
    @mock.patch("drpg.cmd.sys.exit")
    def test_exits(self, m_exit):
        drpg.cmd._handle_signal(SIGTERM, currentframe())
        m_exit.assert_called_once_with(0)
