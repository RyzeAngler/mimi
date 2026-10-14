"""Typed message values at the Agent/device boundary."""

import time
from dataclasses import dataclass
from typing import Any


def _number(payload: dict[str, Any], name: str, default: float = 0.0) -> float:
    try:
        return float(payload.get(name) if payload.get(name) is not None else default)
    except (TypeError, ValueError):
        return default


def _integer(payload: dict[str, Any], name: str) -> int:
    try:
        return int(payload.get(name) or 0)
    except (TypeError, ValueError):
        return 0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class MotionSummary:
    """Continuous features produced by the firmware motion estimator."""

    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    acceleration_norm_g: float = 0.0
    dynamic_acceleration_g: float = 0.0
    angular_speed_dps: float = 0.0
    motion_intensity: float = 0.0
    stability: float = 1.0
    tilt_strength: float = 0.0
    peak_angular_speed_dps: float = 0.0
    peak_dynamic_acceleration_g: float = 0.0
    confidence: float = 0.0
    still_duration_ms: int = 0
    state_duration_ms: int = 0
    motion_duration_ms: int = 0

    _FIELD_NAMES = frozenset(
        {
            "roll_deg",
            "pitch_deg",
            "acceleration_norm_g",
            "dynamic_acceleration_g",
            "angular_speed_dps",
            "motion_intensity",
            "stability",
            "tilt_strength",
            "peak_angular_speed_dps",
            "peak_dynamic_acceleration_g",
            "confidence",
            "still_duration_ms",
            "state_duration_ms",
            "motion_duration_ms",
        }
    )

    @classmethod
    def present_in(cls, payload: dict[str, Any]) -> bool:
        return bool(cls._FIELD_NAMES.intersection(payload))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MotionSummary":
        return cls(
            roll_deg=_number(payload, "roll_deg"),
            pitch_deg=_number(payload, "pitch_deg"),
            acceleration_norm_g=_number(payload, "acceleration_norm_g"),
            dynamic_acceleration_g=_number(payload, "dynamic_acceleration_g"),
            angular_speed_dps=_number(payload, "angular_speed_dps"),
            motion_intensity=_clamp01(_number(payload, "motion_intensity")),
            stability=_clamp01(_number(payload, "stability", 1.0)),
            tilt_strength=_clamp01(_number(payload, "tilt_strength")),
            peak_angular_speed_dps=_number(payload, "peak_angular_speed_dps"),
            peak_dynamic_acceleration_g=_number(
                payload, "peak_dynamic_acceleration_g"
            ),
            confidence=_clamp01(_number(payload, "confidence")),
            still_duration_ms=_integer(payload, "still_duration_ms"),
            state_duration_ms=_integer(payload, "state_duration_ms"),
            motion_duration_ms=_integer(payload, "motion_duration_ms"),
        )


@dataclass(frozen=True)
class PhysicalEvent:
    event_id: str
    event: str
    behavior: str = ""
    intensity: float = 0.0
    timestamp_ms: int = 0
    summary: MotionSummary | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PhysicalEvent":
        event = str(payload.get("event") or payload.get("motion") or "").strip()
        if not event:
            raise ValueError("motion event must contain a non-empty event")
        event_id = str(payload.get("event_id") or payload.get("id") or "")
        if not event_id:
            event_id = f"evt-{time.time_ns()}"
        intensity = _number(payload, "intensity")
        if "intensity" not in payload and "motion_intensity" in payload:
            intensity = _number(payload, "motion_intensity")
        return cls(
            event_id=event_id,
            event=event,
            behavior=str(payload.get("behavior") or payload.get("mode") or ""),
            intensity=_clamp01(intensity),
            timestamp_ms=_integer(payload, "timestamp_ms")
            or int(time.time() * 1000),
            summary=(
                MotionSummary.from_dict(payload)
                if MotionSummary.present_in(payload)
                else None
            ),
        )


@dataclass(frozen=True)
class SensorTelemetry:
    """One sampled raw view plus the firmware's derived motion summary."""

    timestamp_ms: int
    accel_x_g: float
    accel_y_g: float
    accel_z_g: float
    gyro_x_dps: float
    gyro_y_dps: float
    gyro_z_dps: float
    state: str
    behavior: str
    touch_active: bool
    summary: MotionSummary

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SensorTelemetry":
        return cls(
            timestamp_ms=_integer(payload, "timestamp_ms"),
            accel_x_g=_number(payload, "accel_x_g"),
            accel_y_g=_number(payload, "accel_y_g"),
            accel_z_g=_number(payload, "accel_z_g"),
            gyro_x_dps=_number(payload, "gyro_x_dps"),
            gyro_y_dps=_number(payload, "gyro_y_dps"),
            gyro_z_dps=_number(payload, "gyro_z_dps"),
            state=str(payload.get("state") or "level"),
            behavior=str(payload.get("behavior") or "calm"),
            touch_active=bool(payload.get("touch_active", False)),
            summary=MotionSummary.from_dict(payload),
        )
