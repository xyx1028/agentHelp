"""会话历史的裁剪策略。"""


def trim_messages(messages, max_messages: int):
    """保留最近消息，并从用户消息开始，避免保留孤立的工具结果。"""
    if len(messages) <= max_messages:
        return list(messages)

    recent = list(messages[-max_messages:])
    while recent and recent[0].type not in {"human", "system"}:
        recent.pop(0)
    return recent
