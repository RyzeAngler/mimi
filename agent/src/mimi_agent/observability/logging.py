"""Natural-language local logs for debugging a physical Mimi device."""

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
                f"[感知] Mimi 收到了一次{event.event}动作，"
                f"行为状态是{event.behavior or '未标注'}，动作强度为 {event.intensity:.2f}。"
            )
            return
        self._interaction.info(
            f"[感知] Mimi 收到了一次{event.event}动作，"
            f"行为状态是{event.behavior or '未标注'}，动作强度为 {event.intensity:.2f}；"
            f"本次运动持续 {event.summary.motion_duration_ms} 毫秒，"
            f"峰值角速度为 {event.summary.peak_angular_speed_dps:.1f} 度每秒，"
            f"识别置信度为 {event.summary.confidence:.2f}。"
        )

    def sensor(self, telemetry: SensorTelemetry) -> None:
        summary = telemetry.summary
        touch = "，触摸传感器处于按下状态" if telemetry.touch_active else ""
        self._sensor.info(
            f"[芯片] 姿态为{telemetry.state}，行为状态为{telemetry.behavior}；"
            f"加速度是 {telemetry.accel_x_g:.2f}、{telemetry.accel_y_g:.2f}、"
            f"{telemetry.accel_z_g:.2f} g，陀螺仪角速度是 {telemetry.gyro_x_dps:.1f}、"
            f"{telemetry.gyro_y_dps:.1f}、{telemetry.gyro_z_dps:.1f} 度每秒，"
            f"横滚 {summary.roll_deg:.1f} 度、俯仰 {summary.pitch_deg:.1f} 度，"
            f"运动强度 {summary.motion_intensity:.2f}，稳定性 {summary.stability:.2f}，"
            f"峰值角速度 {summary.peak_angular_speed_dps:.1f} 度每秒，"
            f"当前状态持续 {summary.state_duration_ms} 毫秒，"
            f"识别置信度 {summary.confidence:.2f}{touch}。"
        )

    def llm_input(self, speech_id: str, prompt: str) -> None:
        self._interaction.info(
            f"[LLM 输入] 第{speech_id}轮语音的完整输入是：“{_single_line(prompt)}”"
        )

    def llm_output(self, speech_id: str, text: str) -> None:
        self._interaction.info(
            f"[LLM 输出] 第{speech_id}轮语音生成的完整回复是：“{_single_line(text)}”"
        )

    def speech(
        self,
        speech_id: str,
        text: str,
        elapsed_ms: float,
        playback_confirmed: bool = False,
    ) -> None:
        state = "已播放完成" if playback_confirmed else "已发送给设备"
        self._interaction.info(
            f"[语音] 第{speech_id}轮语音{state}，"
            f"内容是：“{_single_line(text)}”，"
            f"总耗时 {elapsed_ms:.0f} 毫秒。"
        )

    def connection(self, message: str) -> None:
        self._interaction.info(f"[连接] {_single_line(message)}")

    def close(self) -> None:
        for logger in (self._interaction, self._sensor):
            for handler in logger.handlers:
                handler.flush()
                handler.close()
                logger.removeHandler(handler)


def _single_line(value: str) -> str:
    return " ".join(value.split())
