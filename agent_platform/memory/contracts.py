"""可替换记忆后端的稳定契约。

三个 Protocol 是记忆子系统的依赖倒置边界：AgentMemory 只依赖这里的接口
而非具体实现；换成 SQLite、Redis 或向量库时实现同一签名即可替换。
Protocol 是结构化类型，实现类无需显式继承，方法签名匹配即被类型检查认可。
"""

from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from langchain_core.messages import BaseMessage

from .models import MemoryQuery, MemoryRecord, MemoryScope, RetrievedMemory


class ShortTermMemory(Protocol):
    """按完整会话作用域保存 LangChain 消息窗口。"""

    def load(self, scope: MemoryScope) -> list[BaseMessage]:
        """读取该会话当前保存的消息序列。"""
        ...

    def replace(self, scope: MemoryScope, messages: Sequence[BaseMessage]) -> None:
        """用全量消息覆盖该会话窗口（实现内通常会先按窗口策略裁剪）。"""
        ...

    def trim(self, messages: Sequence[BaseMessage]) -> list[BaseMessage]:
        """按窗口策略裁剪消息序列，不改动存储本身。"""
        ...

    def clear(self, scope: MemoryScope) -> None:
        """清空该会话的短期消息，不影响长期记忆。"""
        ...


class LongTermMemory(Protocol):
    """跨短期窗口、按用户隔离的结构化记忆存储。"""

    def upsert(self, records: Iterable[MemoryRecord]) -> None:
        """按记录 id 写入或覆盖记忆（同 id 幂等）。"""
        ...

    def search(self, query: MemoryQuery) -> list[RetrievedMemory]:
        """按归属边界与查询文本检索记忆，返回带分数的有序结果。"""
        ...

    def clear_owner(self, owner) -> None:
        """删除该用户（tenant+user）名下的全部长期记忆。"""
        ...


class LongTermMemoryWriter(Protocol):
    """定义如何从一轮真实对话中提取可持久化记忆。"""

    def extract(self, scope: MemoryScope, new_messages: Sequence[BaseMessage]) -> list[MemoryRecord]:
        """从本轮新增消息中筛选值得长期保存的内容；返回空列表表示无可提取。"""
        ...
