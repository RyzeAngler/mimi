from mimi_agent.config import Settings
from mimi_agent.observability import LocalLog
from mimi_agent.protocol.messages import MotionSummary, PhysicalEvent, SensorTelemetry


def test_local_logs_are_natural_language_and_rotated_files(tmp_path) -> None:
    local_log = LocalLog(Settings(log_dir=tmp_path))
    local_log.event(
        PhysicalEvent(event_id="evt-1", event="shaking", behavior="dizzy", intensity=0.8)
    )
    local_log.sensor(
        SensorTelemetry(
            timestamp_ms=10,
            accel_x_g=0.1,
            accel_y_g=0.2,
            accel_z_g=0.9,
            gyro_x_dps=1.0,
            gyro_y_dps=2.0,
            gyro_z_dps=3.0,
            state="shaking",
            behavior="dizzy",
            touch_active=False,
            summary=MotionSummary(
                roll_deg=4.0,
                pitch_deg=5.0,
                angular_speed_dps=6.0,
                motion_intensity=0.7,
                stability=0.4,
                confidence=0.9,
            ),
        )
    )
    local_log.llm_input("sp-1", "动作：shaking")
    local_log.llm_output("sp-1", "别晃啦。")
    local_log.close()

    interaction = (tmp_path / "interaction.log").read_text()
    sensor = (tmp_path / "sensor.log").read_text()
    assert "[LLM 输入]" in interaction
    assert "[LLM 输出]" in interaction
    assert "[芯片]" in sensor
    assert "=" not in interaction + sensor
