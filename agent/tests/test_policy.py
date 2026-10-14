from mimi_agent.behavior.speech_policy import SpeechPolicy
from mimi_agent.protocol.messages import MotionSummary, PhysicalEvent


def event(name: str, behavior: str = "") -> PhysicalEvent:
    return PhysicalEvent(event_id="1", event=name, behavior=behavior)


def test_motion_maps_to_speech_key() -> None:
    decision = SpeechPolicy().decide(event("shaking"), now=10.0)
    assert decision is not None
    assert decision.key == "shaking"
    assert decision.priority == 80


def test_touch_has_highest_reaction_priority() -> None:
    touch = SpeechPolicy().decide(event("touch"), now=10.0)
    shaking = SpeechPolicy().decide(event("shaking"), now=10.0)

    assert touch is not None
    assert shaking is not None
    assert touch.priority > shaking.priority


def test_same_action_is_cooled_down() -> None:
    policy = SpeechPolicy(default_cooldown_ms=1000)
    assert policy.decide(event("tilt_left"), now=10.0) is not None
    assert policy.decide(event("tilt_left"), now=10.5) is None
    assert policy.decide(event("tilt_left"), now=11.1) is not None


def test_level_event_is_silent() -> None:
    assert SpeechPolicy().decide(event("level", "calm"), now=10.0) is None


def test_stationary_low_confidence_event_is_silent() -> None:
    stationary = PhysicalEvent(
        event_id="1",
        event="shaking",
        behavior="dizzy",
        intensity=0.0,
        summary=MotionSummary(
            confidence=0.31,
            motion_duration_ms=0,
            peak_angular_speed_dps=0.0,
            peak_dynamic_acceleration_g=0.0,
            tilt_strength=0.02,
        ),
    )

    assert SpeechPolicy().decide(stationary, now=10.0) is None
