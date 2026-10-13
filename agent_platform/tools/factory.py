"""默认工具组合；后续新增工具只在此处显式注册。

这是工具系统的「组合根」：统一构造领域客户端（知识库、天气客户端），
经各自适配层包成 LangChain 工具后注册进 ToolRegistry。
knowledge_base / weather_client 为可选注入点，便于单元测试替换为 mock。
"""

from __future__ import annotations

from ..config import AgentSettings
from ..rag import KnowledgeBase
from ..weather import OpenMeteoWeatherClient
from .rag import create_rag_tool
from .registry import ToolRegistry
from .weather import create_weather_tool


def build_default_tool_registry(
    settings: AgentSettings,
    *,
    knowledge_base: KnowledgeBase | None = None,
    weather_client: OpenMeteoWeatherClient | None = None,
) -> ToolRegistry:
    """构造当前应用的工具集合；模型绑定、Prompt 和执行器共用同一个注册表。"""
    # 缺省时用项目内置语料/默认客户端自建，测试则注入替身。
    knowledge_base = knowledge_base or KnowledgeBase.from_default_file(
        chunk_size=settings.rag_chunk_size,
        max_results=settings.rag_top_k,
    )
    weather_client = weather_client or OpenMeteoWeatherClient(settings.weather_request_timeout_seconds)
    return ToolRegistry((
        # 本地检索工具：不设专用超时，走执行器默认的 0.3s 兜底。
        create_rag_tool(knowledge_base),
        # 天气工具：网络调用耗时长，标记专用超时覆盖默认值。
        create_weather_tool(weather_client, timeout_seconds=settings.network_tool_timeout_seconds),
    ))
