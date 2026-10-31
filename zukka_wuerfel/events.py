"""Ereignisse, die in der Hauptschleife verarbeitet werden."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ButtonPressed:
    """Der LIVE-Knopf wurde gedrückt."""


@dataclass(frozen=True)
class EncoderConnected:
    """Die Icecast-Quelle wurde vom Server akzeptiert (HTTP 200)."""


@dataclass(frozen=True)
class EncoderError:
    """Der Encoder konnte nicht starten oder die Verbindung brach ab."""

    reason: str


@dataclass(frozen=True)
class EncoderExited:
    """Der ffmpeg-Prozess ist beendet worden."""

    code: int | None = None


@dataclass(frozen=True)
class AudioLevel:
    """Aktueller Peak-Pegel des Eingangssignals in dBFS."""

    db: float
