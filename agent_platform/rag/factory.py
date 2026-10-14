"""RAG 检索后端的装配工厂。

build_knowledge_base 是后端选择的唯一入口：vector（LlamaIndex + Chroma）
服务真实模式；lexical（离线词法倒排）服务评测、mock 与无 embedding 环境。
调用方不感知具体实现，新增后端时仅在此注册。
"""

from __future__ import annotations

from ..config import AgentSettings
from .lexical import LexicalKnowledgeBase
from .models import KnowledgeBase
from .vector import LlamaIndexKnowledgeBase


def build_knowledge_base(
    settings: AgentSettings,
    *,
    embedding_api_key: str | None = None,
    embedding_base_url: str | None = None,
    force_rebuild: bool = False,
) -> KnowledgeBase:
    """按 settings.rag_backend 装配检索后端；embedding 机密由入口显式注入。

    force_rebuild 仅对 vector 后端生效（清空集合后重建索引）；lexical 每次
    构造都从语料全量加载，天然等价于重建，故该参数对它无意义。
    """
    if settings.rag_backend == "lexical":
        return LexicalKnowledgeBase.from_default_file(
            knowledge_dir=settings.rag_knowledge_dir,
            chunk_size=settings.rag_chunk_size,
            max_results=settings.rag_top_k,
        )
    return LlamaIndexKnowledgeBase(
        settings,
        embedding_api_key=embedding_api_key,
        embedding_base_url=embedding_base_url,
        force_rebuild=force_rebuild,
    )
