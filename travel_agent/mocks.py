"""不访问网络的模型替身，专门用于演示与回归测试。"""

from typing import Literal

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


MockScenario = Literal["happy", "timeout", "error", "no-tool"]


def create_mock_model(scenario: MockScenario, city: str = "杭州"):
    """预置“tool_calls -> 最终回答”，稳定验证 Agent 流程而不调用真实模型。"""
    if scenario == "no-tool":
        return FakeMessagesListChatModel(responses=[AIMessage(content="这是无需查询的模拟回复。")])

    tool_city = {"happy": city, "timeout": "超时城市", "error": "错误城市"}[scenario]
    tool_call = {"name": "travel_guide", "args": {"city": tool_city}, "id": "mock-call-1", "type": "tool_call"}
    if scenario == "timeout":
        final_answer = "【模拟最终回复】证据：travel_guide 超时；因此暂时无法查询，未编造行程。"
    elif scenario == "error":
        final_answer = "【模拟最终回复】证据：travel_guide 返回 ValueError；因此说明查询失败，未编造结果。"
    else:
        final_answer = f"【模拟最终回复】证据：travel_guide 已查询“{city}”的示例资料；建议以该资料安排路线。"
    return FakeMessagesListChatModel(responses=[
        AIMessage(content="我先查询示例旅行资料。", tool_calls=[tool_call]),
        AIMessage(content=final_answer),
    ])
