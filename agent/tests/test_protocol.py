import json

from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.protocol.codec import (
    decode_json_message,
    encode_motion_ack,
    encode_speech_end,
    encode_speech_start,
)
from mimi_agent.protocol.messages import PhysicalEvent, SensorTelemetry


def test_physical_event_is_decoded() -> None:
    parsed = PhysicalEvent.from_dict(
        {"type": "motion_event", "event": "tilt_left", "intensity": 0.7}
    )
    assert parsed.event == "tilt_left"
    assert parsed.intensity == 0.7


def test_sensor_telemetry_is_decoded() -> None:
    parsed = SensorTelemetry.from_dict(
        {
            "type": "sensor_telemetry",
            "timestamp_ms": 20,
            "accel_x_g": 0.1,
            "pitch_deg": 14.5,
            "motion_intensity": 1.4,
            "touch_active": True,
        }
    )
    assert parsed.timestamp_ms == 20
    assert parsed.summary.pitch_deg == 14.5
    assert parsed.summary.confidence == 0.0
    assert parsed.summary.motion_intensity == 1.0
    assert parsed.touch_active is True


def test_motion_ack_preserves_event_identity() -> None:
    assert json.loads(encode_motion_ack("evt-1", True)) == {
        "type": "motion_ack",
        "event_id": "evt-1",
        "will_speak": True,
    }


def test_speech_frames_are_json() -> None:
    start = json.loads(encode_speech_start("sp-1", "你好", PcmFormat()))
    end = json.loads(encode_speech_end("sp-1"))
    assert start["type"] == "speech_start"
    assert start["format"] == "pcm_s16le"
    assert end == {"type": "speech_end", "speech_id": "sp-1"}
    assert decode_json_message(encode_speech_end("sp-1"))["type"] == "speech_end"
