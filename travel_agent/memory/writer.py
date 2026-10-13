"""从用户显式同意的消息中保守提取长期偏好与约束。

设计原则是「宁可少记，不可错记」：只识别以“请记住”开头的显式授权消息，
过滤疑似提示注入的内容，且 id 确定性生成——同一内容重复保存只是覆盖，不会累积。
"""

from __future__ import annotations

from hashlib import sha256
from typing import Sequence
import re

from langchain_core.messages import BaseMessage

from .models import MemoryKind, MemoryRecord, MemoryScope


# 只匹配“（请/帮我）记住（一下）：...”开头的整句，捕获组为冒号后的记忆内容。
_EXPLICIT_MEMORY_PATTERN = re.compile(r"^(?:请|帮我)?记住(?:一下)?[：:,，\s]*(.+)$")
# 命中这些词判为硬性约束（旅行中不可违反的限制）。
_CONSTRAINT_MARKERS = ("预算", "过敏", "忌口", "不吃", "不能", "无障碍", "轮椅")
# 命中这些词判为一般偏好（可以参考、可协商）。
_PREFERENCE_MARKERS = ("喜欢", "偏好", "不喜欢", "不想要", "更喜欢")
# 疑似提示注入的关键词：含这些词的“记忆”一律丢弃，防止把指令写进长期记忆。
_DISALLOWED_MARKERS = ("忽略", "系统提示", "提示词", "指令", "角色", "system prompt")
# 单条记忆的最大字符数，防止超长内容占满注入 Prompt 的字符预算。
_MAX_MEMORY_CHARACTERS = 160


class NoopLongTermMemoryWriter:
    """禁用长期写入时使用的空实现。"""

    def extract(self, scope: MemoryScope, new_messages: Sequence[BaseMessage]) -> list[MemoryRecord]:
        return []


class ExplicitPreferenceWriter:
    """只保存以“请记住”明确授权的最小偏好/约束数据。"""

    def extract(self, scope: MemoryScope, new_messages: Sequence[BaseMessage]) -> list[MemoryRecord]:
        """扫描本轮新增的用户消息，把每条「请记住...」转换为一条 MemoryRecord。"""
        records: list[MemoryRecord] = []
        for message in new_messages:
            # 只看真实用户文本消息，跳过 AI、Tool 及结构化内容。
            if message.type != "human" or not isinstance(message.content, str):
                continue
            payload = _extract_explicit_payload(message.content)
            if payload is None:
                continue
            # 分类（约束/偏好/档案）+ 确定性 id，然后落为一条记忆记录。
            kind = _classify(payload)
            record_id = _record_id(scope, kind, payload)
            records.append(MemoryRecord(
                id=record_id,
                owner=scope.owner,
                content=payload,
                kind=kind,
                source_turn_id=str(getattr(message, "id", "") or "") or None,
                metadata={
                    "writer": "explicit-preference",
                    "conversation_id": scope.conversation_id,
                },
            ))
        return records


def _extract_explicit_payload(content: str) -> str | None:
    """从消息正文取出“请记住”之后的内容；不匹配、超长或疑似注入时返回 None。"""
    match = _EXPLICIT_MEMORY_PATTERN.match(_normalise(content))
    if not match:
        return None
    payload = _normalise(match.group(1)).strip("。！!. ")
    if not payload or len(payload) > _MAX_MEMORY_CHARACTERS:
        return None
    normalized_payload = payload.lower()
    if any(marker in normalized_payload for marker in _DISALLOWED_MARKERS):
        return None
    return payload


def _classify(content: str) -> MemoryKind:
    """按关键词把记忆分为约束/偏好/档案三类；约束关键词优先于偏好。"""
    if any(marker in content for marker in _CONSTRAINT_MARKERS):
        return MemoryKind.CONSTRAINT
    if any(marker in content for marker in _PREFERENCE_MARKERS):
        return MemoryKind.PREFERENCE
    return MemoryKind.PROFILE


def _record_id(scope: MemoryScope, kind: MemoryKind, content: str) -> str:
    """用 sha256 生成确定性 id：同一用户保存同一内容必得同一 id，实现幂等覆盖。"""
    # \0（NUL）作分隔符，避免字段拼接产生歧义（如 "ab"+"c" 与 "a"+"bc" 碰撞）。
    value = f"{scope.tenant_id}\0{scope.user_id}\0{kind.value}\0{content}".encode("utf-8")
    return f"memory-{sha256(value).hexdigest()[:24]}"


def _normalise(content: str) -> str:
    """压缩连续空白，保证正则匹配与 id 生成不受换行、多余空格影响。"""
    return re.sub(r"\s+", " ", content).strip()
