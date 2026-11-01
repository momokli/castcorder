from __future__ import annotations

import unittest

from castcorder.lights import (
    ALL_SEGMENTS,
    LEVEL_MASKS,
    LIVE_NO_LEVEL,
    VU_POSITIONS,
    Effects,
)
from castcorder.state import State


class LevelMaskTests(unittest.TestCase):
    def test_level_lights_the_first_segments(self) -> None:
        for value, mask in LEVEL_MASKS.items():
            self.assertEqual(len(mask), value)
            self.assertLessEqual(mask, ALL_SEGMENTS)
            self.assertEqual(mask, frozenset(VU_POSITIONS[:value]))

    def test_layout(self) -> None:
        self.assertEqual(LEVEL_MASKS[1], frozenset({"vu1"}))
        self.assertEqual(LEVEL_MASKS[3], frozenset({"vu1", "vu2", "vu3"}))
        self.assertEqual(LEVEL_MASKS[7], ALL_SEGMENTS)
        self.assertEqual(ALL_SEGMENTS, frozenset(VU_POSITIONS))


class EffectsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.effects = Effects()

    def test_idle_button_glows_softly(self) -> None:
        frame = self.effects.frame(State.IDLE, 0.0)
        self.assertEqual(frame.mask, frozenset())
        self.assertAlmostEqual(frame.button, 0.12)

    def test_connecting_sweeps_and_blinks(self) -> None:
        first = self.effects.frame(State.CONNECTING, 10.0)
        self.assertEqual(first.mask, LEVEL_MASKS[1])
        second = self.effects.frame(State.CONNECTING, 10.14)
        self.assertEqual(second.mask, LEVEL_MASKS[2])
        last = self.effects.frame(State.CONNECTING, 10.0 + 0.14 * 6 + 0.001)
        self.assertEqual(last.mask, LEVEL_MASKS[7])
        off = self.effects.frame(State.CONNECTING, 10.25)
        self.assertLess(off.button, 0.5)

    def test_live_without_level_shows_mid_scale(self) -> None:
        frame = self.effects.frame(State.LIVE, 0.0)
        self.assertEqual(frame.mask, LEVEL_MASKS[LIVE_NO_LEVEL])
        self.assertEqual(frame.button, 1.0)

    def test_live_level_maps_to_ladder(self) -> None:
        self.assertEqual(self.effects.frame(State.LIVE, 0.0, 0.4).mask, LEVEL_MASKS[0])
        self.assertEqual(self.effects.frame(State.LIVE, 0.0, 2.6).mask, LEVEL_MASKS[3])
        self.assertEqual(self.effects.frame(State.LIVE, 0.0, 6.4).mask, LEVEL_MASKS[6])
        self.assertEqual(self.effects.frame(State.LIVE, 0.0, 7.0).mask, ALL_SEGMENTS)

    def test_retrying_blinks_all_segments(self) -> None:
        on = self.effects.frame(State.RETRYING, 5.0)
        off = self.effects.frame(State.RETRYING, 5.5)
        self.assertEqual(on.mask, ALL_SEGMENTS)
        self.assertEqual(off.mask, frozenset())
        self.assertEqual(on.button, 0.0)

    def test_error_blinks_faster(self) -> None:
        on = self.effects.frame(State.ERROR, 0.0)
        off = self.effects.frame(State.ERROR, 0.25)
        self.assertEqual(on.mask, ALL_SEGMENTS)
        self.assertEqual(off.mask, frozenset())

    def test_state_change_restarts_animation_clock(self) -> None:
        self.effects.frame(State.CONNECTING, 0.0)
        self.effects.frame(State.LIVE, 100.0)
        frame = self.effects.frame(State.CONNECTING, 100.0)
        self.assertEqual(frame.mask, LEVEL_MASKS[1])


if __name__ == "__main__":
    unittest.main()
