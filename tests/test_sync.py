import dataclasses
import string
from datetime import datetime, timedelta
from functools import partial
from hashlib import md5
from os import stat_result
from pathlib import Path
from unittest import TestCase, mock

import respx
from httpx import HTTPError

import drpg.sync
from drpg.api import DrpgApi

from .responses import Checksum, FileResponse, FileTaskResponse, ProductResponse


class dummy_config:
    token = "private-token"
    use_checksums = False
    library_path = Path("./test_library")


PathMock = partial(mock.Mock, spec=Path)


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
        self.sync = drpg.DrpgSync(dummy_config)

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
        self.sync._use_checksums = True

        with self.subTest("same md5"):
            item = self.dummy_item(self.old_date)
            product = self.dummy_product(item)

            need = self.sync._need_download(product, item)
            self.assertFalse(need)

        with self.subTest("different md5"):
            item = self.dummy_item(self.old_date)
            item["checksums"][0]["checksum"] += "not matching"
            product = self.dummy_product(item)

            need = self.sync._need_download(product, item)
            self.assertTrue(need)

        with self.subTest("remote file has no checksum"):
            item = self.dummy_item(self.old_date)
            item["checksums"] = []
            product = self.dummy_product(item)

            need = self.sync._need_download(product, item)
            self.assertFalse(need)

    def dummy_item(self, date):
        file_md5 = md5(self.file_content).hexdigest()
        return dataclasses.asdict(
            FileResponse("file.pdf", date.isoformat(), [Checksum(file_md5)])
        )

    def dummy_product(self, *files):
        return dataclasses.asdict(
            ProductResponse("Test rule book", "Test Publishing", files=files)
        )


class DrpgSyncFilePathTest(TestCase):
    def setUp(self):
        self.sync = drpg.DrpgSync(dummy_config)

    def test_product_starts_with_slash(self):
        product = {
            "publishers_name": "/Slash Publishing",
            "products_name": "Rulebook - 2. ed",
        }
        item = {"filename": "filename.pdf"}

        path = self.sync._file_path(product, item)
        try:
            path.relative_to(dummy_config.library_path)
        except ValueError as e:
            self.fail(e)


class DrpgSyncProcessItemTest(TestCase):
    file_task = FileTaskResponse.complete("123")
    content = b"content"

    def setUp(self):
        item = FileResponse("file.pdf", datetime.now().isoformat(), [Checksum("md5")])
        self.item = dataclasses.asdict(item)
        self.product = dataclasses.asdict(
            ProductResponse("Test rule book", "Test Publishing", files=[item])
        )
        self.sync = drpg.DrpgSync(dummy_config)

    @mock.patch("drpg.DrpgSync._file_path", return_value=PathMock())
    @mock.patch("drpg.api.DrpgApi.file_task", return_value=file_task)
    @respx.mock(base_url=DrpgApi.API_URL)
    def test_writes_to_file(self, _, m_file_path, respx_mock):
        respx_mock.get(self.file_task["download_url"]).respond(
            200, content=self.content
        )

        path = m_file_path.return_value
        type(path).parent = mock.PropertyMock(return_value=PathMock())

        self.sync._process_item(self.product, self.item)

        path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        path.write_bytes.assert_called_once_with(self.content)

    @mock.patch("drpg.sync.logger")
    @mock.patch("drpg.api.DrpgApi.file_task")
    def test_io_error_occurs(self, m_file_task, _):
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

    @mock.patch("drpg.sync.logger")
    @mock.patch("drpg.api.DrpgApi.file_task")
    def test_unexpected_file_task_response(self, m_file_task, m_logger):
        m_file_task.side_effect = DrpgApi.FileTaskException
        try:
            self.sync._process_item(self.product, self.item)
        except DrpgApi.FileTaskException as e:
            self.fail(e)
        else:
            m_logger.warning.assert_called_once()
            msg, *_ = m_logger.warning.call_args[0]
            self.assertIn("Could not download product", msg)


class DrpgSyncTest(TestCase):
    def setUp(self):
        self.sync = drpg.DrpgSync(dummy_config)

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
