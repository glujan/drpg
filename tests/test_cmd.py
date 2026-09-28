import logging
import tempfile
import threading
from inspect import currentframe
from os.path import expandvars
from pathlib import Path
from signal import SIGTERM
from unittest import TestCase, mock

from httpx import URL

from drpg import cmd
from drpg.config import Config


class ParseCliTest(TestCase):
    @mock.patch("drpg.cmd.argparse.ArgumentParser.error")
    def test_has_required_params(self, error_mock):
        # Because otherwise this breaks with environments that already have things set
        cmd.environ.clear()
        cmd._parse_cli([])
        error_mock.assert_called_once()

    def test_defaults_from_env(self):
        env = {
            "DRPG_TOKEN": "env-token",
            "DRPG_LIBRARY_PATH": "env/path",
            "DRPG_LOG_LEVEL": "DEBUG",
            "DRPG_USE_CHECKSUMS": "true",
            "DRPG_VALIDATE": "true",
            "DRPG_DRY_RUN": "true",
            "DRPG_THREADS": "1",
            "DRPG_COMPATIBILITY_MODE": "true",
            "DRPG_OMIT_PUBLISHER": "false",
            "DRPG_NO_CHECK": "true",
        }

        with mock.patch.dict(cmd.environ, env):
            config = cmd._parse_cli([])

        self.assertEqual(config.token, env["DRPG_TOKEN"])
        self.assertEqual(config.library_path, Path(env["DRPG_LIBRARY_PATH"]))
        self.assertEqual(config.log_level, env["DRPG_LOG_LEVEL"])
        self.assertTrue(config.use_checksums)
        self.assertTrue(config.validate)
        self.assertTrue(config.dry_run)
        self.assertEqual(config.threads, int(env["DRPG_THREADS"]))
        self.assertTrue(config.compatibility_mode)
        self.assertFalse(config.omit_publisher)
        self.assertFalse(config.do_check)

    @mock.patch("drpg.cmd.argparse.ArgumentParser.error")
    def test_compability_mutually_exclusive_group(self, error_mock):
        cmd._parse_cli(["--compatibility-mode", "--omit-publisher", "--token", "mock_token"])
        error_mock.assert_called()

    def test_config_file_parse(self):
        config = cmd._parse_cli(
            ["--config", Path(__file__).parent.joinpath("test_config.ini").as_posix()]
        )
        assert config == Config(
            token="supersecrettoken",
            library_path=Path("/a/nother/path"),
            use_checksums=True,
            validate=True,
            log_level="DEBUG",
            dry_run=True,
            compatibility_mode=True,
            omit_publisher=False,
            threads=10,
        ), config

    @mock.patch("drpg.cmd.argparse.ArgumentParser.error")
    def test_config_file_bad_parse(self, error_mock: mock.MagicMock):
        test_config_path = Path(__file__).parent.joinpath("test_config.ini")
        with tempfile.NamedTemporaryFile(mode="w") as bad_config_file:
            bad_config_file.write(test_config_path.open().read())
            bad_config_file.write("\nextra_arg=foo\n")
            bad_config_file.flush()
            cmd._parse_cli(["--config", bad_config_file.name])
            error_mock.assert_any_call("argument --config: Unsupported config keys: extra_arg")


class SignalHandlerTest(TestCase):
    @mock.patch("drpg.cmd.sys.exit")
    def test_exits(self, m_exit):
        cmd._shutdown_event = threading.Event()
        cmd._handle_signal(SIGTERM, currentframe())
        m_exit.assert_called_once_with(0)


class ExceptionHandlerTest(TestCase):
    @mock.patch("drpg.cmd.logging.getLogger")
    def test_excepthook(self, m_getLogger: mock.MagicMock):
        m_logger = mock.MagicMock()
        m_getLogger.return_value = m_logger
        cmd._excepthook(Exception, Exception(), None)
        m_getLogger.assert_called_once_with("drpg")
        m_logger.error.assert_called_once_with("Unexpected error occurred, stopping!")
        m_logger.info.assert_called_once_with("Exception\n")


class SetLogLevels(TestCase):
    def test_debug(self):
        cmd._set_httpx_log_level(logging.DEBUG)
        self.assertEqual(logging.getLogger("httpx").level, logging.DEBUG)
        self.assertEqual(logging.getLogger("httpcore").level, logging.INFO)
        self.assertEqual(logging.getLogger("hpack").level, logging.INFO)

    def test_more_than_debug(self):
        for level in (logging.INFO, logging.WARNING, logging.ERROR):
            with self.subTest(level=level):
                cmd._set_httpx_log_level(level)
                self.assertEqual(logging.getLogger("httpx").level, logging.WARNING)
                self.assertEqual(logging.getLogger("httpcore").level, logging.WARNING)
                self.assertEqual(logging.getLogger("hpack").level, logging.WARNING)

    def clear_handlers(self):
        # In the actual app, we only ever call basic_config once, but we need to support calling it
        # multiple times in tests. So clear out the root handlers first. Code is as per the
        # force=True arg for basic_config.
        for h in logging.root.handlers:
            logging.root.removeHandler(h)
            h.close()

    def test_setup_logger_debug(self):
        self.clear_handlers()
        cmd._setup_logger("DEBUG")
        self.assertEqual(logging.root.level, logging.DEBUG)
        self.assertEqual(logging.getLogger("httpx").level, logging.DEBUG)

    def test_setup_logger_warn(self):
        self.clear_handlers()
        cmd._setup_logger("WARNING")
        self.assertEqual(logging.root.level, logging.WARNING)
        self.assertEqual(logging.getLogger("httpx").level, logging.WARNING)


class DefaultDirTest:
    SYSTEM: str

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


class ApplicationKeyFilterTest(TestCase):
    def test_matching_record(self):
        secret = "123456789012345"
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname="dummy.py",
            lineno=10,
            msg="Http request: %s %s %s",
            args=(
                "POST",
                URL(f"https://example.org/?test=1&applicationKey={secret}&dummy=max"),
                "irrelevant",
            ),
            exc_info=None,
        )

        self.assertIn(secret, record.getMessage())
        self.assertTrue(cmd.application_key_filter(record))
        self.assertNotIn(secret, record.getMessage())

    def test_not_matching_record(self):
        secret = "123456789012345"
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname="dummy.py",
            lineno=10,
            msg="Http request: %s %s %s",
            args=(
                "POST",
                URL(f"https://example.org/?test=1&secret={secret}&dummy=max"),
                "irrelevant",
            ),
            exc_info=None,
        )

        self.assertIn(secret, record.getMessage())
        self.assertTrue(cmd.application_key_filter(record))
        self.assertIn(secret, record.getMessage())

    def test_silent_exception(self):
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname="dummy.py",
            lineno=10,
            msg="Log line without params",
            args=None,
            exc_info=None,
        )

        self.assertTrue(cmd.application_key_filter(record))
