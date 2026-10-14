"""Bounded conversation context for one Mimi device session."""

from collections import deque
from dataclasses import dataclass

from .llm import LlmMessage


@dataclass(frozen=True)
class ConversationTurn:
    """A completed user input and Mimi response."""

    user: str
    assistant: str


class ConversationHistory:
    """Keep only the newest completed turns for one connected device."""

    def __init__(self, max_turns: int = 10) -> None:
        if max_turns <= 0:
            raise ValueError("max_turns must be positive")
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)

    @property
    def turns(self) -> tuple[ConversationTurn, ...]:
        return tuple(self._turns)

    def append(self, user: str, assistant: str) -> None:
        if not user.strip() or not assistant.strip():
            raise ValueError("conversation turns must contain user and assistant text")
        self._turns.append(ConversationTurn(user.strip(), assistant.strip()))

    def messages(self, system_prompt: str, current_prompt: str) -> tuple[LlmMessage, ...]:
        if not system_prompt.strip() or not current_prompt.strip():
            raise ValueError("system and current prompts must not be empty")

        messages: list[LlmMessage] = [LlmMessage("system", system_prompt)]
        for turn in self._turns:
            messages.extend(
                (
                    LlmMessage("user", turn.user),
                    LlmMessage("assistant", turn.assistant),
                )
            )
        messages.append(LlmMessage("user", current_prompt))
        return tuple(messages)
