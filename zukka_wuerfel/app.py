"""Zustandsmaschine des radio-zukka-Live-Würfels."""

from __future__ import annotations

import logging
import time
from typing import Callable, Protocol

from .config import Config
from .lights import Effects, Frame
from .state import State


class Encoder(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class Lights(Protocol):
    def show(self, mask: frozenset[str], button: float) -> None: ...


class RadioApp:
    """Verbindet LIVE-Knopf, Encoder-Ereignisse und Würfel-LEDs.

    Die Klasse kennt weder GPIO noch ffmpeg/Icecast direkt und lässt sich
    deshalb mit Fakes vollständig testen.
    """

    def __init__(
        self,
        config: Config,
        encoder: Encoder,
        lights: Lights,
        *,
        clock: Callable[[], float] = time.monotonic,
        log: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.encoder = encoder
        self.lights = lights
        self.clock = clock
        self.log = log or logging.getLogger("zukka_wuerfel")
        self.effects = Effects()

        self.state = State.IDLE
        self._want_live = False
        self._retries = 0
        self._connected = False
        self._connect_deadline: float | None = None
        self._retry_at: float | None = None
        self._live_at = 0.0

        self._level = 0.0
        self._level_at = 0.0
        self._level_seen = False

        self._last_frame: Frame | None = None

    # ------------------------------------------------------------------ input

    def on_button(self) -> None:
        """Der LIVE-Knopf wurde gedrückt: senden oder stoppen."""

        if self.state in {State.CONNECTING, State.LIVE, State.RETRYING}:
            self._stop()
        else:
            self._start()

    def on_encoder_connected(self) -> None:
        if self.state is not State.CONNECTING or not self._want_live:
            return
        self._connected = True
        self.log.info("Icecast-Quelle verbunden.")
        if self.clock() >= self._live_at:
            self._enter(State.LIVE)

    def on_encoder_error(self, reason: str) -> None:
        if self._want_live:
            self._fail(reason)
        else:
            self.log.debug("Encoder-Fehler nach Stop ignoriert: %s", reason)

    def on_encoder_exited(self, code: int | None = None) -> None:
        if self._want_live:
            self._fail(f"Encoder beendet (Code {code})")
        else:
            self.log.debug("Encoder beendet (Code %s)", code)

    def on_audio_level(self, db: float) -> None:
        if not (self.config.leds.vu and self.config.gpio.pips):
            return
        if self.state not in {State.CONNECTING, State.LIVE}:
            return

        low = self.config.leds.vu_min_db
        high = self.config.leds.vu_max_db
        span = max(1e-9, high - low)
        target = (db - low) / span * 7.0
        target = max(0.0, min(7.0, target))

        self._level = max(self._level, target)
        self._level_at = self.clock()
        self._level_seen = True

    # ------------------------------------------------------------- transitions

    def _start(self) -> None:
        self._retries = 0
        self._want_live = True
        self._begin_broadcast()

    def _begin_broadcast(self) -> None:
        now = self.clock()
        self._connected = False
        self._level = 0.0
        self._level_at = now
        self._level_seen = False
        self._connect_deadline = now + self.config.behavior.connect_timeout_seconds
        self._retry_at = None
        self._live_at = now + self.config.behavior.min_connecting_display_seconds
        self._enter(State.CONNECTING)
        self.log.info(
            "Starte Live-Stream als DJ %s zu %s:%s%s",
            self.config.stream.username,
            self.config.stream.host,
            self.config.stream.port,
            self.config.stream.mount,
        )
        try:
            self.encoder.start()
        except Exception as exc:
            self._fail(str(exc) or exc.__class__.__name__)

    def _stop(self) -> None:
        self._want_live = False
        self._retries = 0
        self._connected = False
        self._clear_timers()
        self._enter(State.IDLE)
        self.log.info("Live-Stream gestoppt.")
        try:
            self.encoder.stop()
        except Exception as exc:
            self.log.warning("Encoder konnte nicht gestoppt werden: %s", exc)

    def _fail(self, reason: str) -> None:
        self._clear_timers()
        self._connected = False

        if self._want_live and self._retries < self.config.behavior.max_retries:
            self._retries += 1
            delay = self.config.behavior.retry_delay_seconds
            self._retry_at = self.clock() + delay
            self._enter(State.RETRYING)
            self.log.warning(
                "Stream fehlgeschlagen (%s). Neuer Versuch in %.1fs (%d/%d).",
                reason,
                delay,
                self._retries,
                self.config.behavior.max_retries,
            )
        else:
            self._want_live = False
            self._enter(State.ERROR)
            self.log.error("Live-Stream fehlgeschlagen: %s", reason)

        try:
            self.encoder.stop()
        except Exception:
            pass

    def _enter(self, state: State) -> None:
        if state is self.state:
            return
        self.state = state
        self.log.debug("Zustand -> %s", state)
        if state is State.LIVE:
            self._retries = 0
            self._clear_timers()
            self.log.info(
                "LIVE als %s – AzuraCast hat die Quelle übernommen.",
                self.config.stream.username,
            )

    def _clear_timers(self) -> None:
        self._connect_deadline = None
        self._retry_at = None

    # -------------------------------------------------------------------- loop

    def tick(self) -> None:
        """Regelmäßig aufrufen: Timeouts, Retries, Pegel-Decay und LEDs."""

        now = self.clock()

        if now > self._level_at:
            self._level = max(
                0.0,
                self._level
                - (now - self._level_at) * self.config.leds.vu_decay_per_second,
            )
            self._level_at = now

        if self.state is State.CONNECTING:
            if self._connected and now >= self._live_at:
                self._enter(State.LIVE)
            elif self._connect_deadline is not None and now >= self._connect_deadline:
                self._fail("Zeitüberschreitung beim Verbinden")
        elif (
            self.state is State.RETRYING
            and self._retry_at is not None
            and now >= self._retry_at
        ):
            self._begin_broadcast()

        self._render(now)

    def _render(self, now: float) -> None:
        level = (
            self._level
            if self.config.leds.vu and self._level_seen and self.config.gpio.pips
            else None
        )
        frame = self.effects.frame(self.state, now, level)
        if frame == self._last_frame:
            return
        self._last_frame = frame
        try:
            self.lights.show(frame.mask, frame.button)
        except Exception as exc:
            self.log.warning("LED-Update fehlgeschlagen: %s", exc)

    def shutdown(self) -> None:
        """Beim Beenden keine Retries mehr planen und Events ignorieren."""

        self._want_live = False
        self._clear_timers()
