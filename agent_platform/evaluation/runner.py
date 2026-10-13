"""通用评测运行器、断言和兼容 CLI 报告器。

流水线：Runner 逐案例调用执行器 → _collect_failures 比对断言 →
EvaluationReport 汇总 → Reporter 渲染输出；执行器与报告器均可替换。
"""

from __future__ import annotations

from typing import Protocol, TextIO
import sys

from .cases import DEFAULT_OFFLINE_TOOL_SUITE
from .executors import OfflineToolCaseExecutor
from .models import EvaluationCase, EvaluationExecution, EvaluationReport, EvaluationResult, EvaluationSuite


class EvaluationCaseExecutor(Protocol):
    """不同 suite 可注入自己的 Agent、模型、记忆或后端装配方式。"""

    def execute(self, case: EvaluationCase) -> EvaluationExecution: ...


class EvaluationRunner:
    """执行任意案例执行器，并返回可供 CI、JSON 或仪表盘复用的结构化报告。"""

    def __init__(self, executor: EvaluationCaseExecutor | None = None):
        self._executor = executor or OfflineToolCaseExecutor()

    def run(self, suite: EvaluationSuite) -> EvaluationReport:
        """顺序执行套件内全部案例，返回结构化报告（不打印、不退出）。"""
        results = tuple(self._run_case(case) for case in suite.cases)
        return EvaluationReport(suite_name=suite.name, results=results)

    def _run_case(self, case: EvaluationCase) -> EvaluationResult:
        """执行单个案例：先回收原始观测，再逐条比对断言生成失败描述。"""
        execution = self._executor.execute(case)
        failures = _collect_failures(
            case,
            execution.actual_tool_names,
            execution.observations,
            execution.answer,
        )
        return EvaluationResult(
            case=case,
            actual_tool_names=execution.actual_tool_names,
            observations=execution.observations,
            answer=execution.answer,
            duration_ms=execution.duration_ms,
            failures=tuple(failures),
        )


class ConsoleReporter:
    """将结构化报告渲染为开发期可读的终端输出。"""

    def write(self, report: EvaluationReport, stream: TextIO | None = None) -> None:
        """逐案例打印状态、观测与失败原因，末尾输出通过数汇总。"""
        stream = stream or sys.stdout
        for index, result in enumerate(report.results, start=1):
            status = "PASS" if result.passed else "FAIL"
            expected_tools = list(result.case.expected_tool_names) or "无"
            actual_tools = list(result.actual_tool_names) or "无"
            print(f"[{index:02d}] {status} | {result.case.id} | 预期工具：{expected_tools} | 实际：{actual_tools}", file=stream)
            print(f"     observation：{' | '.join(result.observations) or '无'}", file=stream)
            print(f"     answer：{result.answer}", file=stream)
            if result.failures:
                print(f"     失败原因：{'；'.join(result.failures)}", file=stream)
        print(
            f"评测结果：{report.passed_count}/{len(report.results)} 通过 | suite={report.suite_name}",
            file=stream,
        )


def run_evaluation(
    suite: EvaluationSuite = DEFAULT_OFFLINE_TOOL_SUITE,
    executor: EvaluationCaseExecutor | None = None,
) -> bool:
    """保持 ``python main.py --evaluate`` 的布尔返回契约，同时支持注入新 suite。"""
    report = EvaluationRunner(executor).run(suite)
    ConsoleReporter().write(report)
    return report.passed


def _collect_failures(
    case: EvaluationCase,
    actual_tool_names: tuple[str, ...],
    observations: tuple[str, ...],
    answer: str,
) -> list[str]:
    """把实际观测与案例断言逐项比对，返回全部失败描述（空列表即通过）。"""
    failures: list[str] = []
    # 工具名序列要求完全相等：既校验路由选择，也校验调用次数。
    if actual_tool_names != case.expected_tool_names:
        failures.append(f"工具调用应为 {case.expected_tool_names}，实际为 {actual_tool_names}")

    observation_text = "\n".join(observations)
    for expected in case.expected_observation_contains:
        if expected not in observation_text:
            failures.append(f"工具 observation 缺少“{expected}”")
    for expected in case.expected_answer_contains:
        if expected not in answer:
            failures.append(f"最终答案缺少“{expected}”")
    return failures
