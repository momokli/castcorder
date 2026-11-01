"""VU-Leiter und LED-Effekte des Castcorder."""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import State

# Reihenfolge der sieben LEDs auf der VU-Leiter (links → rechts):
#
#   vu1 vu2 vu3 vu4 vu5 vu6 vu7
VU_POSITIONS = ("vu1", "vu2", "vu3", "vu4", "vu5", "vu6", "vu7")

# Pegel n leuchtet die ersten n Segmente. 7 = alle Segmente = Clipping.
LEVEL_MASKS: dict[int, frozenset[str]] = {
    value: frozenset(VU_POSITIONS[:value]) for value in range(8)
}

ALL_SEGMENTS = frozenset(VU_POSITIONS)

# Ohne Pegel-Event (z. B. VU deaktiviert) zeigt die Leiter einen mittleren
# Ausschlag, damit „live“ nicht wie Clipping aussieht.
LIVE_NO_LEVEL = 4


@dataclass(frozen=True)
class Frame:
    """Ein LED-Zustand: welche Segmente leuchten und wie hell der Knopf ist."""

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
            return Frame(LEVEL_MASKS[0], self.IDLE_BUTTON)

        if state is State.CONNECTING:
            # Die Leiter läuft einmal pro Schritt von links nach rechts durch.
            value = int(elapsed / self.CONNECTING_STEP) % len(VU_POSITIONS) + 1
            button = 1.0 if int(elapsed / self.CONNECTING_BLINK) % 2 == 0 else 0.15
            return Frame(LEVEL_MASKS[value], button)

        if state is State.LIVE:
            if level is None:
                return Frame(LEVEL_MASKS[LIVE_NO_LEVEL], 1.0)
            value = max(0, min(7, int(round(level))))
            return Frame(LEVEL_MASKS[value], 1.0)

        if state is State.RETRYING:
            on = int(elapsed / self.RETRY_BLINK) % 2 == 0
            return Frame(ALL_SEGMENTS if on else LEVEL_MASKS[0], 0.0)

        # ERROR: schnelles Blinken der ganzen Leiter.
        on = int(elapsed / self.ERROR_BLINK) % 2 == 0
        return Frame(ALL_SEGMENTS if on else LEVEL_MASKS[0], 0.0)
