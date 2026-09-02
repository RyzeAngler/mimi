from mimi_agent.agent_core.conversation import ConversationHistory


def test_history_keeps_latest_ten_turns_and_system_prompt() -> None:
    history = ConversationHistory(max_turns=10)
    for index in range(1, 13):
        history.append(f"动作输入 {index}", f"Mimi 回复 {index}")

    messages = history.messages("始终存在的角色设定", "动作输入 13")

    assert messages[0].role == "system"
    assert messages[0].content == "始终存在的角色设定"
    assert messages[-1].role == "user"
    assert messages[-1].content == "动作输入 13"
    assert len(messages) == 22
    assert messages[1].content == "动作输入 3"
    assert messages[2].content == "Mimi 回复 3"
    assert messages[-2].content == "Mimi 回复 12"


def test_history_rejects_empty_turns() -> None:
    history = ConversationHistory()

    try:
        history.append("", "回复")
    except ValueError as exc:
        assert "user and assistant" in str(exc)
    else:
        raise AssertionError("empty conversation turns must be rejected")
