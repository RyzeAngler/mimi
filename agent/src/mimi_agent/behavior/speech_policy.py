"""Determine which physical actions should trigger an LLM speech turn."""

import time
from dataclasses import dataclass

from mimi_agent.protocol.messages import PhysicalEvent


@dataclass(frozen=True)
class SpeechDecision:
    key: str
    priority: int = 1
    cooldown_ms: int = 2500


class SpeechPolicy:
    """Map meaningful motion transitions to speech-worthy event keys.

    Telemetry is intentionally not handled here. The device should emit a
    dedicated ``motion_event`` only when a behavior-worthy action occurs.
    """

    _SPEECH_KEYS = frozenset(
        {
            "tilt_left",
            "tilt_right",
            "tilt_forward",
            "tilt_backward",
            "shaking",
            "pickup",
            "setdown",
            "touch",
            "curious",
            "excited",
            "dizzy",
            "sleepy",
        }
    )

    _PRIORITIES = {
        "touch": 100,
        "shaking": 80,
        "dizzy": 70,
        "pickup": 60,
        "setdown": 60,
        "excited": 50,
        "curious": 40,
        "tilt_left": 40,
        "tilt_right": 40,
        "tilt_forward": 40,
        "tilt_backward": 40,
        "sleepy": 20,
    }

    _MIN_CONFIDENCE = 0.4
    _MIN_INTENSITY = 0.05
    _MIN_MOTION_DURATION_MS = 100
    _MIN_PEAK_ANGULAR_SPEED_DPS = 20.0
    _MIN_PEAK_DYNAMIC_ACCELERATION_G = 0.05
    _MIN_TILT_STRENGTH = 0.08

    def __init__(
        self,
        default_cooldown_ms: int = 2500,
        dizzy_cooldown_ms: int = 5000,
    ) -> None:
        self.default_cooldown_ms = default_cooldown_ms
        self.dizzy_cooldown_ms = dizzy_cooldown_ms
        self._last_spoken_at: dict[str, float] = {}

    def decide(
        self,
        event: PhysicalEvent,
        now: float | None = None,
    ) -> SpeechDecision | None:
        key = self._canonical_key(event)
        if key not in self._SPEECH_KEYS:
            key = event.behavior.lower()
        if key not in self._SPEECH_KEYS:
            return None
        if not self._has_motion_evidence(event, key):
            return None

        cooldown_ms = (
            self.dizzy_cooldown_ms
            if key == "shaking" or event.behavior.lower() == "dizzy"
            else self.default_cooldown_ms
        )
        current = time.monotonic() if now is None else now
        previous = self._last_spoken_at.get(key)
        if previous is not None and (current - previous) * 1000 < cooldown_ms:
            return None
        self._last_spoken_at[key] = current
        return SpeechDecision(
            key=key,
            priority=self._PRIORITIES.get(key, 1),
            cooldown_ms=cooldown_ms,
        )

    @classmethod
    def _has_motion_evidence(cls, event: PhysicalEvent, key: str) -> bool:
        if key == "touch":
            return True
        if event.summary is None:
            return True
        summary = event.summary
        if 0.0 < summary.confidence < cls._MIN_CONFIDENCE:
            return False
        return any(
            (
                event.intensity >= cls._MIN_INTENSITY,
                summary.motion_duration_ms >= cls._MIN_MOTION_DURATION_MS,
                summary.peak_angular_speed_dps >= cls._MIN_PEAK_ANGULAR_SPEED_DPS,
                summary.peak_dynamic_acceleration_g
                >= cls._MIN_PEAK_DYNAMIC_ACCELERATION_G,
                summary.tilt_strength >= cls._MIN_TILT_STRENGTH,
            )
        )

    @staticmethod
    def _canonical_key(event: PhysicalEvent) -> str:
        value = event.event.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "left": "tilt_left",
            "right": "tilt_right",
            "forward": "tilt_forward",
            "backward": "tilt_backward",
            "shake": "shaking",
            "shaking": "shaking",
            "tiltleft": "tilt_left",
            "tiltright": "tilt_right",
            "tiltforward": "tilt_forward",
            "tiltbackward": "tilt_backward",
        }
        return aliases.get(value, value)
