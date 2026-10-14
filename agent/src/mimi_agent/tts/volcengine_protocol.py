"""Binary framing for Volcengine V3 bidirectional TTS WebSockets."""

import gzip
import json
import struct
from dataclasses import dataclass
from typing import Any

FULL_CLIENT_REQUEST = 0x1
FULL_SERVER_RESPONSE = 0x9
AUDIO_ONLY_RESPONSE = 0xB
ERROR_INFORMATION = 0xF
WITH_EVENT = 0x4
JSON_SERIALIZATION = 0x1
RAW_SERIALIZATION = 0x0
GZIP_COMPRESSION = 0x1

START_CONNECTION = 1
FINISH_CONNECTION = 2
CONNECTION_STARTED = 50
CONNECTION_FAILED = 51
CONNECTION_FINISHED = 52
START_SESSION = 100
CANCEL_SESSION = 101
FINISH_SESSION = 102
SESSION_STARTED = 150
SESSION_CANCELED = 151
SESSION_FINISHED = 152
SESSION_FAILED = 153
TASK_REQUEST = 200
TTS_SENTENCE_START = 350
TTS_SENTENCE_END = 351
TTS_RESPONSE = 352
TTS_ENDED = 359
TTS_SUBTITLE = 364


class VolcengineProtocolError(RuntimeError):
    """Raised for malformed or provider-error binary frames."""


@dataclass(frozen=True)
class ServerFrame:
    event: int | None
    identifier: str
    payload: bytes
    message_type: int
    serialization: int
    error_code: int | None = None

    def json_payload(self) -> dict[str, Any]:
        if not self.payload:
            return {}
        try:
            value = json.loads(self.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VolcengineProtocolError("invalid JSON payload from TTS") from exc
        return value if isinstance(value, dict) else {}


def encode_event(
    event: int,
    payload: dict[str, Any] | None = None,
    *,
    session_id: str = "",
) -> bytes:
    body = json.dumps(
        payload or {}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    frame = bytearray((0x11, (FULL_CLIENT_REQUEST << 4) | WITH_EVENT, 0x10, 0x00))
    frame.extend(struct.pack(">I", event))
    if session_id:
        encoded_session = session_id.encode("utf-8")
        frame.extend(struct.pack(">I", len(encoded_session)))
        frame.extend(encoded_session)
    frame.extend(struct.pack(">I", len(body)))
    frame.extend(body)
    return bytes(frame)


def parse_server_frame(data: bytes) -> ServerFrame:
    if len(data) < 8:
        raise VolcengineProtocolError("TTS frame is too short")
    version = data[0] >> 4
    header_size = (data[0] & 0x0F) * 4
    if version != 1 or header_size < 4 or len(data) < header_size + 4:
        raise VolcengineProtocolError("unsupported TTS protocol header")

    message_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F
    offset = header_size

    if message_type == ERROR_INFORMATION:
        error_code, offset = _read_u32(data, offset)
        payload, _ = _read_sized_bytes(data, offset)
        return ServerFrame(
            event=None,
            identifier="",
            payload=_decompress(payload, compression),
            message_type=message_type,
            serialization=serialization,
            error_code=error_code,
        )

    if not flags & WITH_EVENT:
        raise VolcengineProtocolError("TTS frame is missing an event number")
    event, offset = _read_u32(data, offset)
    identifier_bytes, offset = _read_sized_bytes(data, offset)
    declared_size, offset = _read_u32(data, offset)
    if event in {TTS_SENTENCE_START, TTS_SENTENCE_END}:
        # Volcengine documents that these two events may report Unicode
        # character count instead of UTF-8 byte count. The WebSocket frame is
        # already message-bounded, so consume its remaining bytes.
        payload = data[offset:]
        offset = len(data)
    else:
        end = offset + declared_size
        if end > len(data):
            raise VolcengineProtocolError("truncated TTS payload")
        payload = data[offset:end]
        offset = end
        if offset != len(data):
            raise VolcengineProtocolError("TTS frame contains trailing bytes")
    try:
        identifier = identifier_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VolcengineProtocolError("invalid TTS connection/session id") from exc
    return ServerFrame(
        event=event,
        identifier=identifier,
        payload=_decompress(payload, compression),
        message_type=message_type,
        serialization=serialization,
    )


def provider_error(frame: ServerFrame) -> VolcengineProtocolError:
    if frame.error_code is not None:
        detail = frame.payload.decode("utf-8", errors="replace")
        return VolcengineProtocolError(
            f"Volcengine TTS protocol error {frame.error_code}: {detail[:500]}"
        )
    detail = frame.json_payload()
    return VolcengineProtocolError(
        "Volcengine TTS session failed: "
        f"code={detail.get('status_code', '')}, message={detail.get('message', '')}"
    )


def _read_u32(data: bytes, offset: int) -> tuple[int, int]:
    if offset + 4 > len(data):
        raise VolcengineProtocolError("truncated TTS integer field")
    return struct.unpack_from(">I", data, offset)[0], offset + 4


def _read_sized_bytes(data: bytes, offset: int) -> tuple[bytes, int]:
    size, offset = _read_u32(data, offset)
    end = offset + size
    if end > len(data):
        raise VolcengineProtocolError("truncated TTS payload")
    return data[offset:end], end


def _decompress(payload: bytes, compression: int) -> bytes:
    if compression == 0:
        return payload
    if compression == GZIP_COMPRESSION:
        try:
            return gzip.decompress(payload)
        except gzip.BadGzipFile as exc:
            raise VolcengineProtocolError("invalid gzip TTS payload") from exc
    raise VolcengineProtocolError(f"unsupported TTS compression {compression}")
