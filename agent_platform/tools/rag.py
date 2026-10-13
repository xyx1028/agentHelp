"""本地知识库的 LangChain 工具适配层。

闭包捕获已构造的 KnowledgeBase，@tool 装饰器把内层函数注册为
LangChain 工具；内层函数的 docstring 是给 LLM 阅读的使用说明，
直接决定模型何时调用它、传什么参数。检索细节保留在领域组件 agent_platform.rag。
"""

from langchain_core.tools import tool

from ..rag import SearchResult, KnowledgeBase
from .registry import ToolRegistration


def create_rag_tool(knowledge_base: KnowledgeBase) -> ToolRegistration:
    """创建 RAG 工具；检索细节保留在领域组件 ``agent_platform.rag`` 中。"""

    @tool
    def search_knowledge(query: str, top_k: int = 3) -> str:
        """检索本地知识库中的资料，返回带 [source:...] 来源标识的证据。用户问题涉及知识库可能收录的特定资料、或明确要求查资料时使用；常识性、闲聊性问题不必调用。"""
        # 未命中时明确告知知识库无资料；模型可凭自身知识回答，但须声明来源不是知识库。
        results = knowledge_base.search(query, top_k=top_k)
        if not results:
            return "检索结果：本地知识库未检索到相关资料。可凭自身知识回答，但需说明该回答并非来自知识库。"
        return _format_search_results(results)

    return ToolRegistration(tool=search_knowledge)


def _format_search_results(results: list[SearchResult]) -> str:
    """把命中片段拼成带 [source:...] 标识的 observation，供模型引用来源作答。"""
    observations = ["检索结果（以下来自本地知识库的资料优先于你的既有知识，回答时注明来源）："]
    for result in results:
        chunk = result.chunk
        observations.append(f"[source:{chunk.source_id}] {chunk.title}\n{chunk.content}")
    return "\n\n".join(observations)
