from __future__ import annotations

import unittest

from zukka_wuerfel.lights import ALL_PIPS, PIP_MASKS, PIP_POSITIONS, Effects
from zukka_wuerfel.state import State


class PipMaskTests(unittest.TestCase):
    def test_dice_values_have_expected_pip_counts(self) -> None:
        for value, mask in PIP_MASKS.items():
            self.assertEqual(len(mask), value)
            self.assertLessEqual(mask, ALL_PIPS)

    def test_layout(self) -> None:
        self.assertEqual(PIP_MASKS[1], frozenset({"c"}))
        self.assertEqual(PIP_MASKS[2], frozenset({"tl", "br"}))
        self.assertNotIn("c", PIP_MASKS[2])
        self.assertEqual(len(PIP_MASKS[6]), 6)
        self.assertEqual(ALL_PIPS, frozenset(PIP_POSITIONS))


class EffectsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.effects = Effects()

    def test_idle_button_glows_softly(self) -> None:
        frame = self.effects.frame(State.IDLE, 0.0)
        self.assertEqual(frame.mask, frozenset())
        self.assertAlmostEqual(frame.button, 0.12)

    def test_connecting_rolls_and_blinks(self) -> None:
        first = self.effects.frame(State.CONNECTING, 10.0)
        self.assertEqual(first.mask, PIP_MASKS[1])
        second = self.effects.frame(State.CONNECTING, 10.14)
        self.assertEqual(second.mask, PIP_MASKS[2])
        last = self.effects.frame(State.CONNECTING, 10.0 + 0.14 * 5 + 0.001)
        self.assertEqual(last.mask, PIP_MASKS[6])
        off = self.effects.frame(State.CONNECTING, 10.25)
        self.assertLess(off.button, 0.5)

    def test_live_without_level_shows_six(self) -> None:
        frame = self.effects.frame(State.LIVE, 0.0)
        self.assertEqual(frame.mask, PIP_MASKS[6])
        self.assertEqual(frame.button, 1.0)

    def test_live_level_maps_to_dice(self) -> None:
        self.assertEqual(self.effects.frame(State.LIVE, 0.0, 0.4).mask, PIP_MASKS[0])
        self.assertEqual(self.effects.frame(State.LIVE, 0.0, 2.6).mask, PIP_MASKS[3])
        self.assertEqual(self.effects.frame(State.LIVE, 0.0, 6.4).mask, PIP_MASKS[6])
        self.assertEqual(self.effects.frame(State.LIVE, 0.0, 7.0).mask, ALL_PIPS)

    def test_retrying_blinks_all_pips(self) -> None:
        on = self.effects.frame(State.RETRYING, 5.0)
        off = self.effects.frame(State.RETRYING, 5.5)
        self.assertEqual(on.mask, ALL_PIPS)
        self.assertEqual(off.mask, frozenset())
        self.assertEqual(on.button, 0.0)

    def test_error_blinks_faster(self) -> None:
        on = self.effects.frame(State.ERROR, 0.0)
        off = self.effects.frame(State.ERROR, 0.25)
        self.assertEqual(on.mask, ALL_PIPS)
        self.assertEqual(off.mask, frozenset())

    def test_state_change_restarts_animation_clock(self) -> None:
        self.effects.frame(State.CONNECTING, 0.0)
        self.effects.frame(State.LIVE, 100.0)
        frame = self.effects.frame(State.CONNECTING, 100.0)
        self.assertEqual(frame.mask, PIP_MASKS[1])


if __name__ == "__main__":
    unittest.main()
