"""GPIO-Hardware (Knopf, Button-LED, sieben VU-Segmente)."""

from __future__ import annotations

import logging
from typing import Callable, Protocol

from .config import GpioConfig
from .lights import VU_POSITIONS


class HardwareError(RuntimeError):
    """GPIO konnte nicht initialisiert werden."""


class Lights(Protocol):
    def show(self, mask: frozenset[str], button: float) -> None: ...

    def close(self) -> None: ...


class NullLights:
    """LED-Ersatz für die Entwicklung ohne Pi (``--no-gpio``)."""

    def __init__(self, log: logging.Logger | None = None) -> None:
        self._log = log or logging.getLogger("castcorder")
        self._last: tuple[frozenset[str], float] | None = None

    def show(self, mask: frozenset[str], button: float) -> None:
        current = (mask, round(button, 2))
        if current != self._last:
            self._last = current
            self._log.debug(
                "LEDs: %d Segmente leuchten (%s), Knopf %.2f",
                len(mask),
                ",".join(sorted(mask)) or "-",
                button,
            )

    def close(self) -> None:
        pass


class GpioHardware:
    """Konkrete LED-/Knopf-Anbindung über gpiozero.

    gpiozero wird erst hier importiert, damit die restliche Software (und die
    Tests) auch auf einem Mac ohne GPIO läuft.
    """

    def __init__(
        self,
        config: GpioConfig,
        on_press: Callable[[], None],
        log: logging.Logger | None = None,
    ) -> None:
        if config.button_pin is None:
            raise HardwareError(
                "[gpio] button_pin fehlt. Ohne Knopf mit --no-gpio starten."
            )
        if config.vu_leds and len(config.vu_leds) != len(VU_POSITIONS):
            raise HardwareError(
                f"[gpio] vu_leds braucht genau {len(VU_POSITIONS)} Pins "
                "(oder eine leere Liste)."
            )

        try:
            from gpiozero import PWMLED, Button
        except ImportError as exc:
            raise HardwareError(
                "gpiozero fehlt. Auf dem Pi: "
                "sudo apt install python3-gpiozero python3-lgpio"
            ) from exc

        self._log = log or logging.getLogger("castcorder")
        self._button = None
        self._button_led = None
        self._segments: dict[str, object] = {}

        try:
            for position, pin in zip(VU_POSITIONS, config.vu_leds):
                self._segments[position] = PWMLED(pin)

            if config.button_led_pin is not None:
                self._button_led = PWMLED(config.button_led_pin)

            bounce_time = config.button_bounce_time or None
            self._button = Button(
                config.button_pin,
                pull_up=not config.button_active_high,
                bounce_time=bounce_time,
            )
            self._button.when_pressed = on_press
        except Exception as exc:
            self.close()
            raise HardwareError(f"GPIO-Initialisierung fehlgeschlagen: {exc}") from exc

        self._log.info(
            "GPIO bereit: Knopf BCM%d, Button-LED %s, VU-Leiter %s",
            config.button_pin,
            f"BCM{config.button_led_pin}"
            if config.button_led_pin is not None
            else "aus",
            ",".join(str(pin) for pin in config.vu_leds) if config.vu_leds else "aus",
        )

    def show(self, mask: frozenset[str], button: float) -> None:
        for position, led in self._segments.items():
            led.value = 1.0 if position in mask else 0.0  # type: ignore[attr-defined]
        if self._button_led is not None:
            self._button_led.value = button  # type: ignore[attr-defined]

    def close(self) -> None:
        for device in (self._button, self._button_led, *self._segments.values()):
            if device is None:
                continue
            try:
                device.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._button = None
        self._button_led = None
        self._segments = {}
