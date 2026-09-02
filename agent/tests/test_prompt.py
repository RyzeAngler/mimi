import json

from mimi_agent.agent_core.prompt import (
    CHARACTER_PROFILE,
    PERFORMANCE_PROMPT,
    SENSOR_CONTRACT,
    SYSTEM_PROMPT,
    build_event_prompt,
)
from mimi_agent.agent_core.llm import LlmSpeechRequest
from mimi_agent.protocol.messages import MotionSummary


def test_prompt_defines_mimi_before_event_instructions() -> None:
    role_index = SYSTEM_PROMPT.index("# 角色档案")
    biography_index = SYSTEM_PROMPT.index("# 人物小传")
    personality_index = SYSTEM_PROMPT.index("# 性格结构")
    sensor_index = SYSTEM_PROMPT.index("# 场景数据")
    boundary_index = SYSTEM_PROMPT.index("# 判定边界")
    performance_index = SYSTEM_PROMPT.index("# 本场表演")

    assert (
        role_index
        < biography_index
        < personality_index
        < sensor_index
        < boundary_index
        < performance_index
    )
    assert "Mimi，女性，18岁" in CHARACTER_PROFILE
    assert "海边小城" in CHARACTER_PROFILE
    assert "老钟表店" in CHARACTER_PROFILE
    assert "最亲近的同住者" in CHARACTER_PROFILE
    assert "相处建立在平等和默契上" in CHARACTER_PROFILE
    assert "越害怕失去，越装作不在乎" in CHARACTER_PROFILE
    assert "宠物" not in CHARACTER_PROFILE
    assert "主人" not in CHARACTER_PROFILE
    assert "AI" not in CHARACTER_PROFILE
    assert "字段是本场戏实际发生的身体事实" in SENSOR_CONTRACT
    assert "像演员进入角色一样回应" in PERFORMANCE_PROMPT
    assert "intensity：当前综合运动强度，范围 [0, 1]" in SYSTEM_PROMPT
    assert "roll_deg：左右横滚角，范围 [-180, 180]" in SYSTEM_PROMPT
    assert "pitch_deg：前后俯仰角，范围 [-90, 90]" in SYSTEM_PROMPT
    assert "角速度超过 180 度/秒" in SYSTEM_PROMPT
    assert "偏离 1g 超过 0.30g" in SYSTEM_PROMPT


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
    assert "身体向前倾了一下" not in prompt
    assert "你有点晕" not in prompt


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
    assert "不高兴" not in prompt


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
    assert "touch 事件固定为 1" in SYSTEM_PROMPT
    assert "不代表按压力度" in SYSTEM_PROMPT
