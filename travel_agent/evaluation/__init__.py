"""Agent 评测套件公共 API。

离线、确定性、无网络的回归评测：用 fake 模型预置工具调用、用替身工具
模拟各类成功/失败场景，断言 Agent 的工具路由、observation 与最终答复。
"""

from .cases import DEFAULT_OFFLINE_TOOL_SUITE, OFFLINE_TOOL_CASES
from .executors import OfflineToolCaseExecutor
from .fakes import MockScenario, create_mock_model, create_mock_tool_registry
from .models import EvaluationCase, EvaluationExecution, EvaluationReport, EvaluationResult, EvaluationSuite
from .runner import ConsoleReporter, EvaluationCaseExecutor, EvaluationRunner, run_evaluation

__all__ = [
    "ConsoleReporter",
    "DEFAULT_OFFLINE_TOOL_SUITE",
    "EvaluationCase",
    "EvaluationCaseExecutor",
    "EvaluationExecution",
    "EvaluationReport",
    "EvaluationResult",
    "EvaluationRunner",
    "EvaluationSuite",
    "MockScenario",
    "OFFLINE_TOOL_CASES",
    "OfflineToolCaseExecutor",
    "create_mock_model",
    "create_mock_tool_registry",
    "run_evaluation",
]
