from __future__ import annotations

import logging
import unittest

from castcorder.app import RadioApp
from castcorder.config import (
    BehaviorConfig,
    Config,
    GpioConfig,
    InputConfig,
    LedsConfig,
    StreamConfig,
)
from castcorder.lights import ALL_SEGMENTS, LEVEL_MASKS, LIVE_NO_LEVEL
from castcorder.state import State


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeEncoder:
    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0
        self.error: Exception | None = None

    def start(self) -> None:
        self.starts += 1
        if self.error is not None:
            raise self.error

    def stop(self) -> None:
        self.stops += 1


class FakeLights:
    def __init__(self) -> None:
        self.frames: list[tuple[frozenset[str], float]] = []

    def show(self, mask: frozenset[str], button: float) -> None:
        self.frames.append((mask, button))


def make_config(*, vu: bool = True) -> Config:
    return Config(
        input=InputConfig(device="test"),
        stream=StreamConfig(username="momo"),
        gpio=GpioConfig(vu_leds=(5, 6, 16, 22, 23, 24, 25)),
        leds=LedsConfig(
            vu=vu,
            vu_min_db=-48,
            vu_max_db=0,
            vu_decay_per_second=8,
        ),
        behavior=BehaviorConfig(
            connect_timeout_seconds=10,
            retry_delay_seconds=5,
            max_retries=2,
            min_connecting_display_seconds=0.5,
        ),
    )


class RadioAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.encoder = FakeEncoder()
        self.lights = FakeLights()
        self.config = make_config()
        self.log = logging.getLogger("test.castcorder")
        self.log.addHandler(logging.NullHandler())
        self.app = RadioApp(
            self.config,
            self.encoder,
            self.lights,
            clock=self.clock,
            log=self.log,
        )

    def press(self) -> None:
        self.app.on_button()

    def connected(self) -> None:
        self.app.on_encoder_connected()

    def make_live(self) -> None:
        self.press()
        self.connected()
        self.clock.advance(1.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.LIVE)

    def drive_to_error(self) -> None:
        self.press()
        for _ in range(3):
            self.clock.advance(10.0)
            self.app.tick()
            self.clock.advance(5.0)
            self.app.tick()
        self.assertEqual(self.app.state, State.ERROR)

    def test_button_starts_encoder(self) -> None:
        self.press()
        self.assertEqual(self.app.state, State.CONNECTING)
        self.assertEqual(self.encoder.starts, 1)

    def test_connected_waits_for_minimum_display(self) -> None:
        self.press()
        self.connected()
        self.assertEqual(self.app.state, State.CONNECTING)

        self.clock.advance(0.49)
        self.app.tick()
        self.assertEqual(self.app.state, State.CONNECTING)

        self.clock.advance(0.02)
        self.app.tick()
        self.assertEqual(self.app.state, State.LIVE)

    def test_connected_after_delay_is_live_immediately(self) -> None:
        self.press()
        self.clock.advance(1.0)
        self.connected()
        self.assertEqual(self.app.state, State.LIVE)

    def test_second_press_stops(self) -> None:
        self.make_live()
        self.press()
        self.assertEqual(self.app.state, State.IDLE)
        self.assertGreaterEqual(self.encoder.stops, 1)

    def test_connect_timeout_retries_then_errors(self) -> None:
        self.press()

        self.clock.advance(10.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.RETRYING)
        self.assertEqual(self.encoder.starts, 1)

        self.clock.advance(5.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.CONNECTING)
        self.assertEqual(self.encoder.starts, 2)

        self.clock.advance(10.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.RETRYING)

        self.clock.advance(5.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.CONNECTING)
        self.assertEqual(self.encoder.starts, 3)

        self.clock.advance(10.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.ERROR)

    def test_encoder_error_retries(self) -> None:
        self.press()
        self.app.on_encoder_error("auth")
        self.assertEqual(self.app.state, State.RETRYING)

        self.clock.advance(5.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.CONNECTING)
        self.assertEqual(self.encoder.starts, 2)

    def test_press_during_retry_cancels(self) -> None:
        self.press()
        self.app.on_encoder_error("auth")
        self.assertEqual(self.app.state, State.RETRYING)

        self.press()
        self.assertEqual(self.app.state, State.IDLE)

        self.clock.advance(60.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.IDLE)
        self.assertEqual(self.encoder.starts, 1)

    def test_press_after_error_restarts(self) -> None:
        self.drive_to_error()
        self.press()
        self.assertEqual(self.app.state, State.CONNECTING)
        self.assertEqual(self.encoder.starts, 4)

    def test_encoder_exit_while_live_retries(self) -> None:
        self.make_live()
        self.app.on_encoder_exited(1)
        self.assertEqual(self.app.state, State.RETRYING)

    def test_encoder_exit_while_idle_is_ignored(self) -> None:
        self.app.on_encoder_exited(1)
        self.assertEqual(self.app.state, State.IDLE)

    def test_start_failure_is_retried(self) -> None:
        self.encoder.error = RuntimeError("ffmpeg fehlt")
        self.press()
        self.assertEqual(self.app.state, State.RETRYING)
        self.assertEqual(self.encoder.starts, 1)

        self.clock.advance(5.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.RETRYING)

        self.clock.advance(5.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.ERROR)

    def test_audio_level_maps_to_vu_ladder(self) -> None:
        self.make_live()
        self.app.on_audio_level(-24.0)
        self.app.tick()
        self.assertEqual(self.lights.frames[-1][0], LEVEL_MASKS[4])

    def test_audio_level_peak_is_held(self) -> None:
        self.make_live()
        self.app.on_audio_level(0.0)
        self.app.tick()
        self.assertEqual(self.lights.frames[-1][0], ALL_SEGMENTS)

        self.app.on_audio_level(-30.0)
        self.app.tick()
        # Der alte Peak wird noch gehalten, nicht sofort abgesenkt.
        self.assertEqual(self.lights.frames[-1][0], ALL_SEGMENTS)

    def test_audio_level_decays(self) -> None:
        self.make_live()
        self.app.on_audio_level(0.0)
        self.app.tick()
        self.assertEqual(self.lights.frames[-1][0], ALL_SEGMENTS)

        self.clock.advance(1.0)
        self.app.tick()
        self.assertEqual(self.lights.frames[-1][0], LEVEL_MASKS[0])

    def test_vu_disabled_shows_mid_scale(self) -> None:
        self.config = make_config(vu=False)
        self.app = RadioApp(
            self.config,
            self.encoder,
            self.lights,
            clock=self.clock,
            log=self.log,
        )
        self.make_live()
        self.app.on_audio_level(0.0)
        self.app.tick()
        self.assertEqual(self.lights.frames[-1][0], LEVEL_MASKS[LIVE_NO_LEVEL])

    def test_audio_level_ignored_when_idle(self) -> None:
        self.app.on_audio_level(0.0)
        self.app.tick()
        self.assertEqual(self.app.state, State.IDLE)

    def test_shutdown_does_not_retry(self) -> None:
        self.make_live()
        self.app.shutdown()
        self.app.on_encoder_exited(1)
        self.assertEqual(self.app.state, State.LIVE)


if __name__ == "__main__":
    unittest.main()
