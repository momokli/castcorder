"""ffmpeg-Audio-Capture und Icecast-Source-Client für AzuraCast.

Das Castcorder sendet bewusst selbst die Icecast-Source-Anfrage (``SOURCE /…``),
statt eine ``icecast://``-URL an ffmpeg zu geben. Das hat zwei Vorteile:

* Das Streamer-Passwort landet nie in der Prozessliste (``ps``).
* AzuraCast/Liquidsoap akzeptiert auch den Mountpoint ``/``, den ffmpegs
  eingebauter Icecast-Client ablehnt.
"""

from __future__ import annotations

import base64
import logging
import math
import re
import signal
import socket
import ssl
import subprocess
import threading
import time
from typing import Callable
from urllib.parse import quote

from .config import EncoderConfig, InputConfig, StreamConfig
from .events import AudioLevel, EncoderConnected, EncoderError, EncoderExited

USER_AGENT = "castcorder/0.1"

_LEVEL_RE = re.compile(
    r"lavfi\.astats\.Overall\.Peak_level=(-?(?:\d+(?:\.\d+)?|inf|nan))",
    re.IGNORECASE,
)


class EncoderFailure(RuntimeError):
    """Capture oder Icecast-Verbindung fehlgeschlagen."""


def build_ffmpeg_command(
    input_cfg: InputConfig,
    encoder_cfg: EncoderConfig,
    *,
    vu: bool,
    binary: str = "ffmpeg",
) -> list[str]:
    """Baut die ffmpeg-Kommandozeile (pur, damit testbar)."""

    command = [
        binary,
        "-hide_banner",
        "-nostdin",
        "-nostats",
        "-loglevel",
        "info" if vu else "warning",
        "-thread_queue_size",
        "1024",
        *input_cfg.extra_args,
        "-f",
        "alsa",
        "-i",
        input_cfg.device,
        "-ac",
        str(input_cfg.channels),
        "-ar",
        str(input_cfg.sample_rate),
    ]
    if vu:
        command += [
            "-af",
            "astats=metadata=1:reset=10,"
            "ametadata=print:key=lavfi.astats.Overall.Peak_level",
        ]
    command += [
        "-c:a",
        "libmp3lame",
        "-b:a",
        f"{encoder_cfg.bitrate}k",
        "-flush_packets",
        "1",
        *encoder_cfg.extra_args,
        "-f",
        "mp3",
        "pipe:1",
    ]
    return command


def parse_level(line: str) -> float | None:
    """Liest den Peak-Pegel aus einer ffmpeg-``astats``-Logzeile."""

    match = _LEVEL_RE.search(line)
    if match is None:
        return None
    raw = match.group(1).lower()
    if raw in {"-inf", "nan"}:
        return -120.0
    if raw in {"inf", "+inf"}:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _source_path(mount: str) -> str:
    path = mount.strip() or "/"
    if not path.startswith("/"):
        path = "/" + path
    return quote(path, safe="/")


class IcecastSource:
    """Minimaler Icecast-2-Source-Client (SOURCE + Basic Auth + MP3-Body)."""

    def __init__(
        self,
        stream: StreamConfig,
        *,
        password: str,
        bitrate: int,
        channels: int = 2,
        sample_rate: int = 44100,
        connect_timeout: float = 10.0,
        io_timeout: float = 10.0,
        log: logging.Logger | None = None,
    ) -> None:
        self.stream = stream
        self._password = password
        self._bitrate = bitrate
        self._channels = channels
        self._sample_rate = sample_rate
        self._connect_timeout = connect_timeout
        self._io_timeout = io_timeout
        self.log = log or logging.getLogger("castcorder")
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        path = _source_path(self.stream.mount)
        try:
            raw = socket.create_connection(
                (self.stream.host, self.stream.port),
                timeout=self._connect_timeout,
            )
        except OSError as exc:
            raise EncoderFailure(
                f"Keine Verbindung zu {self.stream.host}:{self.stream.port}: {exc}"
            ) from exc

        if self.stream.tls:
            try:
                raw = ssl.create_default_context().wrap_socket(
                    raw, server_hostname=self.stream.host
                )
            except OSError as exc:
                raw.close()
                raise EncoderFailure(f"TLS-Verbindung fehlgeschlagen: {exc}") from exc

        raw.settimeout(self._connect_timeout)
        self._sock = raw

        request = self._request(path)
        try:
            raw.sendall(request)
            status, status_line = self._read_response(raw)
        except OSError as exc:
            self.close()
            raise EncoderFailure(f"Keine Antwort vom Icecast-Server: {exc}") from exc

        if status != 200:
            self.close()
            raise EncoderFailure(
                f"Icecast hat die Quelle abgelehnt ({status_line}). "
                "Benutzername/Passwort/Port/Mountpoint prüfen."
            )

        raw.settimeout(self._io_timeout)
        self.log.info(
            "Icecast-Quelle akzeptiert: %s:%s%s (%s)",
            self.stream.host,
            self.stream.port,
            path,
            status_line,
        )

    def send(self, data: bytes) -> None:
        if self._sock is None:
            raise EncoderFailure("Icecast-Verbindung ist nicht offen")
        try:
            self._sock.sendall(data)
        except OSError as exc:
            raise EncoderFailure(f"Stream-Verbindung verloren: {exc}") from exc

    def close(self) -> None:
        sock, self._sock = self._sock, None
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def _request(self, path: str) -> bytes:
        credentials = base64.b64encode(
            f"{self.stream.username}:{self._password}".encode("utf-8")
        ).decode("ascii")
        headers = [
            f"SOURCE {path} HTTP/1.0",
            f"Host: {self.stream.host}:{self.stream.port}",
            "Content-Type: audio/mpeg",
            f"Authorization: Basic {credentials}",
            f"User-Agent: {USER_AGENT}",
            f"Ice-Bitrate: {self._bitrate}",
            f"Ice-Public: {1 if self.stream.public else 0}",
            "Ice-Audio-Info: "
            f"ice-bitrate={self._bitrate};ice-channels={self._channels};"
            f"ice-samplerate={self._sample_rate}",
        ]
        for key, value in (
            ("Ice-Name", self.stream.name),
            ("Ice-Description", self.stream.description),
            ("Ice-Genre", self.stream.genre),
            ("Ice-Url", self.stream.url),
        ):
            if value:
                headers.append(f"{key}: {value}")
        return ("\r\n".join(headers) + "\r\n\r\n").encode("utf-8")

    def _read_response(self, sock: socket.socket) -> tuple[int, str]:
        deadline = time.monotonic() + self._connect_timeout
        buffer = b""

        while True:
            if b"\r\n\r\n" in buffer:
                head, _, rest = buffer.partition(b"\r\n\r\n")
                lines = head.decode("latin-1").split("\r\n")
                status_line = lines[0].strip() if lines else ""
                match = re.match(r"HTTP/\d(?:\.\d)?\s+(\d{3})", status_line)
                if match is None:
                    raise EncoderFailure(f"Ungültige Icecast-Antwort: {status_line!r}")
                status = int(match.group(1))
                if status == 100:
                    buffer = rest
                    continue
                return status, status_line

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EncoderFailure("Zeitüberschreitung beim Icecast-Login")
            sock.settimeout(remaining)
            chunk = sock.recv(4096)
            if not chunk:
                raise EncoderFailure("Icecast-Server hat die Verbindung geschlossen")
            buffer += chunk
            if len(buffer) > 65536:
                raise EncoderFailure("Icecast-Antwort ist zu groß")


class BroadcastEncoder:
    """Startet ffmpeg und schickt dessen MP3-Ausgabe an AzuraCast."""

    def __init__(
        self,
        input_cfg: InputConfig,
        encoder_cfg: EncoderConfig,
        stream_cfg: StreamConfig,
        *,
        password: str,
        event_sink: Callable[[object], None],
        vu: bool = True,
        connect_timeout: float = 10.0,
        binary: str = "ffmpeg",
        log: logging.Logger | None = None,
    ) -> None:
        self.input = input_cfg
        self.encoder = encoder_cfg
        self.stream = stream_cfg
        self._password = password
        self._event_sink = event_sink
        self._vu = vu
        self._connect_timeout = connect_timeout
        self._binary = binary
        self.log = log or logging.getLogger("castcorder")

        self._lock = threading.Lock()
        self._generation = 0
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._source: IcecastSource | None = None

    def start(self) -> None:
        self.stop()
        stop_event = threading.Event()
        with self._lock:
            self._stop_event = stop_event
            self._generation += 1
            generation = self._generation
            self._thread = threading.Thread(
                target=self._run,
                args=(generation, stop_event),
                name="encoder",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            stop_event = self._stop_event
            self._generation += 1
            source = self._source
            proc = self._proc
            thread = self._thread

        if stop_event is not None:
            stop_event.set()
        if source is not None:
            source.close()
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
            except OSError:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
            if thread.is_alive():
                if proc is not None and proc.poll() is None:
                    try:
                        proc.kill()
                        proc.wait(timeout=1.0)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                thread.join(timeout=1.0)
            if thread.is_alive():
                self.log.warning("Encoder-Thread reagiert nicht auf Stop.")

        with self._lock:
            if self._thread is thread:
                self._thread = None
            if self._stop_event is stop_event:
                self._stop_event = None
            if self._source is source:
                self._source = None
            if self._proc is proc:
                self._proc = None

    def close(self) -> None:
        self.stop()

    # ----------------------------------------------------------------- private

    def _run(self, generation: int, stop_event: threading.Event) -> None:
        proc: subprocess.Popen | None = None
        source: IcecastSource | None = None
        stderr_thread: threading.Thread | None = None

        try:
            if stop_event.is_set() or generation != self._generation:
                return

            command = build_ffmpeg_command(
                self.input,
                self.encoder,
                vu=self._vu,
                binary=self._binary,
            )
            self.log.debug("Starte ffmpeg: %s", " ".join(command))
            try:
                proc = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
            except FileNotFoundError as exc:
                raise EncoderFailure(
                    "ffmpeg ist nicht installiert (sudo apt install ffmpeg)"
                ) from exc
            except OSError as exc:
                raise EncoderFailure(
                    f"ffmpeg konnte nicht gestartet werden: {exc}"
                ) from exc

            with self._lock:
                self._proc = proc
            stderr_thread = threading.Thread(
                target=self._read_stderr,
                args=(proc, generation, stop_event),
                name="ffmpeg-stderr",
                daemon=True,
            )
            stderr_thread.start()

            source = IcecastSource(
                self.stream,
                password=self._password,
                bitrate=self.encoder.bitrate,
                channels=self.input.channels,
                sample_rate=self.input.sample_rate,
                connect_timeout=self._connect_timeout,
                log=self.log,
            )
            with self._lock:
                self._source = source

            if stop_event.is_set() or generation != self._generation:
                return

            # Erst Audio prüfen, dann die Quelle bei AzuraCast anmelden:
            # so wird kein "live"-Webhook ausgelöst, wenn der Eingang fehlt.
            first = proc.stdout.read(8192) if proc.stdout is not None else b""
            if not first:
                code = proc.poll()
                raise EncoderFailure(
                    f"ffmpeg liefert keine Audiodaten (Code {code}). "
                    "Eingabegerät prüfen (arecord -l)."
                )
            if stop_event.is_set() or generation != self._generation:
                return

            source.connect()
            if stop_event.is_set() or generation != self._generation:
                return
            self._emit(EncoderConnected(), generation, stop_event)
            source.send(first)

            while not stop_event.is_set():
                chunk = proc.stdout.read(8192) if proc.stdout is not None else b""
                if not chunk:
                    break
                source.send(chunk)

            code = proc.poll()
            if code is None:
                try:
                    code = proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    code = None
            if not stop_event.is_set() and generation == self._generation:
                self._emit(EncoderExited(code), generation, stop_event)
        except Exception as exc:
            if not stop_event.is_set() and generation == self._generation:
                self._emit(
                    EncoderError(str(exc) or exc.__class__.__name__),
                    generation,
                    stop_event,
                )
        finally:
            if source is not None:
                source.close()
                with self._lock:
                    if self._source is source:
                        self._source = None
            if proc is not None:
                if proc.poll() is None:
                    try:
                        proc.send_signal(signal.SIGINT)
                        proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        try:
                            proc.wait(timeout=1.0)
                        except subprocess.TimeoutExpired:
                            self.log.warning("ffmpeg reagiert nicht auf SIGKILL")
                    except OSError:
                        pass
                try:
                    proc.wait(timeout=1.0)
                except (subprocess.TimeoutExpired, OSError):
                    pass
                if stderr_thread is not None:
                    stderr_thread.join(timeout=1.0)
                for pipe in (proc.stdout, proc.stderr):
                    if pipe is not None:
                        try:
                            pipe.close()
                        except OSError:
                            pass
                with self._lock:
                    if self._proc is proc:
                        self._proc = None

    def _read_stderr(
        self,
        proc: subprocess.Popen,
        generation: int,
        stop_event: threading.Event,
    ) -> None:
        if proc.stderr is None:
            return
        for raw in proc.stderr:
            if stop_event.is_set() or generation != self._generation:
                return
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            level = parse_level(line)
            if level is not None:
                self._emit(AudioLevel(level), generation, stop_event)
                continue
            lowered = line.lower()
            if any(
                word in lowered
                for word in ("error", "failed", "cannot", "unable", "denied")
            ):
                self.log.warning("ffmpeg: %s", line)
            else:
                self.log.debug("ffmpeg: %s", line)

    def _emit(
        self,
        event: object,
        generation: int,
        stop_event: threading.Event,
    ) -> None:
        if stop_event.is_set() or generation != self._generation:
            return
        try:
            self._event_sink(event)
        except Exception:
            self.log.exception("Event konnte nicht verarbeitet werden")
