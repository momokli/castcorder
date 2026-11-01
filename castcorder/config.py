"""Konfiguration aus TOML laden und validieren."""

from __future__ import annotations

import math
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .lights import VU_POSITIONS

DEFAULT_STREAM_HOST = "cast.zukkafabrik.de"
DEFAULT_STREAM_PORT = 8005
DEFAULT_MOUNT = "/"
DEFAULT_PASSWORD_ENV = "CASTCORDER_STREAMER_PASSWORD"


class ConfigError(ValueError):
    """Die Konfigurationsdatei ist unbrauchbar."""


@dataclass(frozen=True)
class InputConfig:
    """Audio-Eingang (Mischpult-Master über USB-Interface oder ADC-HAT)."""

    device: str = ""
    sample_rate: int = 44100
    channels: int = 2
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class StreamConfig:
    """Icecast-Source-Zugang von AzuraCast (Streamers/DJs → Icecast Clients)."""

    host: str = DEFAULT_STREAM_HOST
    port: int = DEFAULT_STREAM_PORT
    mount: str = DEFAULT_MOUNT
    username: str = ""
    password_env: str = DEFAULT_PASSWORD_ENV
    tls: bool = False
    name: str = "radio zukka"
    description: str = "Live from the Castcorder"
    genre: str = ""
    url: str = "https://radio.zukkafabrik.de"
    public: bool = False


@dataclass(frozen=True)
class EncoderConfig:
    bitrate: int = 192
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class LedsConfig:
    vu: bool = True
    vu_min_db: float = -48.0
    vu_max_db: float = 0.0
    vu_decay_per_second: float = 8.0


@dataclass(frozen=True)
class GpioConfig:
    button_pin: int | None = None
    button_led_pin: int | None = None
    button_active_high: bool = False
    button_bounce_time: float = 0.05
    vu_leds: tuple[int, ...] = ()


@dataclass(frozen=True)
class BehaviorConfig:
    connect_timeout_seconds: float = 20.0
    retry_delay_seconds: float = 8.0
    max_retries: int = 3
    min_connecting_display_seconds: float = 0.9


@dataclass(frozen=True)
class Config:
    input: InputConfig = field(default_factory=InputConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    encoder: EncoderConfig = field(default_factory=EncoderConfig)
    leds: LedsConfig = field(default_factory=LedsConfig)
    gpio: GpioConfig = field(default_factory=GpioConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    source: Path | None = None


_TOP_LEVEL = {"input", "stream", "encoder", "leds", "gpio", "behavior"}
_INPUT_KEYS = {"device", "sample_rate", "channels", "extra_args"}
_STREAM_KEYS = {
    "host",
    "port",
    "mount",
    "username",
    "password_env",
    "tls",
    "name",
    "description",
    "genre",
    "url",
    "public",
}
_ENCODER_KEYS = {"bitrate", "extra_args"}
_LEDS_KEYS = {"vu", "vu_min_db", "vu_max_db", "vu_decay_per_second"}
_GPIO_KEYS = {
    "button_pin",
    "button_led_pin",
    "button_active_high",
    "button_bounce_time",
    "vu_leds",
}
_BEHAVIOR_KEYS = {
    "connect_timeout_seconds",
    "retry_delay_seconds",
    "max_retries",
    "min_connecting_display_seconds",
}


def load_config(path: str | Path) -> Config:
    """Lädt und validiert ``path``. Wirft bei Fehlern :class:`ConfigError`."""

    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Konfiguration nicht gefunden: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"Konfiguration nicht lesbar ({path}): {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Ungültiges TOML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: erwartet wird eine TOML-Tabelle")

    unknown = sorted(set(raw) - _TOP_LEVEL)
    if unknown:
        raise ConfigError(
            f"Unbekannte Tabelle(n) in {path}: {', '.join(unknown)} "
            f"(erlaubt: {', '.join(sorted(_TOP_LEVEL))})"
        )

    input_raw = _section(raw, "input", _INPUT_KEYS)
    stream_raw = _section(raw, "stream", _STREAM_KEYS)
    encoder_raw = _section(raw, "encoder", _ENCODER_KEYS)
    leds_raw = _section(raw, "leds", _LEDS_KEYS)
    gpio_raw = _section(raw, "gpio", _GPIO_KEYS)
    behavior_raw = _section(raw, "behavior", _BEHAVIOR_KEYS)

    cfg = Config(
        input=InputConfig(
            device=_string(input_raw, "device", "", where="[input]"),
            sample_rate=_int(
                input_raw,
                "sample_rate",
                44100,
                where="[input]",
                minimum=8000,
                maximum=192000,
            ),
            channels=_int(
                input_raw, "channels", 2, where="[input]", minimum=1, maximum=2
            ),
            extra_args=_string_list(input_raw, "extra_args", where="[input]"),
        ),
        stream=StreamConfig(
            host=_stream_host(
                _string(stream_raw, "host", DEFAULT_STREAM_HOST, where="[stream]")
            ),
            port=_int(
                stream_raw,
                "port",
                DEFAULT_STREAM_PORT,
                where="[stream]",
                minimum=1,
                maximum=65535,
            ),
            mount=_mount(_string(stream_raw, "mount", DEFAULT_MOUNT, where="[stream]")),
            username=_string(stream_raw, "username", "", where="[stream]"),
            password_env=_string(
                stream_raw,
                "password_env",
                DEFAULT_PASSWORD_ENV,
                where="[stream]",
            ),
            tls=_bool(stream_raw, "tls", False, where="[stream]"),
            name=_string(stream_raw, "name", "radio zukka", where="[stream]"),
            description=_string(
                stream_raw,
                "description",
                "Live from the Castcorder",
                where="[stream]",
            ),
            genre=_string(stream_raw, "genre", "", where="[stream]"),
            url=_string(
                stream_raw,
                "url",
                "https://radio.zukkafabrik.de",
                where="[stream]",
            ),
            public=_bool(stream_raw, "public", False, where="[stream]"),
        ),
        encoder=EncoderConfig(
            bitrate=_int(
                encoder_raw,
                "bitrate",
                192,
                where="[encoder]",
                minimum=32,
                maximum=320,
            ),
            extra_args=_string_list(encoder_raw, "extra_args", where="[encoder]"),
        ),
        leds=LedsConfig(
            vu=_bool(leds_raw, "vu", True, where="[leds]"),
            vu_min_db=_number(leds_raw, "vu_min_db", -48.0, where="[leds]"),
            vu_max_db=_number(leds_raw, "vu_max_db", 0.0, where="[leds]"),
            vu_decay_per_second=_number(
                leds_raw,
                "vu_decay_per_second",
                8.0,
                where="[leds]",
                minimum=0.1,
            ),
        ),
        gpio=GpioConfig(
            button_pin=_optional_pin(gpio_raw, "button_pin"),
            button_led_pin=_optional_pin(gpio_raw, "button_led_pin"),
            button_active_high=_bool(
                gpio_raw, "button_active_high", False, where="[gpio]"
            ),
            button_bounce_time=_number(
                gpio_raw,
                "button_bounce_time",
                0.05,
                where="[gpio]",
                minimum=0.0,
            ),
            vu_leds=_vu_leds(gpio_raw),
        ),
        behavior=BehaviorConfig(
            connect_timeout_seconds=_number(
                behavior_raw,
                "connect_timeout_seconds",
                20.0,
                where="[behavior]",
                minimum=1.0,
            ),
            retry_delay_seconds=_number(
                behavior_raw,
                "retry_delay_seconds",
                8.0,
                where="[behavior]",
                minimum=0.0,
            ),
            max_retries=_int(
                behavior_raw, "max_retries", 3, where="[behavior]", minimum=0
            ),
            min_connecting_display_seconds=_number(
                behavior_raw,
                "min_connecting_display_seconds",
                0.9,
                where="[behavior]",
                minimum=0.0,
            ),
        ),
        source=path,
    )

    _validate(cfg)
    return cfg


def read_streamer_password(stream: StreamConfig) -> str:
    """Liest das Streamer-Passwort aus der konfigurierten Umgebungsvariable."""

    env_name = stream.password_env
    value = os.environ.get(env_name, "")
    if not value:
        raise ConfigError(
            f"Streamer-Passwort fehlt: Umgebungsvariable {env_name} ist nicht gesetzt "
            "(z. B. in /etc/castcorder/streamer.env)."
        )
    if "\n" in value or "\r" in value:
        raise ConfigError(f"Umgebungsvariable {env_name} enthält einen Zeilenumbruch.")
    return value


def _section(raw: dict, name: str, allowed: set[str]) -> dict:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] muss eine TOML-Tabelle sein")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConfigError(
            f"Unbekannte Option(en) in [{name}]: {', '.join(unknown)} "
            f"(erlaubt: {', '.join(sorted(allowed))})"
        )
    return value


def _string(section: dict, key: str, default: str, *, where: str) -> str:
    value = section.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{where} {key} muss ein Text sein")
    return value


def _string_list(section: dict, key: str, *, where: str) -> tuple[str, ...]:
    value = section.get(key, [])
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise ConfigError(f"{where} {key} muss eine Liste von Texten sein")
    return tuple(value)


def _bool(section: dict, key: str, default: bool, *, where: str) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{where} {key} muss true oder false sein")
    return value


def _int(
    section: dict,
    key: str,
    default: int,
    *,
    where: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where} {key} muss eine ganze Zahl sein")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{where} {key} muss >= {minimum} sein")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{where} {key} muss <= {maximum} sein")
    return value


def _number(
    section: dict,
    key: str,
    default: float,
    *,
    where: str,
    minimum: float | None = None,
) -> float:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where} {key} muss eine Zahl sein")
    value = float(value)
    if not math.isfinite(value):
        raise ConfigError(f"{where} {key} muss eine endliche Zahl sein")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{where} {key} muss >= {minimum} sein")
    return value


def _optional_pin(section: dict, key: str) -> int | None:
    if key not in section:
        return None
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"[gpio] {key} muss eine BCM-GPIO-Nummer sein")
    if not 0 <= value <= 27:
        raise ConfigError(f"[gpio] {key}={value} ist kein gültiger BCM-Pin (0–27)")
    return value


def _vu_leds(section: dict) -> tuple[int, ...]:
    value = section.get("vu_leds", [])
    if not isinstance(value, list):
        raise ConfigError("[gpio] vu_leds muss eine Liste mit 7 BCM-Pins sein")
    if value and len(value) != len(VU_POSITIONS):
        raise ConfigError(
            f"[gpio] vu_leds braucht genau {len(VU_POSITIONS)} Pins "
            f"(oder eine leere Liste für 'keine LEDs')"
        )
    pins: list[int] = []
    for index, pin in enumerate(value):
        if isinstance(pin, bool) or not isinstance(pin, int):
            raise ConfigError(f"[gpio] vu_leds[{index}] muss eine BCM-GPIO-Nummer sein")
        if not 0 <= pin <= 27:
            raise ConfigError(
                f"[gpio] vu_leds[{index}]={pin} ist kein gültiger BCM-Pin (0–27)"
            )
        pins.append(pin)
    return tuple(pins)


def _mount(value: str) -> str:
    mount = value.strip()
    if not mount:
        return DEFAULT_MOUNT
    if not mount.startswith("/"):
        mount = "/" + mount
    return mount


def _stream_host(value: str) -> str:
    host = value.strip()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host.rstrip("/")


def _validate(cfg: Config) -> None:
    if not cfg.input.device.strip():
        raise ConfigError(
            "[input] device fehlt (z. B. 'plughw:CARD=Device,DEV=0'; siehe arecord -l)"
        )
    if any(ch.isspace() for ch in cfg.input.device):
        raise ConfigError("[input] device darf keine Leerzeichen enthalten")

    if not cfg.stream.host.strip():
        raise ConfigError("[stream] host fehlt")
    if any(ch.isspace() for ch in cfg.stream.host):
        raise ConfigError("[stream] host darf keine Leerzeichen enthalten")
    if "/" in cfg.stream.host:
        raise ConfigError(
            "[stream] host muss ein Hostname/eine IP ohne Pfad sein "
            "(ohne https:// und ohne /)"
        )
    if not cfg.stream.username.strip():
        raise ConfigError(
            "[stream] username fehlt (Streamer/DJ-Benutzername aus AzuraCast)"
        )
    if ":" in cfg.stream.username or any(ch.isspace() for ch in cfg.stream.username):
        raise ConfigError("[stream] username darf keine Leerzeichen oder ':' enthalten")
    if not cfg.stream.password_env.strip() or "=" in cfg.stream.password_env:
        raise ConfigError("[stream] password_env ist kein gültiger Variablenname")
    if any(ch.isspace() for ch in cfg.stream.mount):
        raise ConfigError("[stream] mount darf keine Leerzeichen enthalten")

    for key in ("name", "description", "genre", "url"):
        value = getattr(cfg.stream, key)
        if "\n" in value or "\r" in value:
            raise ConfigError(f"[stream] {key} darf keine Zeilenumbrüche enthalten")

    if cfg.leds.vu_min_db >= cfg.leds.vu_max_db:
        raise ConfigError("[leds] vu_min_db muss kleiner als vu_max_db sein")

    _validate_pins(cfg.gpio)


def _validate_pins(gpio: GpioConfig) -> None:
    used: dict[int, str] = {}
    named = (
        ("button_pin", gpio.button_pin),
        ("button_led_pin", gpio.button_led_pin),
    )
    for label, pin in named:
        if pin is None:
            continue
        if pin in used:
            raise ConfigError(
                f"[gpio] BCM{pin} ist doppelt belegt: {used[pin]} und {label}"
            )
        used[pin] = label

    for position, pin in zip(VU_POSITIONS, gpio.vu_leds):
        if pin in used:
            raise ConfigError(
                f"[gpio] BCM{pin} ist doppelt belegt: {used[pin]} und VU-Segment {position}"
            )
        used[pin] = f"VU-Segment {position}"
