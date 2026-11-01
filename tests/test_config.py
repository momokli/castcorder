from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from castcorder.config import (
    DEFAULT_PASSWORD_ENV,
    ConfigError,
    load_config,
    read_streamer_password,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "config.example.toml"

BASE = """
[input]
device = "plughw:CARD=Device,DEV=0"

[stream]
host = "cast.example.org"
port = 8005
mount = "/"
username = "momo"
password_env = "TEST_STREAMER_PASSWORD"

[gpio]
button_pin = 17
vu_leds = [5, 6, 16, 22, 23, 24, 25]
"""


class ConfigTests(unittest.TestCase):
    def load(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(text, encoding="utf-8")
            return load_config(path)

    def test_base_config(self) -> None:
        cfg = self.load(BASE)
        self.assertEqual(cfg.input.device, "plughw:CARD=Device,DEV=0")
        self.assertEqual(cfg.stream.username, "momo")
        self.assertEqual(cfg.stream.mount, "/")
        self.assertEqual(cfg.encoder.bitrate, 192)
        self.assertTrue(cfg.leds.vu)
        self.assertEqual(cfg.gpio.button_pin, 17)

    def test_example_config_is_valid(self) -> None:
        cfg = load_config(EXAMPLE)
        self.assertEqual(cfg.stream.host, "cast.zukkafabrik.de")
        self.assertEqual(cfg.stream.port, 8005)
        self.assertEqual(cfg.gpio.button_pin, 17)
        self.assertEqual(len(cfg.gpio.vu_leds), 7)

    def test_missing_device_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "device"):
            self.load('[stream]\nusername = "momo"\n')

    def test_missing_username_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "username"):
            self.load(BASE.replace('username = "momo"', 'username = ""'))

    def test_mount_is_normalized(self) -> None:
        cfg = self.load(BASE.replace('mount = "/"', 'mount = "radio.mp3"'))
        self.assertEqual(cfg.stream.mount, "/radio.mp3")
        cfg = self.load(BASE.replace('mount = "/"', 'mount = ""'))
        self.assertEqual(cfg.stream.mount, "/")

    def test_host_scheme_is_normalized(self) -> None:
        cfg = self.load(
            BASE.replace(
                'host = "cast.example.org"',
                'host = "https://cast.example.org/"',
            )
        )
        self.assertEqual(cfg.stream.host, "cast.example.org")

    def test_unknown_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "Unbekannte"):
            self.load(BASE.replace("port = 8005", "port = 8005\nbogus = 1"))

    def test_vu_leds_need_seven_entries(self) -> None:
        with self.assertRaisesRegex(ConfigError, "genau 7"):
            self.load(
                BASE.replace(
                    "vu_leds = [5, 6, 16, 22, 23, 24, 25]",
                    "vu_leds = [5, 6, 16]",
                )
            )

    def test_duplicate_pins_are_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "doppelt belegt"):
            self.load(
                BASE.replace(
                    "vu_leds = [5, 6, 16, 22, 23, 24, 25]",
                    "vu_leds = [5, 6, 16, 22, 23, 24, 17]",
                )
            )

    def test_invalid_bitrate_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "bitrate"):
            self.load(BASE + "\n[encoder]\nbitrate = 999\n")

    def test_invalid_port_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "port"):
            self.load(BASE.replace("port = 8005", "port = 70000"))

    def test_username_with_colon_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "username"):
            self.load(BASE.replace('username = "momo"', 'username = "mo:mo"'))

    def test_header_newlines_are_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "Zeilenumbrüche"):
            self.load(
                BASE.replace('username = "momo"', 'username = "momo"\nname = "a\\nb"')
            )

    def test_invalid_vu_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "vu_min_db"):
            self.load(BASE + "\n[leds]\nvu_min_db = 0\nvu_max_db = -10\n")

    def test_password_from_environment(self) -> None:
        cfg = self.load(BASE)
        with mock.patch.dict(
            os.environ, {"TEST_STREAMER_PASSWORD": "geheim"}, clear=False
        ):
            self.assertEqual(read_streamer_password(cfg.stream), "geheim")

    def test_missing_password_is_reported(self) -> None:
        cfg = self.load(BASE)
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigError, "TEST_STREAMER_PASSWORD"):
                read_streamer_password(cfg.stream)

    def test_default_password_env_name(self) -> None:
        self.assertEqual(DEFAULT_PASSWORD_ENV, "CASTCORDER_STREAMER_PASSWORD")
        cfg = self.load(BASE.replace('password_env = "TEST_STREAMER_PASSWORD"', ""))
        self.assertEqual(cfg.stream.password_env, "CASTCORDER_STREAMER_PASSWORD")

    def test_password_from_default_environment(self) -> None:
        cfg = self.load(BASE.replace('password_env = "TEST_STREAMER_PASSWORD"', ""))
        with mock.patch.dict(
            os.environ, {"CASTCORDER_STREAMER_PASSWORD": "neu"}, clear=True
        ):
            self.assertEqual(read_streamer_password(cfg.stream), "neu")

    def test_missing_file(self) -> None:
        with self.assertRaisesRegex(ConfigError, "nicht gefunden"):
            load_config("/definitely/not/here.toml")


if __name__ == "__main__":
    unittest.main()
