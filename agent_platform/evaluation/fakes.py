"""评测与 CLI mock 共用的无网络模型和工具替身。

FakeMessagesListChatModel 按预置队列依次「回复」：第一条发起工具调用，
第二条给出最终答复，从而确定性地驱动 LangGraph 走完 assistant→tools→assistant 循环。
"""

import time
from typing import Literal

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from ..config import AgentSettings
from ..rag import LexicalKnowledgeBase
from ..tools import ToolRegistration, ToolRegistry, build_default_tool_registry


# 五种离线场景：正常 RAG / 天气 / 工具超时 / 工具报错 / 无需工具。
MockScenario = Literal["happy", "weather", "timeout", "error", "no-tool"]
# 城市 → 该城资料在知识库中的 source-id 标识，供构造断言用的模拟答复。
_SOURCE_IDS = {
    "杭州": "[source:hangzhou-west-lake]",
    "北京": "[source:beijing-palace]",
    "上海": "[source:shanghai-bund]",
}


def create_mock_tool_registry(scenario: MockScenario, settings: AgentSettings) -> ToolRegistry:
    """复制默认注册表，只替换当前离线场景需要模拟的单个工具。"""
    # 评测/mock 固定使用词法后端：离线、确定性，与 embedding 模型下载和向量库完全解耦。
    registry = build_default_tool_registry(
        settings,
        knowledge_base=LexicalKnowledgeBase.from_default_file(
            chunk_size=settings.rag_chunk_size,
            max_results=settings.rag_top_k,
        ),
    )

    if scenario in ("timeout", "error"):

        @tool
        def search_knowledge(query: str, top_k: int = 3) -> str:
            """用于离线验证 RAG 工具的超时和错误处理。"""
            if scenario == "timeout":
                time.sleep(0.8)  # 超过默认 0.3s 执行超时，必然触发超时路径
                return "不应返回此结果。"
            raise ValueError("模拟知识库不可用")

        return registry.replace("search_knowledge", ToolRegistration(search_knowledge))

    if scenario == "weather":

        @tool
        def get_weather_forecast(city: str, forecast_days: int = 1) -> str:
            """用于离线验证天气工具的调用和 observation 回流。"""
            return f"天气预报（模拟）：{city}未来 {forecast_days} 天晴，18.0–25.0°C，最大降水概率 10%。"

        return registry.replace(
            "get_weather_forecast",
            ToolRegistration(get_weather_forecast, timeout_seconds=settings.network_tool_timeout_seconds),
        )

    return registry


def create_mock_model(scenario: MockScenario, city: str = "杭州"):
    """预置工具调用，稳定验证 Agent 对 RAG 和天气工具的路由。"""
    if scenario == "no-tool":
        return FakeMessagesListChatModel(responses=[AIMessage(content="这是无需查询的模拟回复。")])

    if scenario == "weather":
        # 预置一次天气工具调用，最终答复声明证据来源。
        tool_call = {
            "name": "get_weather_forecast",
            "args": {"city": city, "forecast_days": 1},
            "id": "mock-call-1",
            "type": "tool_call",
        }
        final_answer = f"【模拟最终回复】证据：get_weather_forecast 已查询{city}天气；建议按实时预报调整出行。"
    else:
        # happy/timeout/error 场景都预置一次 RAG 检索调用，仅最终答复措辞不同。
        tool_call = {
            "name": "search_knowledge",
            "args": {"query": city},
            "id": "mock-call-1",
            "type": "tool_call",
        }
        if scenario == "timeout":
            final_answer = "【模拟最终回复】证据：search_knowledge 超时；因此暂时无法查询，未编造结果。"
        elif scenario == "error":
            final_answer = "【模拟最终回复】证据：search_knowledge 返回 ValueError；因此说明查询失败，未编造结果。"
        elif city in _SOURCE_IDS:
            final_answer = (
                f"【模拟最终回复】证据：已检索“{city}”的资料 {_SOURCE_IDS[city]}；"
                "建议仅依据该资料回答。"
            )
        else:
            final_answer = "【模拟最终回复】证据：未检索到相关资料；因此说明资料不足，未编造结果。"

    # 预置两段回复：第一段带 tool_calls 驱动图进入 tools 节点，第二段为最终答复。
    return FakeMessagesListChatModel(responses=[
        AIMessage(content="我先查询适合的工具。", tool_calls=[tool_call]),
        AIMessage(content=final_answer),
    ])
