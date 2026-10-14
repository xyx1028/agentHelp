"""RAG 检索的数据模型与后端契约。

KnowledgeBase 是检索后端的统一边界（typing.Protocol，与 memory 子系统的
契约惯例一致）：工具适配层只依赖它，词法倒排（lexical）与向量检索（vector）
两个实现可自由互换，上层代码与评测断言不受影响。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class KnowledgeChunk:
    """知识库中可检索、可引用的最小文本片段。"""

    source_id: str  # 稳定来源标识，回答中以 [source:...] 形式引用
    title: str
    content: str


@dataclass(frozen=True)
class SearchResult:
    """一次检索命中的片段及其内部排序分数。"""

    chunk: KnowledgeChunk
    score: float  # 后端相关的相关性分数，仅用于排序与观测，跨后端不可比


class KnowledgeBase(Protocol):
    """检索后端契约：按查询返回相关片段，并暴露已索引片段数用于观测。"""

    @property
    def chunk_count(self) -> int:
        """已建立索引的片段数量，便于启动时观察与验证。"""
        ...

    def search(self, query: str, *, top_k: int = 3) -> list[SearchResult]:
        """检索与查询最相关的片段；无命中时返回空列表，由上层提示"资料不足"。"""
        ...
