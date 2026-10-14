import json

from mimi_agent.agent_core.prompt import (
    build_event_prompt,
)
from mimi_agent.agent_core.llm import LlmSpeechRequest
from mimi_agent.protocol.messages import MotionSummary


def test_event_prompt_contains_raw_sensor_data() -> None:
    prompt = build_event_prompt(
        LlmSpeechRequest(
            event="tilt_forward",
            behavior="dizzy",
            intensity=0.63,
            summary=MotionSummary(
                pitch_deg=22.5,
                acceleration_norm_g=1.01,
                still_duration_ms=1200,
                confidence=0.91,
                stability=0.82,
                tilt_strength=0.60,
            ),
            messages=(),
        )
    )

    payload = json.loads(prompt.splitlines()[1])
    assert payload["event"] == "tilt_forward"
    assert payload["behavior"] == "dizzy"
    assert payload["intensity"] == 0.63
    assert payload["pitch_deg"] == 22.5
    assert payload["acceleration_norm_g"] == 1.01
    assert payload["confidence"] == 0.91
    assert payload["still_duration_ms"] == 1200


def test_event_prompt_preserves_conflicting_data_for_llm_reasoning() -> None:
    prompt = build_event_prompt(
        LlmSpeechRequest(
            event="shaking",
            behavior="calm",
            intensity=0.0,
            summary=MotionSummary(
                peak_angular_speed_dps=141.0,
                peak_dynamic_acceleration_g=0.54,
            ),
            messages=(),
        )
    )

    payload = json.loads(prompt.splitlines()[1])
    assert payload["event"] == "shaking"
    assert payload["behavior"] == "calm"
    assert payload["intensity"] == 0.0
    assert payload["peak_angular_speed_dps"] == 141.0
    assert payload["peak_dynamic_acceleration_g"] == 0.54


def test_touch_prompt_keeps_trigger_value_without_inventing_pressure() -> None:
    prompt = build_event_prompt(
        LlmSpeechRequest(
            event="touch",
            behavior="happy",
            intensity=1.0,
            summary=None,
            messages=(),
        )
    )

    payload = json.loads(prompt.splitlines()[1])
    assert payload == {"event": "touch", "behavior": "happy", "intensity": 1.0}
