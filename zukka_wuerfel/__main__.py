"""CLI-Einstiegspunkt: ``python3 -m zukka_wuerfel``."""

from __future__ import annotations

import argparse
import logging
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

from . import __version__
from .app import RadioApp
from .config import (
    Config,
    ConfigError,
    load_config,
    read_streamer_password,
)
from .encoder import BroadcastEncoder
from .events import (
    AudioLevel,
    ButtonPressed,
    EncoderConnected,
    EncoderError,
    EncoderExited,
)
from .hardware import GpioHardware, HardwareError, NullLights
from .lights import PIP_POSITIONS

DEFAULT_CONFIG = "/etc/zukka-wuerfel/config.toml"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("zukka_wuerfel")

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    if args.input_device:
        config = replace(
            config,
            input=replace(config.input, device=args.input_device),
        )

    if args.check:
        return _check(config, no_gpio=args.no_gpio)

    if not args.no_gpio and config.gpio.button_pin is None:
        log.error("[gpio] button_pin fehlt. Für einen Test ohne Hardware: --no-gpio")
        return 2

    try:
        password = read_streamer_password(config.stream)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    events: queue.Queue[object] = queue.Queue()

    if args.no_gpio:
        lights = NullLights(log)
        _start_stdin_button(events, log)
    else:
        try:
            lights = GpioHardware(
                config.gpio,
                lambda: events.put(ButtonPressed()),
                log,
            )
        except HardwareError as exc:
            log.error("%s", exc)
            return 3

    encoder = BroadcastEncoder(
        config.input,
        config.encoder,
        config.stream,
        password=password,
        event_sink=events.put,
        vu=config.leds.vu and bool(config.gpio.pips),
        connect_timeout=config.behavior.connect_timeout_seconds,
        log=log,
    )
    app = RadioApp(config, encoder, lights, log=log)

    stop = threading.Event()

    def _request_stop(signum: int, _frame: object) -> None:
        if stop.is_set():
            return
        log.info("Signal %s empfangen, beende …", signum)
        app.shutdown()
        stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    log.info(
        "radio zukka Würfel bereit (Konfiguration: %s). LIVE drücken zum Senden.",
        config.source,
    )

    try:
        while not stop.is_set():
            try:
                event = events.get(timeout=0.1)
            except queue.Empty:
                event = None

            if stop.is_set():
                break

            if isinstance(event, ButtonPressed):
                app.on_button()
            elif isinstance(event, EncoderConnected):
                app.on_encoder_connected()
            elif isinstance(event, EncoderError):
                app.on_encoder_error(event.reason)
            elif isinstance(event, EncoderExited):
                app.on_encoder_exited(event.code)
            elif isinstance(event, AudioLevel):
                app.on_audio_level(event.db)

            app.tick()
    finally:
        app.shutdown()
        try:
            lights.show(frozenset(), 0.0)
        except Exception:
            pass
        encoder.close()
        lights.close()
        log.info("Beendet.")

    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="zukka-wuerfel",
        description=(
            "radio zukka LIVE-Würfel: Mischpult-Master als DJ-Stream zu AzuraCast."
        ),
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("ZUKKA_WUERFEL_CONFIG", DEFAULT_CONFIG),
        help=f"Pfad zur TOML-Konfiguration (Standard: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--input-device",
        default=None,
        help='ALSA-Capture-Gerät überschreiben, z. B. "plughw:CARD=Device,DEV=0"',
    )
    parser.add_argument(
        "--no-gpio",
        action="store_true",
        help="ohne GPIO starten (Entwicklung; Enter simuliert den Knopf)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Konfiguration und Voraussetzungen prüfen, dann beenden",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Log-Level (Standard: INFO)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser.parse_args(argv)


def _start_stdin_button(events: queue.Queue[object], log: logging.Logger) -> None:
    """Entwicklungsmodus: jede Enter-Zeile zählt als Knopfdruck."""

    if sys.stdin is None:
        return

    def run() -> None:
        log.info("--no-gpio aktiv: Enter drücken simuliert den LIVE-Knopf.")
        try:
            for _line in sys.stdin:
                events.put(ButtonPressed())
        except (OSError, ValueError):
            pass

    threading.Thread(target=run, name="stdin-button", daemon=True).start()


def _check(config: Config, *, no_gpio: bool) -> int:
    print(f"Konfiguration : {config.source}")
    print(
        f"Eingang       : {config.input.device} "
        f"({config.input.channels} ch, {config.input.sample_rate} Hz)"
    )
    print(
        "AzuraCast     : "
        f"{config.stream.host}:{config.stream.port} "
        f"mount {config.stream.mount} (DJ: {config.stream.username})"
    )
    print(f"Encoding      : MP3 {config.encoder.bitrate} kbps")
    print(f"VU-Pips       : {'an' if config.leds.vu and config.gpio.pips else 'aus'}")
    print(
        "Würfel-Pips   : "
        + (
            ", ".join(
                f"{position}=BCM{pin}"
                for position, pin in zip(PIP_POSITIONS, config.gpio.pips)
            )
            if config.gpio.pips
            else "aus"
        )
    )
    print(
        "LIVE-Knopf    : "
        + (
            f"BCM{config.gpio.button_pin} "
            f"({'active-high' if config.gpio.button_active_high else 'gegen GND'})"
            if config.gpio.button_pin is not None
            else "nicht konfiguriert"
        )
    )
    print(
        "Knopf-LED     : "
        + (
            f"BCM{config.gpio.button_led_pin}"
            if config.gpio.button_led_pin is not None
            else "aus"
        )
    )

    model = Path("/proc/device-tree/model")
    if model.exists():
        try:
            print("Board         : " + model.read_text(errors="ignore").strip("\x00"))
        except OSError:
            pass

    ok = True

    try:
        read_streamer_password(config.stream)
        print(
            f"Streamer-PW   : gesetzt (Umgebungsvariable {config.stream.password_env})"
        )
    except ConfigError as exc:
        print(f"Streamer-PW   : FEHLT – {exc}")
        ok = False

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print("ffmpeg        : FEHLT (sudo apt install ffmpeg)")
        ok = False
    else:
        version = _first_line([ffmpeg, "-version"])
        print(f"ffmpeg        : {ffmpeg}" + (f" ({version})" if version else ""))

    arecord = shutil.which("arecord")
    if arecord is None:
        print("arecord       : FEHLT (sudo apt install alsa-utils)")
        ok = False
    else:
        print("\nCapture-Geräte (arecord -l):")
        devices = _output([arecord, "-l"], timeout=5)
        print(devices.rstrip() if devices else "  (keine Ausgabe)")
        print(f"  Konfiguriert : {config.input.device}")
        if not devices or "card" not in devices.lower():
            print("  Keine Capture-Karte gefunden – USB-Interface/ADC prüfen.")
            ok = False

    try:
        import gpiozero
        from gpiozero import Device

        factory = Device.pin_factory
        print(
            f"\ngpiozero      : {getattr(gpiozero, '__version__', 'vorhanden')} "
            f"(Pin-Factory: {factory})"
        )
        if factory is None or factory.__class__.__name__ == "MockFactory":
            print("                keine echte GPIO-Hardware gefunden")
            if not no_gpio:
                ok = False
    except ImportError:
        print(
            "\ngpiozero      : FEHLT (sudo apt install python3-gpiozero python3-lgpio)"
        )
        if not no_gpio:
            ok = False
    except Exception as exc:
        print(f"\ngpiozero      : FEHLER ({exc})")
        if not no_gpio:
            ok = False

    if not no_gpio and config.gpio.button_pin is None:
        print(
            "\nHinweis       : Kein button_pin konfiguriert (nur mit --no-gpio startbar)."
        )
        ok = False

    return 0 if ok else 1


def _first_line(command: list[str]) -> str | None:
    output = _output(command, timeout=5)
    if not output:
        return None
    return output.splitlines()[0].strip()


def _output(command: list[str], *, timeout: float) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (result.stdout or "") + (result.stderr or "")


if __name__ == "__main__":
    raise SystemExit(main())
