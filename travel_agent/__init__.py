"""旅行 Agent 的可扩展包入口。

对外统一从本模块导入；__all__ 白名单内的名字构成稳定公共 API，
内部模块布局（agent/config/rag/weather 及 memory、tools、evaluation 子包）
可自由重构而不影响调用方。
"""

from .agent import AgentTurn, TravelAssistantAgent
from .config import AgentSettings
from .memory import AgentMemory, MemoryRecord, MemoryScope, MemorySettings
from .rag import TravelKnowledgeBase
from .tools import ToolRegistration, ToolRegistry, build_default_tool_registry
from .weather import OpenMeteoWeatherClient

__all__ = [
    "AgentMemory",
    "AgentSettings",
    "AgentTurn",
    "MemoryRecord",
    "MemoryScope",
    "MemorySettings",
    "OpenMeteoWeatherClient",
    "ToolRegistration",
    "ToolRegistry",
    "TravelAssistantAgent",
    "TravelKnowledgeBase",
    "build_default_tool_registry",
]
