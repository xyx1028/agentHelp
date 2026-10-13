"""可替换的短期与长期记忆公共 API。

包内分层（单向依赖）：models 数据模型 → contracts 接口契约 →
short_term / long_term / writer 进程内实现 → service 组合门面 AgentMemory。
外部只需从本模块导入；__all__ 白名单之外的名字属内部细节，可能随时调整。
"""

from .contracts import LongTermMemory, LongTermMemoryWriter, ShortTermMemory
from .long_term import InMemoryLongTermMemory
from .models import (
    MemoryKind,
    MemoryOwner,
    MemoryQuery,
    MemoryRecord,
    MemoryScope,
    MemorySettings,
    RetrievedMemory,
)
from .service import AgentMemory
from .short_term import InMemoryShortTermMemory, MessageWindowPolicy
from .writer import ExplicitPreferenceWriter, NoopLongTermMemoryWriter

__all__ = [
    "AgentMemory",
    "ExplicitPreferenceWriter",
    "InMemoryLongTermMemory",
    "InMemoryShortTermMemory",
    "LongTermMemory",
    "LongTermMemoryWriter",
    "MemoryKind",
    "MemoryOwner",
    "MemoryQuery",
    "MemoryRecord",
    "MemoryScope",
    "MemorySettings",
    "MessageWindowPolicy",
    "NoopLongTermMemoryWriter",
    "RetrievedMemory",
    "ShortTermMemory",
]
