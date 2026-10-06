"""离线最小评测集。"""

from dataclasses import dataclass

from .agent import TravelAssistantAgent
from .mocks import MockScenario, create_mock_model


@dataclass(frozen=True)
class EvaluationCase:
    question: str
    city: str
    scenario: MockScenario
    expected_evidence: str


CASES = (
    EvaluationCase("杭州有什么可玩的？", "杭州", "happy", "已查询“杭州”"),
    EvaluationCase("北京有哪些注意事项？", "北京", "happy", "已查询“北京”"),
    EvaluationCase("上海适合什么时候去外滩？", "上海", "happy", "已查询“上海”"),
    EvaluationCase("杭州的资料？", "杭州", "happy", "已查询“杭州”"),
    EvaluationCase("北京的资料？", "北京", "happy", "已查询“北京”"),
    EvaluationCase("上海的资料？", "上海", "happy", "已查询“上海”"),
    EvaluationCase("资料库没收录的城市怎么办？", "南京", "happy", "已查询“南京”"),
    EvaluationCase("查询超时怎么办？", "杭州", "timeout", "travel_guide 超时"),
    EvaluationCase("工具报错怎么办？", "杭州", "error", "travel_guide 返回 ValueError"),
    EvaluationCase("不用查资料，介绍一下你自己。", "杭州", "no-tool", "无需查询"),
)


def run_evaluation() -> bool:
    """输出工具调用和回答证据，返回是否全部通过。"""
    passed = 0
    for index, case in enumerate(CASES, start=1):
        turn = TravelAssistantAgent(create_mock_model(case.scenario, case.city)).ask(case.question)
        tool_names = [message.name for message in turn.messages if message.type == "tool"]
        expected_tool = "travel_guide" if case.scenario != "no-tool" else "无"
        expected_calls = [] if case.scenario == "no-tool" else ["travel_guide"]
        ok = tool_names == expected_calls and case.expected_evidence in turn.answer
        passed += ok
        print(f"[{index:02d}] {'PASS' if ok else 'FAIL'} | 预期工具：{expected_tool} | 实际：{tool_names or '无'}")
        print(f"     答案证据（应含“{case.expected_evidence}”）：{turn.answer}")
    print(f"评测结果：{passed}/{len(CASES)} 通过")
    return passed == len(CASES)
