"""可替换的评测案例执行器。

执行器负责「如何跑一个案例」，与 runner 的「如何断言」解耦：
换成真实模型或其他装配方式时，只需实现同一 execute 契约。
"""

from __future__ import annotations

from time import perf_counter

from ..agent import TravelAssistantAgent
from ..config import AgentSettings
from .fakes import create_mock_model, create_mock_tool_registry
from .models import EvaluationCase, EvaluationExecution


class OfflineToolCaseExecutor:
    """当前默认执行器：使用确定性 fake 验证工具编排，不访问网络。"""

    def __init__(self, settings: AgentSettings | None = None):
        self._settings = settings or AgentSettings()

    def execute(self, case: EvaluationCase) -> EvaluationExecution:
        """按案例场景组装 fake 模型与替身工具，跑一轮问答并回收原始观测。"""
        started_at = perf_counter()
        # 每个案例独立组装注册表与 Agent：互不污染，结果可复现。
        tool_registry = create_mock_tool_registry(case.scenario, self._settings)
        turn = TravelAssistantAgent(
            create_mock_model(case.scenario, case.city),
            settings=self._settings,
            tool_registry=tool_registry,
        ).ask(case.question)
        # 只抽取 ToolMessage 作为观测：工具名序列与 observation 文本是断言对象。
        tool_messages = [message for message in turn.messages if message.type == "tool"]
        return EvaluationExecution(
            actual_tool_names=tuple(message.name for message in tool_messages),
            observations=tuple(str(message.content) for message in tool_messages),
            answer=str(turn.answer),
            duration_ms=(perf_counter() - started_at) * 1_000,
        )
