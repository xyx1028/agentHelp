"""短期消息窗口策略及进程内实现。

MessageWindowPolicy 负责「怎么裁剪」，InMemoryShortTermMemory 负责「按会话存取」，
两者分离便于单独测试裁剪规则、替换存储后端（如 Redis）。
"""

from __future__ import annotations

from threading import RLock
from typing import Sequence

from langchain_core.messages import BaseMessage

from .models import MemoryScope


class MessageWindowPolicy:
    """按消息数量裁剪，同时避免窗口从孤立 AI 或 ToolMessage 开始。"""

    def __init__(self, max_messages: int):
        if max_messages < 1:
            raise ValueError("max_messages 必须至少为 1。")
        self.max_messages = max_messages

    def apply(self, messages: Sequence[BaseMessage]) -> list[BaseMessage]:
        """保留最近 max_messages 条，并保证窗口不从孤立的 AI/Tool 消息开始。

        若窗口以 ToolMessage 开头，模型会因找不到对应的 tool_call 而报错；
        因此裁剪后继续向前丢弃非 human/system 消息，哪怕窗口因此变得更短。
        """
        if len(messages) <= self.max_messages:
            return list(messages)

        recent = list(messages[-self.max_messages:])
        # 丢弃窗口头部的孤立 AI/Tool 消息，保证剩余序列能从一轮完整的用户输入开始。
        while recent and recent[0].type not in {"human", "system"}:
            recent.pop(0)
        return recent


class InMemoryShortTermMemory:
    """按会话作用域隔离的短期消息窗口；进程重启后数据会丢失。"""

    def __init__(self, window_policy: MessageWindowPolicy):
        self._window_policy = window_policy
        self._messages_by_scope: dict[MemoryScope, list[BaseMessage]] = {}
        self._lock = RLock()

    def load(self, scope: MemoryScope) -> list[BaseMessage]:
        """返回该会话消息的拷贝，调用方修改返回值不影响存储。"""
        with self._lock:
            return list(self._messages_by_scope.get(scope, ()))

    def replace(self, scope: MemoryScope, messages: Sequence[BaseMessage]) -> None:
        """裁剪后覆盖该会话窗口；全程加锁保证并发读写安全。"""
        with self._lock:
            self._messages_by_scope[scope] = self.trim(messages)

    def trim(self, messages: Sequence[BaseMessage]) -> list[BaseMessage]:
        """委托窗口策略裁剪消息，供送入模型前调用。"""
        return self._window_policy.apply(messages)

    def clear(self, scope: MemoryScope) -> None:
        """删除该会话的全部短期消息。"""
        with self._lock:
            self._messages_by_scope.pop(scope, None)
