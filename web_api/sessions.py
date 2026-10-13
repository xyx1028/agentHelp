"""进程内会话注册表：会话 id → 元数据（标题）。

与短期/长期记忆一致采用进程内存储，进程重启即失；将来要持久化时
只需把本模块换成数据库实现，路由层接口不变。
"""

from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

DEFAULT_TITLE = "新会话"  # 新建会话的默认名；首轮提问后自动改用问题前缀
_AUTO_TITLE_LENGTH = 16  # 自动命名时取问题前多少个字符
_CONVERSATION_ID_LENGTH = 8  # 会话 id 取 uuid4 前缀长度，短号便于 URL 展示


@dataclass
class ConversationMeta:
    """会话元数据；当前只有标题，预留扩展（创建时间、置顶等）。"""

    id: str
    title: str = DEFAULT_TITLE


class ConversationRegistry:
    """线程安全的会话登记表；与 AgentMemory 的 scope 锁配合支撑并发请求。"""

    def __init__(self) -> None:
        self._items: dict[str, ConversationMeta] = {}
        self._lock = RLock()

    def create(self, title: str | None = None) -> ConversationMeta:
        """登记新会话并返回元数据；空标题回落为默认名。"""
        meta = ConversationMeta(
            id=uuid4().hex[:_CONVERSATION_ID_LENGTH],
            title=(title or "").strip() or DEFAULT_TITLE,
        )
        with self._lock:
            self._items[meta.id] = meta
        return meta

    def list(self) -> list[ConversationMeta]:
        """返回全部会话（按登记先后）。"""
        with self._lock:
            return list(self._items.values())

    def get(self, conversation_id: str) -> ConversationMeta | None:
        """按 id 查会话；不存在返回 None，由路由层翻译成 404。"""
        with self._lock:
            return self._items.get(conversation_id)

    def rename_if_default(self, conversation_id: str, question: str) -> None:
        """会话仍叫默认名时，取首条问题的前若干字命名，省一次手工改名。"""
        with self._lock:
            meta = self._items.get(conversation_id)
            if meta is not None and meta.title == DEFAULT_TITLE:
                meta.title = question[:_AUTO_TITLE_LENGTH]

    def remove(self, conversation_id: str) -> bool:
        """移除登记；返回是否确实存在过（幂等，重复删不报错）。"""
        with self._lock:
            return self._items.pop(conversation_id, None) is not None
