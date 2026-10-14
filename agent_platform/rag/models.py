"""RAG 检索的数据模型、运行参数与后端契约。

KnowledgeBase 是检索后端的统一边界（typing.Protocol，与 memory 子系统的
契约惯例一致）：工具适配层只依赖它，词法倒排（lexical）与向量检索（vector）
两个实现可自由互换，上层代码与评测断言不受影响。
RagSettings 是两个后端共用的配置，由应用层 AgentSettings 组合引用——
子系统 Settings 定义在自己包内、与 MemorySettings 同一惯例。
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


@dataclass(frozen=True)
class RagSettings:
    """检索子系统的运行参数；vector 与 lexical 两个后端共用同一份配置。

    环境变量只覆盖 backend / embedding_provider / embedding_model 三项（见入口
    _load_settings）；embedding 机密不入本对象，由装配点显式注入。
    """

    backend: str = "vector"  # 检索后端：vector=LlamaIndex+Chroma 向量索引；lexical=离线词法倒排（评测/兜底）
    top_k: int = 3  # 知识库单次检索最多返回的片段数
    chunk_size: int = 260  # 知识库切块的目标字符数（词法后端下限 80；向量后端同样按字符切块）
    knowledge_dir: str = "knowledge"  # 内置语料目录：受控 knowledge_base.md 及用户直接投放的文档
    persist_dir: str = "storage/chroma"  # Chroma 向量索引的本地持久化目录（勿提交版本库）
    embedding_provider: str = "fastembed"  # embedding 提供方：fastembed=本地免费模型（首次运行自动下载）；openai=OpenAI 兼容 API
    embedding_model: str = "BAAI/bge-small-zh-v1.5"  # embedding 模型名；provider=openai 时需改为服务方模型（如 text-embedding-3-small）
    min_score: float = 0.55  # 向量检索的相似度下限（exp(-余弦距离)，越大越相关）；低于视为未命中，防止无关查询返回低分噪声

    def __post_init__(self) -> None:
        """Fail Fast 校验：非法取值在启动装配期暴露，而非拖到首次检索。"""
        if self.backend not in ("vector", "lexical"):
            raise ValueError(f"backend 只支持 vector / lexical，当前为 {self.backend!r}。")
        if self.embedding_provider not in ("fastembed", "openai"):
            raise ValueError(
                f"embedding_provider 只支持 fastembed / openai，当前为 {self.embedding_provider!r}。"
            )
        for field_name in ("knowledge_dir", "persist_dir", "embedding_model"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} 不能为空字符串。")
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError("min_score 必须在 0~1 之间（exp(-距离) 转换后的相似度取值范围）。")
