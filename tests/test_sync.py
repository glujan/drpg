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
from drpg import types
from drpg.api import DrpgApi

from .fixtures import PrepareDownloadUrlResponseFixture


class dummy_config:
    token = "private-token"
    use_checksums = False
    validate = False
    library_path = Path("./test_library")
    dry_run = False
    threads = 5
    compatibility_mode = False
    omit_publisher = False


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
                except error as e:  # pragma: no cover
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
        product["fileLastModified"] = datetime.now().isoformat()

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
        self.sync._config.use_checksums = True

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
        return types.DownloadItem(
            index=0,
            filename="file.pdf",
            checksums=[types.Checksum(checksum=file_md5, checksumDate=_checksum_date_now())],
        )

    def dummy_product(self, file):
        return types.Product(
            productId="test-id",
            publisher=types.Publisher(name="Test Publishing"),
            name="Test rule book",
            orderProductId=123,
            fileLastModified=self.old_date.isoformat(),
            files=[file],
        )


class DrpgSyncFilePathTest(TestCase):
    def test_product_starts_with_slash(self):
        product = {
            "name": "Rulebook - 2. ed",
            "publisher": {"name": "/Slash Publishing"},
        }
        item = {"filename": "filename.pdf"}

        path = drpg.DrpgSync(dummy_config)._file_path(product, item)
        try:
            path.relative_to(dummy_config.library_path)
        except ValueError as e:  # pragma: no cover
            self.fail(e)

    def test_omit_publisher(self):
        publisher = "Unit Publishing"
        product = {
            "name": "Rulebook - 2. ed",
            "publisher": {"name": publisher},
        }
        item = {"filename": "filename.pdf"}

        config = dummy_config()
        config.omit_publisher = True
        path = drpg.DrpgSync(config)._file_path(product, item)
        self.assertNotIn(publisher, str(path))

    def test_not_omit_publisher(self):
        publisher = "Unit Publishing"
        product = {
            "name": "Rulebook - 2. ed",
            "publisher": {"name": publisher},
        }
        item = {"filename": "filename.pdf"}

        config = dummy_config()
        config.omit_publisher = False
        path = drpg.DrpgSync(config)._file_path(product, item)
        self.assertIn(publisher, str(path))


class DrpgSyncProcessItemTest(TestCase):
    download_url = PrepareDownloadUrlResponseFixture.complete()
    content = b"content"

    def setUp(self):
        self.item = types.DownloadItem(
            index=0,
            filename="test.pdf",
            checksums=[types.Checksum(checksum="md5", checksumDate=_checksum_date_now())],
        )
        self.product = types.Product(
            productId="test-product",
            publisher=types.Publisher(name="Test Publishing"),
            name="Test rule book",
            orderProductId=123,
            fileLastModified=datetime.now().isoformat(),
            files=[self.item],
        )
        self.sync = drpg.DrpgSync(dummy_config)

    @mock.patch("drpg.DrpgSync._file_path", return_value=PathMock())
    @mock.patch("drpg.api.DrpgApi.prepare_download_url", return_value=download_url)
    @respx.mock(base_url=DrpgApi.API_URL, using="httpx")
    def test_writes_to_file(self, _, file_path, respx_mock):
        respx_mock.get(self.download_url["url"]).respond(200, content=self.content)

        path = file_path.return_value
        type(path).parent = mock.PropertyMock(return_value=PathMock())

        self.sync._process_item(self.product, self.item)

        path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        path.write_bytes.assert_called_once_with(self.content)

    @mock.patch("drpg.sync.logger")
    @mock.patch("drpg.api.DrpgApi.prepare_download_url")
    def test_io_error_occurs(self, prepare_download_url, _):
        class TestHTTPError(HTTPError):
            def __init__(self):
                "Helper error to easier make an instance of HTTPError"

        for error_class in [TestHTTPError, PermissionError]:
            with self.subTest(error_class=error_class):
                prepare_download_url.side_effect = error_class
                try:
                    self.sync._process_item(self.product, self.item)
                except error_class as e:  # pragma:  no cover
                    self.fail(e)

    @mock.patch("drpg.sync.logger")
    @mock.patch("drpg.api.DrpgApi.prepare_download_url")
    def test_unexpected_prepare_download_url_response(self, prepare_download_url, logger):
        prepare_download_url.side_effect = DrpgApi.PrepareDownloadUrlException
        try:
            self.sync._process_item(self.product, self.item)
        except DrpgApi.PrepareDownloadUrlException as e:  # pragma:  no cover
            self.fail(e)
        else:
            logger.warning.assert_called_once()
            msg, *_ = logger.warning.call_args[0]
            self.assertIn("Could not download product", msg)

    @mock.patch("drpg.sync.logger")
    @mock.patch("drpg.DrpgSync._file_path", return_value=PathMock())
    @mock.patch("drpg.api.DrpgApi.prepare_download_url", return_value=download_url)
    def test_invalid_download(self, _prepare_download_url, _file_path, logger):
        config = dummy_config()
        config.validate = True
        drpg.DrpgSync(config)._process_item(self.product, self.item)
        logger.error.assert_called_once()
        self.assertIn("Invalid checksum", logger.error.call_args.args[0])

    @mock.patch("drpg.sync.logger")
    @mock.patch("drpg.DrpgSync._file_path", return_value=PathMock())
    def test_dry_run(self, file_path, logger):
        config = dummy_config()
        config.dry_run = True
        drpg.DrpgSync(config)._process_item(self.product, self.item)
        logger.info.assert_called_once()
        self.assertEqual(logger.info.call_args.args[1], file_path.return_value)


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
            self.dummy_product(f"Rule Book {i}", files_count) for i in range(products_count)
        ]
        self.sync.sync()
        self.assertEqual(process_item_mock.call_count, files_count * products_count)

    def dummy_product(self, name, files_count):
        return types.Product(
            productId="test-product",
            publisher=types.Publisher(name="Test Publishing"),
            name=name,
            orderProductId=987,
            fileLastModified=datetime.now().isoformat(),
            files=[
                types.DownloadItem(index=0, filename=f"file{i}.pdf", checksums=[])
                for i in range(files_count)
            ],
        )


class EscapePathTest(TestCase):
    def test_substitute_whitespaces(self):
        for whitespace in string.whitespace:
            name = f"some{whitespace}name"
            self.assertEqual(drpg.sync._normalize_path_part(name, False), "some name")
            self.assertEqual(drpg.sync._normalize_path_part(name, True), "some name")

    def test_normalize_path_part(self):
        """
        Make sure that filenames and directory names use UTF-8 character instead of
        escape codes. For example, "Game Designers&#039; Workshop (GDW)" should
        become "Game Designers' Workshop (GDW)"
        """
        # It's a pity that Python unittest doesn't have built-in support for parameterized
        # test cases like pytest does. Instead, we'll just loop through this table of expectations.
        test_data = [
            # drpg - fabricated names for the test
            ["<name>", False, "name"],
            ["No/slash", False, "No - slash"],
            ["less<than", False, "less - than"],
            ["two -  - to one", False, "two - to one"],
            ["squash   \tme", False, "squash me"],
            [" trim ", False, "trim"],
            # drpg with compatibility mode off - These are actual product names
            ["Game Designers&#039; Workshop (GDW)", False, "Game Designers' Workshop (GDW)"],
            [
                "The Eyes of Winter (Holiday Adventure)",
                False,
                "The Eyes of Winter (Holiday Adventure)",
            ],
            ["Not So Fast, Billy Ray!", False, "Not So Fast, Billy Ray!"],
            ["SAWS+ Character Sheet for Pathfinder", False, "SAWS+ Character Sheet for Pathfinder"],
            ["Tabletop Gaming Guide to: Vikings", False, "Tabletop Gaming Guide to - Vikings"],
            ["Fast & Light", False, "Fast & Light"],
            [
                "1,000+ Forgotten Magical Items Volume I (Weapons & Armor)",
                False,
                "1,000+ Forgotten Magical Items Volume I (Weapons & Armor)",
            ],
            # compatibility mode - fabricated names for the test
            ["<name>", True, "_name_"],
            ['<>:"/\\|?*', True, "_________"],
            ["No/slash", True, "No_slash"],
            ["less<than", True, "less_than"],  # This is hypothetical
            # compatibility mode (DTRPG client) - These are all actual product names
            ["Game Designers&#039; Workshop (GDW)", True, "Game Designers__039_ Workshop _GDW_"],
            [
                "The Eyes of Winter (Holiday Adventure)",
                True,
                "The Eyes of Winter _Holiday Adventure_",
            ],
            ["Not So Fast, Billy Ray!", True, "Not So Fast_ Billy Ray_"],
            ["SAWS+ Character Sheet for Pathfinder", True, "SAWS_ Character Sheet for Pathfinder"],
            ["Tabletop Gaming Guide to: Vikings", True, "Tabletop Gaming Guide to_ Vikings"],
            ["Fast & Light", True, "Fast _ Light"],
            [
                "1,000+ Forgotten Magical Items Volume I (Weapons & Armor)",
                True,
                "1_000_ Forgotten Magical Items Volume I _Weapons _ Armor_",
            ],
        ]

        for row in test_data:
            with self.subTest(msg=row[0]):
                self.assertEqual(
                    drpg.sync._normalize_path_part(row[0], row[1]),
                    row[2],
                    msg=f"With compatibility mode {row[1]}",
                )


class NewestChecksumTest(TestCase):
    def test_no_checksums(self):
        checksum = drpg.sync._newest_checksum({"checksums": []})
        self.assertIsNone(checksum)


def _checksum_date_now() -> str:
    return datetime.now().isoformat()
