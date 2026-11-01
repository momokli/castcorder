"""Betriebszustände des Castcorder."""

from __future__ import annotations

from enum import Enum


class State(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    LIVE = "live"
    RETRYING = "retrying"
    ERROR = "error"

    def __str__(self) -> str:
        return self.value
