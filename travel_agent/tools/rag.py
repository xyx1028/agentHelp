"""本地旅行知识库的 LangChain 工具适配层。

闭包捕获已构造的 TravelKnowledgeBase，@tool 装饰器把内层函数注册为
LangChain 工具；内层函数的 docstring 是给 LLM 阅读的使用说明，
直接决定模型何时调用它、传什么参数。检索细节保留在领域组件 travel_agent.rag。
"""

from langchain_core.tools import tool

from ..rag import SearchResult, TravelKnowledgeBase
from .registry import ToolRegistration


def create_rag_tool(knowledge_base: TravelKnowledgeBase) -> ToolRegistration:
    """创建 RAG 工具；检索细节保留在领域组件 ``travel_agent.rag`` 中。"""

    @tool
    def search_travel_knowledge(query: str, top_k: int = 3) -> str:
        """检索本地旅行知识库中的景点、交通、路线和规则资料，返回带 [source:...] 标识的证据。需要旅行事实或用户明确要求查资料时使用。"""
        # 未命中时返回引导性文本，提醒模型如实说明资料不足而非编造。
        results = knowledge_base.search(query, top_k=top_k)
        if not results:
            return "检索结果：未检索到相关旅行资料。请明确说明资料不足，不要补充未检索到的事实。"
        return _format_search_results(results)

    return ToolRegistration(tool=search_travel_knowledge)


def _format_search_results(results: list[SearchResult]) -> str:
    """把命中片段拼成带 [source:...] 标识的 observation，供模型引用来源作答。"""
    observations = ["检索结果（仅可依据以下资料回答）："]
    for result in results:
        chunk = result.chunk
        observations.append(f"[source:{chunk.source_id}] {chunk.title}\n{chunk.content}")
    return "\n\n".join(observations)
