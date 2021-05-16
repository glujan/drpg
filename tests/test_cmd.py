from inspect import currentframe
from os.path import expandvars
from pathlib import Path
from signal import SIGTERM
from unittest import TestCase, mock

from drpg import cmd


class ParseCliTest(TestCase):
    @mock.patch("drpg.cmd.argparse.ArgumentParser.error")
    def test_has_required_params(self, error_mock):
        cmd._parse_cli([])
        error_mock.assert_called_once()

    def test_defaults_from_env(self):
        env = {
            "DRPG_TOKEN": "env-token",
            "DRPG_LIBRARY_PATH": "env/path",
            "DRPG_LOG_LEVEL": "DEBUG",
            "DRPG_USE_CHECKSUMS": "true",
        }

        with mock.patch.dict(cmd.environ, env):
            config = cmd._parse_cli([])

        self.assertEqual(config.token, env["DRPG_TOKEN"])
        self.assertEqual(config.library_path, Path(env["DRPG_LIBRARY_PATH"]))
        self.assertEqual(config.log_level, env["DRPG_LOG_LEVEL"])
        self.assertTrue(config.use_checksums)


class SignalHandlerTest(TestCase):
    @mock.patch("drpg.cmd.sys.exit")
    def test_exits(self, m_exit):
        cmd._handle_signal(SIGTERM, currentframe())
        m_exit.assert_called_once_with(0)


class DefaultDirTest:
    def setUp(self):
        self.platform_system = mock.patch(
            "drpg.cmd.platform.system", return_value=self.SYSTEM
        ).start()

    def tearDown(self):
        self.platform_system.stop()


class LinuxDefaultDirTest(DefaultDirTest, TestCase):
    SYSTEM = "Linux"
    DOCS_DIR = "$HOME/DocumentsDirInUsersLanguage"
    DOCS_DIR_FALLBACK = "$HOME/Documents"
    XDG_USER_DIRS_FILE = mock.mock_open(read_data=f'XDG_DOCUMENTS_DIR="{DOCS_DIR}"')

    @mock.patch("drpg.cmd.open", XDG_USER_DIRS_FILE)
    def test_xdg_config_home(self):
        with self.subTest("Default XDG_CONFIG_HOME"):
            env = {"XDG_CONFIG_HOME": ""}
            with mock.patch.dict("drpg.cmd.environ", env, clear=True):
                default_dir = cmd._default_dir()
            self.assertTrue(default_dir.relative_to(self.DOCS_DIR))

        with self.subTest("Custom XDG_CONFIG_HOME"):
            env = {"XDG_CONFIG_HOME": "$HOME/.config/xdg"}
            with mock.patch.dict("drpg.cmd.environ", env, clear=True):
                default_dir = cmd._default_dir()
            self.assertTrue(default_dir.relative_to(self.DOCS_DIR))

    def test_xdg_config_user_dirs(self):
        with self.subTest("The user-dirs.dirs config file exists"):
            with mock.patch("drpg.cmd.open", self.XDG_USER_DIRS_FILE):
                default_dir = cmd._default_dir()
            self.assertTrue(default_dir.relative_to(expandvars(self.DOCS_DIR)))

        with self.subTest("The user-dirs.dirs config file does not exist"):
            with mock.patch("drpg.cmd.open", side_effect=FileNotFoundError):
                default_dir = cmd._default_dir()
            self.assertTrue(default_dir.relative_to(expandvars(self.DOCS_DIR_FALLBACK)))


class WindowsDefaultDirTest(DefaultDirTest, TestCase):
    SYSTEM = "Windows"

    def test_default_dir(self):
        default_dir = cmd._default_dir()
        self.assertEqual(default_dir.parent, Path.home())


class MacDefaultDirTest(DefaultDirTest, TestCase):
    SYSTEM = "Darwin"

    def test_default_dir(self):
        default_dir = cmd._default_dir()
        self.assertEqual(default_dir.parent, Path.cwd())
