from __future__ import annotations

import queue
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from castcorder.config import EncoderConfig, InputConfig, StreamConfig
from castcorder.encoder import (
    BroadcastEncoder,
    EncoderFailure,
    IcecastSource,
    build_ffmpeg_command,
    parse_level,
)
from castcorder.events import AudioLevel, EncoderConnected
from castcorder.events import EncoderError as EncoderErrorEvent

FAKE_FFMPEG = """#!/usr/bin/env python3
import signal
import sys
import time

def stop(*_):
    sys.exit(0)

signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

while True:
    sys.stdout.buffer.write(b"ID3FAKE" * 512)
    sys.stdout.buffer.flush()
    print("lavfi.astats.Overall.Peak_level=-12.5", file=sys.stderr, flush=True)
    time.sleep(0.05)
"""


class FakeIcecastServer:
    def __init__(self, response: bytes = b"HTTP/1.0 200 OK\r\n\r\n") -> None:
        self.response = response
        self.request = b""
        self.received = bytearray()
        self._lock = threading.Lock()
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(1)
        self.port = self._server.getsockname()[1]
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            connection, _ = self._server.accept()
        except OSError:
            return
        connection.settimeout(3.0)
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = connection.recv(4096)
                if not chunk:
                    return
                request += chunk
            self.request = request
            connection.sendall(self.response)
            while True:
                try:
                    chunk = connection.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                with self._lock:
                    self.received.extend(chunk)
        except OSError:
            pass
        finally:
            connection.close()

    def close(self) -> None:
        try:
            self._server.close()
        except OSError:
            pass
        self._thread.join(timeout=2.0)


class FfmpegCommandTests(unittest.TestCase):
    def test_command_contains_capture_and_mp3(self) -> None:
        command = build_ffmpeg_command(
            InputConfig(device="plughw:CARD=Device,DEV=0"),
            EncoderConfig(bitrate=192),
            vu=True,
        )
        self.assertIn("-f", command)
        self.assertIn("alsa", command)
        self.assertIn("plughw:CARD=Device,DEV=0", command)
        self.assertIn("libmp3lame", command)
        self.assertIn("192k", command)
        self.assertIn("pipe:1", command)
        self.assertTrue(any("astats" in arg for arg in command))

    def test_vu_off_omits_astats(self) -> None:
        command = build_ffmpeg_command(
            InputConfig(device="test"),
            EncoderConfig(bitrate=128),
            vu=False,
        )
        self.assertFalse(any("astats" in arg for arg in command))
        self.assertIn("warning", command)

    def test_extra_args_are_appended(self) -> None:
        command = build_ffmpeg_command(
            InputConfig(device="test"),
            EncoderConfig(bitrate=192, extra_args=("--foo", "bar")),
            vu=False,
        )
        self.assertLess(command.index("--foo"), command.index("pipe:1"))
        self.assertIn("bar", command)


class LevelParseTests(unittest.TestCase):
    def test_parses_peak(self) -> None:
        line = "[Parsed_ametadata_1 @ 0x123] lavfi.astats.Overall.Peak_level=-18.063656"
        self.assertAlmostEqual(parse_level(line), -18.063656)

    def test_silence_is_very_low(self) -> None:
        self.assertEqual(parse_level("lavfi.astats.Overall.Peak_level=-inf"), -120.0)
        self.assertEqual(parse_level("lavfi.astats.Overall.Peak_level=nan"), -120.0)

    def test_other_lines_are_ignored(self) -> None:
        self.assertIsNone(parse_level("Input #0, alsa, from 'plughw:...'"))


class IcecastSourceTests(unittest.TestCase):
    def make_source(self, server: FakeIcecastServer, mount: str = "/") -> IcecastSource:
        return IcecastSource(
            StreamConfig(
                host="127.0.0.1",
                port=server.port,
                mount=mount,
                username="momo",
            ),
            password="secret",
            bitrate=192,
            connect_timeout=2.0,
        )

    def test_source_request_and_body(self) -> None:
        server = FakeIcecastServer()
        source = self.make_source(server)
        try:
            source.connect()
            source.send(b"mp3-bytes")
            deadline = time.monotonic() + 2.0
            while not server.received and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIn(b"SOURCE / HTTP/1.0\r\n", server.request)
            self.assertIn(
                b"Authorization: Basic bW9tbzpzZWNyZXQ=",
                server.request,
            )
            self.assertIn(b"Content-Type: audio/mpeg", server.request)
            self.assertIn(b"mp3-bytes", bytes(server.received))
        finally:
            source.close()
            server.close()

    def test_mount_without_slash_is_prefixed(self) -> None:
        server = FakeIcecastServer()
        source = self.make_source(server, mount="radio.mp3")
        try:
            source.connect()
            self.assertIn(b"SOURCE /radio.mp3 HTTP/1.0", server.request)
        finally:
            source.close()
            server.close()

    def test_wrong_password_is_reported(self) -> None:
        server = FakeIcecastServer(b"HTTP/1.0 401 Unauthorized\r\n\r\n")
        source = self.make_source(server)
        try:
            with self.assertRaisesRegex(EncoderFailure, "abgelehnt"):
                source.connect()
        finally:
            source.close()
            server.close()

    def test_continue_response_is_handled(self) -> None:
        server = FakeIcecastServer(
            b"HTTP/1.0 100 Continue\r\n\r\nHTTP/1.0 200 OK\r\n\r\n"
        )
        source = self.make_source(server)
        try:
            source.connect()
        finally:
            source.close()
            server.close()


class BroadcastEncoderTests(unittest.TestCase):
    def test_end_to_end_with_fake_ffmpeg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "fake-ffmpeg"
            binary.write_text(FAKE_FFMPEG, encoding="utf-8")
            binary.chmod(0o755)

            server = FakeIcecastServer()
            events: queue.Queue[object] = queue.Queue()
            encoder = BroadcastEncoder(
                InputConfig(device="test"),
                EncoderConfig(bitrate=192),
                StreamConfig(
                    host="127.0.0.1",
                    port=server.port,
                    mount="/",
                    username="momo",
                ),
                password="secret",
                event_sink=events.put,
                vu=True,
                connect_timeout=2.0,
                binary=str(binary),
            )
            try:
                encoder.start()
                self._wait_for(
                    events, lambda event: isinstance(event, EncoderConnected)
                )
                level = self._wait_for(
                    events, lambda event: isinstance(event, AudioLevel)
                )
                time.sleep(0.2)
                self.assertIn(b"SOURCE / HTTP/1.0", server.request)
                self.assertGreater(len(server.received), 0)
                self.assertAlmostEqual(level.db, -12.5)
            finally:
                encoder.stop()
                server.close()

    def test_rejected_source_emits_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "fake-ffmpeg"
            binary.write_text(FAKE_FFMPEG, encoding="utf-8")
            binary.chmod(0o755)

            server = FakeIcecastServer(b"HTTP/1.0 401 Unauthorized\r\n\r\n")
            events: queue.Queue[object] = queue.Queue()
            encoder = BroadcastEncoder(
                InputConfig(device="test"),
                EncoderConfig(bitrate=192),
                StreamConfig(
                    host="127.0.0.1",
                    port=server.port,
                    mount="/",
                    username="momo",
                ),
                password="secret",
                event_sink=events.put,
                connect_timeout=2.0,
                binary=str(binary),
            )
            try:
                encoder.start()
                error = self._wait_for(
                    events, lambda event: isinstance(event, EncoderErrorEvent)
                )
                self.assertIn("abgelehnt", error.reason)
                self.assertNotIn("secret", error.reason)
            finally:
                encoder.stop()
                server.close()

    @staticmethod
    def _wait_for(
        events: queue.Queue[object],
        predicate,
        timeout: float = 5.0,
    ):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if predicate(event):
                return event
        raise AssertionError("erwartetes Encoder-Event blieb aus")


if __name__ == "__main__":
    unittest.main()
