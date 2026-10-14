"""可扩展的 Agent 工具包。

__all__ 白名单即本包全部对外契约：执行器、注册表模型与组合工厂。
create_rag_tool / create_weather_tool 等适配函数属内部细节，不对外导出；
新增工具的唯一入口是 tools/factory.py 的 build_default_tool_registry。
"""

from .executor import ReadOnlyToolExecutor
from .factory import build_default_tool_registry
from .registry import ToolRegistration, ToolRegistry
from .settings import ToolSettings

__all__ = [
    "ReadOnlyToolExecutor",
    "ToolRegistration",
    "ToolRegistry",
    "ToolSettings",
    "build_default_tool_registry",
]
