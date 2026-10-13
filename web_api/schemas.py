"""API 的请求/响应模型；由 Pydantic 统一校验入参，路由函数不再手写判空。"""

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    """会话元数据，供前端侧栏列表展示。"""

    id: str
    title: str


class CreateConversationIn(BaseModel):
    """新建会话请求；标题可缺省，由服务端给默认名。"""

    title: str | None = Field(default=None, max_length=50)


class MessageOut(BaseModel):
    """一条可展示的消息；工具调用等中间产物不下发给前端。"""

    role: str  # "user" 或 "assistant"
    content: str


class SendMessageIn(BaseModel):
    """发送消息请求；content 必须非空，避免空转模型白花钱。"""

    content: str = Field(min_length=1, max_length=4000)


class SendMessageOut(BaseModel):
    """一轮问答结果；memory_context 供前端展开查看本轮召回的长期记忆。"""

    answer: str
    memory_context: str
