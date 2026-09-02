"""Route device events into behavior decisions."""

from __future__ import annotations

from mimi_agent.protocol.messages import PhysicalEvent

from .speech_policy import SpeechDecision, SpeechPolicy


class EventRouter:
    def __init__(self, speech_policy: SpeechPolicy) -> None:
        self.speech_policy = speech_policy

    def route(self, event: PhysicalEvent) -> SpeechDecision | None:
        return self.speech_policy.decide(event)
