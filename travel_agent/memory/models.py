"""记忆域的数据模型；不依赖 Agent、ToolRegistry 或具体存储后端。

两类隔离边界：
- MemoryScope（tenant + user + conversation 三级）：短期消息窗口按完整三级隔离；
- MemoryOwner（tenant + user 两级）：长期记忆按用户归属，可跨会话召回。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4


class MemoryKind(str, Enum):
    """长期记忆的语义类型，后续可扩展为摘要、档案或业务实体。"""

    PREFERENCE = "preference"  # 用户偏好，如“喜欢安静的咖啡馆”
    CONSTRAINT = "constraint"  # 硬性约束，如“预算不超过 2000”“海鲜过敏”
    PROFILE = "profile"        # 用户档案事实，如“带两个孩子出行”
    SUMMARY = "summary"        # 会话摘要（预留类型，当前未启用）


@dataclass(frozen=True)
class MemoryOwner:
    """长期记忆的隔离边界；同一用户可拥有多个会话。"""

    tenant_id: str  # 租户标识，多租户部署时的最外层隔离边界
    user_id: str    # 用户标识，长期记忆按 tenant+user 归属

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.user_id.strip():
            raise ValueError("tenant_id 和 user_id 都不能为空。")


@dataclass(frozen=True)
class MemoryScope:
    """一次对话使用的完整记忆作用域。"""

    tenant_id: str = "local"
    user_id: str = "default"
    conversation_id: str = "default"  # 会话标识，短期窗口按 conversation 一级隔离

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.user_id.strip() or not self.conversation_id.strip():
            raise ValueError("tenant_id、user_id 和 conversation_id 都不能为空。")

    @property
    def owner(self) -> MemoryOwner:
        """由作用域派生长期记忆的归属边界（去掉 conversation 一级）。"""
        return MemoryOwner(tenant_id=self.tenant_id, user_id=self.user_id)

    @classmethod
    def local(cls) -> "MemoryScope":
        """返回适用于本地 CLI 演示的默认作用域。"""
        return cls()


@dataclass(frozen=True)
class MemoryRecord:
    """一条可跨短期窗口、可跨会话召回的用户记忆。"""

    owner: MemoryOwner           # 归属边界，检索时按它过滤
    content: str                 # 记忆正文（用户显式保存的偏好/约束）
    kind: MemoryKind = MemoryKind.PREFERENCE
    id: str = field(default_factory=lambda: uuid4().hex)  # 缺省随机 id；writer 改用确定性 id 实现幂等覆盖
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_turn_id: str | None = None  # 溯源：产生该记忆的消息 id
    metadata: Mapping[str, str] = field(default_factory=dict)  # 附加信息，构造后固化为只读

    def __post_init__(self) -> None:
        """Fail Fast 校验，并把 metadata 固化为只读视图，防止共享引用被外部篡改。"""
        if not self.id.strip() or not self.content.strip():
            raise ValueError("记忆 id 和 content 都不能为空。")
        if self.created_at.tzinfo is None:
            raise ValueError("记忆 created_at 必须带时区。")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class MemoryQuery:
    """长期记忆检索请求。"""

    owner: MemoryOwner
    text: str                            # 查询文本（通常是当前用户问题）
    limit: int = 5                       # 最多返回的记忆条数
    kinds: tuple[MemoryKind, ...] = ()   # 空元组表示不按类型过滤

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("记忆检索 limit 必须至少为 1。")


@dataclass(frozen=True)
class RetrievedMemory:
    """检索结果及分数；未来向量检索可保持同一返回契约。"""

    record: MemoryRecord
    score: float


@dataclass(frozen=True)
class MemorySettings:
    """记忆门面的通用运行参数。"""

    short_term_max_messages: int = 6              # 送入模型的短期窗口最大消息数
    long_term_retrieval_limit: int = 4            # 单次召回的长期记忆条数上限
    long_term_context_max_characters: int = 800   # 注入 Prompt 的长期记忆字符预算（下限 80 防误配）

    def __post_init__(self) -> None:
        if self.short_term_max_messages < 1:
            raise ValueError("short_term_max_messages 必须至少为 1。")
        if self.long_term_retrieval_limit < 1:
            raise ValueError("long_term_retrieval_limit 必须至少为 1。")
        if self.long_term_context_max_characters < 80:
            raise ValueError("long_term_context_max_characters 不能小于 80。")
