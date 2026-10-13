"""工具注册表：集中管理工具、超时策略与供模型阅读的工具目录。

模型 bind_tools、系统 Prompt 工具目录、执行器超时配置三处共用同一个
ToolRegistry 各自取数，从根上避免三处手工维护列表出现不同步。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class ToolRegistration:
    """一个工具及其运行策略；新增工具只需创建并注册此对象。"""

    tool: BaseTool                        # LangChain 工具对象，其 docstring 即模型可见的使用说明
    timeout_seconds: float | None = None  # 该工具的执行超时；None 表示回落到执行器默认超时

    def __post_init__(self) -> None:
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError(f"工具 {self.tool.name} 的超时必须大于 0。")


class ToolRegistry:
    """不可变工具集合，避免模型 Schema、Prompt 与执行器出现不同步。"""

    def __init__(self, registrations: Iterable[ToolRegistration]):
        """构造时固化为元组并 Fail Fast 校验工具名唯一，保证运行期注册表不可变。"""
        self._registrations = tuple(registrations)
        names = [registration.tool.name for registration in self._registrations]
        duplicated_names = sorted({name for name in names if names.count(name) > 1})
        if duplicated_names:
            raise ValueError(f"工具名称不能重复：{', '.join(duplicated_names)}")

    @property
    def registrations(self) -> tuple[ToolRegistration, ...]:
        return self._registrations

    @property
    def tools(self) -> tuple[BaseTool, ...]:
        """用于模型 bind_tools() 的 LangChain 工具列表。"""
        return tuple(registration.tool for registration in self._registrations)

    @property
    def timeouts_by_name(self) -> dict[str, float]:
        """返回显式配置了专用超时的工具映射。"""
        return {
            registration.tool.name: registration.timeout_seconds
            for registration in self._registrations
            if registration.timeout_seconds is not None
        }

    def bind_model(self, model: Any) -> Any:
        """以注册表工具 Schema 绑定模型；不支持绑定的测试替身保持原样。"""
        bind_tools = getattr(model, "bind_tools", None)
        if not callable(bind_tools) or not self._registrations:
            return model  # 无工具或模型不支持绑定时直接透传
        try:
            bound_model = bind_tools(self.tools)
        except NotImplementedError:
            return model  # 某些测试替身声明了 bind_tools 但未实现
        return model if bound_model is None else bound_model

    def prompt_catalog(self) -> str:
        """从工具自身 description 动态生成模型可见目录，无需在 Prompt 手工维护工具名。"""
        if not self._registrations:
            return "（当前没有可调用工具。）"
        lines = []
        for registration in self._registrations:
            description = " ".join((registration.tool.description or "无说明。").split())
            lines.append(f"- {registration.tool.name}：{description}")
        return "\n".join(lines)

    def replace(self, tool_name: str, registration: ToolRegistration) -> "ToolRegistry":
        """返回替换指定工具后的新注册表，供 mock 和集成测试注入替身。"""
        if registration.tool.name != tool_name:
            raise ValueError("替换工具时，注册工具名必须与目标工具名一致。")

        # 注册表不可变：逐条复制并用替身换掉目标工具，返回新实例。
        replaced = False
        registrations: list[ToolRegistration] = []
        for current in self._registrations:
            if current.tool.name == tool_name:
                registrations.append(registration)
                replaced = True
            else:
                registrations.append(current)
        if not replaced:
            raise KeyError(f"未注册工具：{tool_name}")
        return ToolRegistry(registrations)
