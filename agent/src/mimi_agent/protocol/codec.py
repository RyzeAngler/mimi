"""JSON control frames and binary PCM frame metadata."""

import json
from typing import Any

from mimi_agent.audio.pcm import PcmFormat


def decode_json_message(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Mimi control frame must be a JSON object")
    return value


def _encode(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def encode_speech_start(
    speech_id: str,
    text: str,
    audio_format: PcmFormat,
    event_id: str = "",
    text_complete: bool = True,
) -> str:
    audio_format.validate()
    return _encode(
        {
            "type": "speech_start",
            "speech_id": speech_id,
            "event_id": event_id,
            "text": text,
            "text_complete": text_complete,
            "format": audio_format.name,
            "sample_rate": audio_format.sample_rate,
            "channels": audio_format.channels,
        }
    )


def encode_motion_ack(event_id: str, will_speak: bool) -> str:
    return _encode(
        {
            "type": "motion_ack",
            "event_id": event_id,
            "will_speak": will_speak,
        }
    )


def encode_speech_end(speech_id: str) -> str:
    return _encode({"type": "speech_end", "speech_id": speech_id})


def encode_speech_cancel(speech_id: str) -> str:
    return _encode({"type": "speech_cancel", "speech_id": speech_id})


def encode_speech_error(speech_id: str, message: str, event_id: str = "") -> str:
    return _encode(
        {
            "type": "speech_error",
            "speech_id": speech_id,
            "event_id": event_id,
            "message": message,
        }
    )
