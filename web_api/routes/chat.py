"""会话与消息路由：前端多会话界面的唯一数据入口。

所有请求共享同一个 AssistantAgent；每个会话映射为一个
MemoryScope(conversation_id=...)，因此短期窗口按会话隔离，
长期记忆按同一 tenant+user 跨会话召回。
"""

from fastapi import APIRouter, HTTPException
from langchain_core.messages import BaseMessage

from agent_platform.agent import AssistantAgent
from agent_platform.memory import MemoryScope

from ..schemas import (
    ConversationOut,
    CreateConversationIn,
    MessageOut,
    SendMessageIn,
    SendMessageOut,
)
from ..sessions import ConversationRegistry


def build_chat_router(
    agent: AssistantAgent,
    registry: ConversationRegistry,
    *,
    tenant_id: str,
    user_id: str,
) -> APIRouter:
    """构造会话/消息路由；依赖经闭包注入，避免全局单例，测试时可整体换替身。"""

    router = APIRouter(prefix="/api/conversations", tags=["conversations"])

    def scope_of(conversation_id: str) -> MemoryScope:
        """由会话 id 推导记忆作用域；tenant/user 固定，保证同一用户长期记忆共享。"""
        return MemoryScope(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)

    def require_conversation(conversation_id: str) -> None:
        """会话必须先在注册表登记，防止客户端凭空向任意 scope 写入历史。"""
        if registry.get(conversation_id) is None:
            raise HTTPException(status_code=404, detail="会话不存在或已删除")

    @router.get("")
    def list_conversations() -> list[ConversationOut]:
        """返回全部会话元数据，供侧栏列表展示。"""
        return [ConversationOut(id=item.id, title=item.title) for item in registry.list()]

    @router.post("", status_code=201)
    def create_conversation(payload: CreateConversationIn) -> ConversationOut:
        """登记一个新会话；短期历史在首次问答时由记忆子系统惰性创建。"""
        item = registry.create(payload.title)
        return ConversationOut(id=item.id, title=item.title)

    @router.delete("/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str) -> None:
        """删除会话并清掉它的短期窗口；长期记忆归属用户，不随会话删除。"""
        require_conversation(conversation_id)
        registry.remove(conversation_id)
        agent.memory.reset_conversation(scope_of(conversation_id))

    @router.get("/{conversation_id}/messages")
    def list_messages(conversation_id: str) -> list[MessageOut]:
        """返回该会话的可展示历史；工具调用中间产物不下发给前端。"""
        require_conversation(conversation_id)
        history = agent.memory.load_conversation(scope_of(conversation_id))
        return _serialize_history(history)

    @router.post("/{conversation_id}/messages")
    def send_message(conversation_id: str, payload: SendMessageIn) -> SendMessageOut:
        """执行一轮问答；同步 def 路由由 FastAPI 放进线程池，不会阻塞事件循环。"""
        require_conversation(conversation_id)
        registry.rename_if_default(conversation_id, payload.content)
        turn = agent.ask(payload.content, memory_scope=scope_of(conversation_id))
        return SendMessageOut(answer=turn.answer, memory_context=turn.memory_context)

    return router


def _serialize_history(messages: list[BaseMessage]) -> list[MessageOut]:
    """只保留用户消息与最终答复；带 tool_calls 的 AI 中间消息和 ToolMessage 属内部过程。"""
    items: list[MessageOut] = []
    for message in messages:
        if message.type == "human":
            items.append(MessageOut(role="user", content=message.content))
        elif message.type == "ai" and not message.tool_calls:
            items.append(MessageOut(role="assistant", content=message.content))
    return items
