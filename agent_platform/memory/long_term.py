"""无外部依赖的进程内长期记忆实现。

按 owner（tenant+user）隔离存储，检索用中文双字 bigram / 英文整词的词面重叠打分；
数据仅存在于当前进程，生产环境可用 SQLite、Redis 或向量库实现同一契约替换。
"""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Iterable
import re

from .models import MemoryOwner, MemoryQuery, MemoryRecord, RetrievedMemory


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)


class InMemoryLongTermMemory:
    """按 owner 隔离的可替换长期记忆 adapter。

    该实现支持跨短期窗口和跨 Agent 实例共享，但仅存在于当前进程；生产环境可用
    SQLite、Redis 或向量库实现同一 ``LongTermMemory`` 契约替换它。
    """

    def __init__(self):
        self._records_by_owner: dict[MemoryOwner, dict[str, MemoryRecord]] = defaultdict(dict)
        self._lock = RLock()

    def upsert(self, records: Iterable[MemoryRecord]) -> None:
        """按记录 id 写入或覆盖；确定性 id 使同一内容重复保存只是覆盖，不会累积。"""
        with self._lock:
            for record in records:
                self._records_by_owner[record.owner][record.id] = record

    def search(self, query: MemoryQuery) -> list[RetrievedMemory]:
        """按词面重叠对相关记忆打分；无命中时回退到该用户的最新记忆。"""
        # 1. 先按 owner 取出候选集：锁内拷贝、锁外打分，缩小临界区。
        with self._lock:
            records = list(self._records_by_owner.get(query.owner, {}).values())

        # 2. 可选地按记忆类型过滤（空 kinds 表示不过滤）。
        if query.kinds:
            allowed_kinds = set(query.kinds)
            records = [record for record in records if record.kind in allowed_kinds]

        # 3. 词面重叠打分：重叠词项数 / 查询词项数；查询无有效词项时全部入选。
        query_terms = set(_extract_terms(query.text))
        ranked: list[RetrievedMemory] = []
        for record in records:
            record_terms = set(_extract_terms(record.content))
            overlap = len(query_terms & record_terms)
            if overlap or not query_terms:
                score = overlap / max(len(query_terms), 1)
                ranked.append(RetrievedMemory(record=record, score=score))

        # 用户偏好往往与当前问题没有词面重合；没有直接命中时回退到最新记忆。
        if not ranked and records:
            ranked = [RetrievedMemory(record=record, score=0.0) for record in records]

        # 4. 分数降序、同分时新记忆优先，最后按 limit 截断。
        ranked.sort(
            key=lambda item: (-item.score, -item.record.created_at.timestamp(), item.record.id),
        )
        return ranked[:query.limit]

    def clear_owner(self, owner: MemoryOwner) -> None:
        """删除该用户名下的全部长期记忆。"""
        with self._lock:
            self._records_by_owner.pop(owner, None)


def _extract_terms(text: str) -> list[str]:
    """独立于 RAG 的轻量分词，避免长期记忆耦合到检索实现细节。"""
    terms: list[str] = []
    for token in _TOKEN_PATTERN.findall(text.lower()):
        if token[0].isascii() or len(token) == 1:
            terms.append(token)
        else:
            terms.extend(token[index:index + 2] for index in range(len(token) - 1))
    return terms
