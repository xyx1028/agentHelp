"""稳定的离线工具回归案例。

EvaluationCase 位置参数顺序（定义见 evaluation/models.py）：
(id, question, scenario, city, expected_tool_names,
 expected_answer_contains, expected_observation_contains, tags)。
scenario 取值对应 evaluation/fakes.py 的 MockScenario，决定 fake 模型与替身工具的行为。
"""

from .models import EvaluationCase, EvaluationSuite


OFFLINE_TOOL_CASES = (
    # —— RAG 命中：三城资料应按各自的 [source:...] 标识引用 ——
    EvaluationCase("rag-hangzhou", "杭州有什么可玩的？", "happy", "杭州", ("search_knowledge",), ("[source:hangzhou-west-lake]",), ("[source:hangzhou-west-lake]",), ("rag",)),
    EvaluationCase("rag-beijing", "北京有哪些注意事项？", "happy", "北京", ("search_knowledge",), ("[source:beijing-palace]",), ("[source:beijing-palace]",), ("rag",)),
    EvaluationCase("rag-shanghai", "上海适合什么时候去外滩？", "happy", "上海", ("search_knowledge",), ("[source:shanghai-bund]",), ("[source:shanghai-bund]",), ("rag",)),
    # —— 天气路由：应调用天气工具并回传模拟预报 ——
    EvaluationCase("weather-hangzhou", "杭州明天天气怎么样？", "weather", "杭州", ("get_weather_forecast",), ("get_weather_forecast 已查询杭州天气",), ("天气预报（模拟）：杭州",), ("weather",)),
    # —— 重复问法：同一城市不同措辞应稳定命中同一来源 ——
    EvaluationCase("rag-hangzhou-repeat", "杭州的资料？", "happy", "杭州", ("search_knowledge",), ("[source:hangzhou-west-lake]",), ("[source:hangzhou-west-lake]",), ("rag",)),
    EvaluationCase("rag-shanghai-repeat", "上海的资料？", "happy", "上海", ("search_knowledge",), ("[source:shanghai-bund]",), ("[source:shanghai-bund]",), ("rag",)),
    # —— 失败路径：未收录 / 超时 / 报错都应如实说明，而非编造结果 ——
    EvaluationCase("rag-miss", "资料库没收录的城市怎么办？", "happy", "南京", ("search_knowledge",), ("未检索到相关资料",), ("未检索到相关资料",), ("rag", "miss")),
    EvaluationCase("rag-timeout", "查询超时怎么办？", "timeout", "杭州", ("search_knowledge",), ("search_knowledge 超时",), ("工具超时：search_knowledge",), ("rag", "failure")),
    EvaluationCase("rag-error", "工具报错怎么办？", "error", "杭州", ("search_knowledge",), ("search_knowledge 返回 ValueError",), ("工具错误：search_knowledge 返回 ValueError",), ("rag", "failure")),
    # —— 无需工具：模型应直接回答，不应强行调用工具 ——
    EvaluationCase("no-tool", "不用查资料，介绍一下你自己。", "no-tool", "杭州", (), ("无需查询",), (), ("no-tool",)),
)

DEFAULT_OFFLINE_TOOL_SUITE = EvaluationSuite(
    name="offline-tool-regression",
    cases=OFFLINE_TOOL_CASES,
)
