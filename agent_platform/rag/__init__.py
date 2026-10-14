"""RAG 检索子系统：统一契约 + 词法/向量双后端。

后端边界是 models.KnowledgeBase（Protocol），工具适配层只依赖它：
- lexical：离线确定性词法倒排，服务评测、mock 与无 embedding 环境的兜底；
- vector：LlamaIndex + Chroma 本地向量检索，真实模式的默认后端。
build_knowledge_base 按 settings.rag_backend 装配，新增后端在 factory 注册。
"""

from .factory import build_knowledge_base
from .lexical import LexicalKnowledgeBase
from .models import KnowledgeBase, KnowledgeChunk, SearchResult
from .vector import LlamaIndexKnowledgeBase

__all__ = [
    "KnowledgeBase",
    "KnowledgeChunk",
    "LexicalKnowledgeBase",
    "LlamaIndexKnowledgeBase",
    "SearchResult",
    "build_knowledge_base",
]
