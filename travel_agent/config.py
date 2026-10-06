"""集中放置 Agent 的运行配置。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSettings:
    """后续可从 .env、配置文件或管理台构造的运行参数。"""

    system_prompt: str = """你是一个旅行助手。用中文简短回答。
需要查询示例旅行资料时，可以调用 travel_guide；不要编造工具返回之外的事实。
工具只能读取资料，不能下单、修改行程或写入数据。"""
    max_history_messages: int = 6
    tool_timeout_seconds: float = 0.3
