"""Würfel-Augenzahl (Pips) und LED-Effekte."""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import State

# Reihenfolge der sieben LEDs auf der Würfelfläche:
#
#   tl   tr
#     ml c mr
#   bl   br
PIP_POSITIONS = ("tl", "tr", "ml", "c", "mr", "bl", "br")

PIP_MASKS: dict[int, frozenset[str]] = {
    0: frozenset(),
    1: frozenset({"c"}),
    2: frozenset({"tl", "br"}),
    3: frozenset({"tl", "c", "br"}),
    4: frozenset({"tl", "tr", "bl", "br"}),
    5: frozenset({"tl", "tr", "c", "bl", "br"}),
    6: frozenset({"tl", "tr", "ml", "mr", "bl", "br"}),
}

ALL_PIPS = frozenset(PIP_POSITIONS)


@dataclass(frozen=True)
class Frame:
    """Ein LED-Zustand: welche Pips leuchten und wie hell der Knopf ist."""

    mask: frozenset[str] = field(default_factory=frozenset)
    button: float = 0.0


class Effects:
    """Erzeugt aus Zustand, Zeit und optionalem Pegel einen LED-Frame."""

    CONNECTING_STEP = 0.14
    CONNECTING_BLINK = 0.25
    RETRY_BLINK = 0.5
    ERROR_BLINK = 0.25
    IDLE_BUTTON = 0.12

    def __init__(self) -> None:
        self._state: State | None = None
        self._since = 0.0

    def frame(self, state: State, now: float, level: float | None = None) -> Frame:
        if state is not self._state:
            self._state = state
            self._since = now

        elapsed = max(0.0, now - self._since)

        if state is State.IDLE:
            return Frame(PIP_MASKS[0], self.IDLE_BUTTON)

        if state is State.CONNECTING:
            value = int(elapsed / self.CONNECTING_STEP) % 6 + 1
            button = 1.0 if int(elapsed / self.CONNECTING_BLINK) % 2 == 0 else 0.15
            return Frame(PIP_MASKS[value], button)

        if state is State.LIVE:
            if level is None:
                # Noch kein Pegel-Event (z. B. VU deaktiviert): stabile 6.
                return Frame(PIP_MASKS[6], 1.0)
            value = max(0, min(7, int(round(level))))
            mask = ALL_PIPS if value >= 7 else PIP_MASKS[value]
            return Frame(mask, 1.0)

        if state is State.RETRYING:
            on = int(elapsed / self.RETRY_BLINK) % 2 == 0
            return Frame(ALL_PIPS if on else PIP_MASKS[0], 0.0)

        # ERROR: schnelles Blinken aller Pips.
        on = int(elapsed / self.ERROR_BLINK) % 2 == 0
        return Frame(ALL_PIPS if on else PIP_MASKS[0], 0.0)
