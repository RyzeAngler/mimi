"""Natural-language local logs for debugging a physical Mimi device."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mimi_agent.config import Settings
from mimi_agent.protocol.messages import PhysicalEvent, SensorTelemetry


class LocalLog:
    """Write human-readable interaction and sensor records to rotating files."""

    def __init__(self, settings: Settings) -> None:
        directory = Path(settings.log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        self._interaction = self._build_logger(
            "mimi.local.interaction",
            directory / "interaction.log",
            settings,
        )
        self._sensor = self._build_logger(
            "mimi.local.sensor",
            directory / "sensor.log",
            settings,
        )

    @staticmethod
    def _build_logger(name: str, path: Path, settings: Settings) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            handler = RotatingFileHandler(
                path,
                maxBytes=settings.log_max_bytes,
                backupCount=settings.log_backup_count,
                encoding="utf-8",
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
            )
            logger.addHandler(handler)
        return logger

    def event(self, event: PhysicalEvent) -> None:
        if event.summary is None:
            self._interaction.info(
                "[感知] Mimi 收到了一次%s动作，行为状态是%s，动作强度为 %.2f。",
                event.event,
                event.behavior or "未标注",
                event.intensity,
            )
            return
        self._interaction.info(
            "[感知] Mimi 收到了一次%s动作，行为状态是%s，动作强度为 %.2f；"
            "本次运动持续 %d 毫秒，峰值角速度为 %.1f 度每秒，识别置信度为 %.2f。",
            event.event,
            event.behavior or "未标注",
            event.intensity,
            event.summary.motion_duration_ms,
            event.summary.peak_angular_speed_dps,
            event.summary.confidence,
        )

    def sensor(self, telemetry: SensorTelemetry) -> None:
        summary = telemetry.summary
        touch = "，触摸传感器处于按下状态" if telemetry.touch_active else ""
        self._sensor.info(
            "[芯片] 姿态为%s，行为状态为%s；加速度是 %.2f、%.2f、%.2f g，"
            "陀螺仪角速度是 %.1f、%.1f、%.1f 度每秒，横滚 %.1f 度、俯仰 %.1f 度，"
            "运动强度 %.2f，稳定性 %.2f，峰值角速度 %.1f 度每秒，"
            "当前状态持续 %d 毫秒，识别置信度 %.2f%s。",
            telemetry.state,
            telemetry.behavior,
            telemetry.accel_x_g,
            telemetry.accel_y_g,
            telemetry.accel_z_g,
            telemetry.gyro_x_dps,
            telemetry.gyro_y_dps,
            telemetry.gyro_z_dps,
            summary.roll_deg,
            summary.pitch_deg,
            summary.motion_intensity,
            summary.stability,
            summary.peak_angular_speed_dps,
            summary.state_duration_ms,
            summary.confidence,
            touch,
        )

    def llm_input(self, speech_id: str, prompt: str) -> None:
        self._interaction.info(
            "[LLM 输入] 第%s轮语音的完整输入是：“%s”",
            speech_id,
            _single_line(prompt),
        )

    def llm_output(self, speech_id: str, text: str) -> None:
        self._interaction.info(
            "[LLM 输出] 第%s轮语音生成的完整回复是：“%s”",
            speech_id,
            _single_line(text),
        )

    def speech(self, speech_id: str, text: str, elapsed_ms: float) -> None:
        self._interaction.info(
            "[语音] 第%s轮语音已经播放完成，内容是：“%s”，总耗时 %.0f 毫秒。",
            speech_id,
            _single_line(text),
            elapsed_ms,
        )

    def connection(self, message: str) -> None:
        self._interaction.info("[连接] %s", _single_line(message))

    def close(self) -> None:
        for logger in (self._interaction, self._sensor):
            for handler in logger.handlers:
                handler.flush()
                handler.close()
                logger.removeHandler(handler)


def _single_line(value: str) -> str:
    return " ".join(value.split())
