from unittest import TestCase
import string

import drpg


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
