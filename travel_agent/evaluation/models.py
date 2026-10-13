"""评测数据、执行结果和报告模型。

分三层：Case/Suite 描述「要验什么」，Execution 是执行器回收的原始观测，
Result/Report 把观测与断言合并为可机器消费的结果（适合接 JSON/CI/仪表盘）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvaluationCase:
    """一个可重复执行的 Agent 行为断言。"""

    id: str                                   # 案例唯一标识，用于在报告中定位
    question: str                             # 模拟用户提问
    scenario: str                             # MockScenario，决定 fake 模型与替身工具行为
    city: str                                 # 传给 fake 模型构造工具调用参数
    expected_tool_names: tuple[str, ...]      # 期望实际调用的工具名序列（空 tuple 表示不应调用工具）
    expected_answer_contains: tuple[str, ...]  # 最终答复必须包含的子串
    expected_observation_contains: tuple[str, ...] = ()  # 工具 observation 必须包含的子串
    tags: tuple[str, ...] = ()                # 分类标签，便于按类筛选统计


@dataclass(frozen=True)
class EvaluationSuite:
    """同一执行模型下的一组评测案例。"""

    name: str
    cases: tuple[EvaluationCase, ...]


@dataclass(frozen=True)
class EvaluationExecution:
    """案例执行器返回的与断言无关的原始观测。"""

    actual_tool_names: tuple[str, ...]  # 实际被调用的工具名序列
    observations: tuple[str, ...]       # 各工具返回的 observation 文本
    answer: str                         # Agent 的最终自然语言答复
    duration_ms: float                  # 该案例端到端耗时（毫秒）


@dataclass(frozen=True)
class EvaluationResult:
    """单个案例的结构化结果，适合后续接 JSON/CI/仪表盘报告器。"""

    case: EvaluationCase                  # 被断言的案例本身
    actual_tool_names: tuple[str, ...]      # 实际被调用的工具名序列
    observations: tuple[str, ...]           # 各工具返回的 observation 文本
    answer: str                             # Agent 的最终自然语言答复
    duration_ms: float                      # 该案例端到端耗时（毫秒）
    failures: tuple[str, ...] = ()          # 逐项比对收集到的失败描述

    @property
    def passed(self) -> bool:
        """无失败描述即视为通过。"""
        return not self.failures


@dataclass(frozen=True)
class EvaluationReport:
    """一个评测套件的完整运行报告。"""

    suite_name: str
    results: tuple[EvaluationResult, ...]
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """全部案例通过，套件才算通过（作为 CLI 退出码依据）。"""
        return all(result.passed for result in self.results)

    @property
    def passed_count(self) -> int:
        """通过的案例数。"""
        return sum(result.passed for result in self.results)

    @property
    def failed_count(self) -> int:
        """失败的案例数。"""
        return len(self.results) - self.passed_count
