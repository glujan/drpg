from inspect import currentframe
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
