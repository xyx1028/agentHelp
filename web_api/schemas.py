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


class KnowledgeStatsOut(BaseModel):
    """知识库管理入口状态；manageable=False（mock/词法后端）时前端禁用上传与重建。"""

    manageable: bool  # 仅向量后端可管理
    chunk_count: int  # 当前索引片段总数；不可管理时为 0


class IngestDocumentsOut(BaseModel):
    """一次上传灌入的结果；errors 收集单文件失败明细，部分成功也算成功。"""

    ingested_files: list[str]  # 成功灌入的原始文件名
    added_chunks: int  # 本次新增的索引片段数
    chunk_count: int  # 灌入后的索引片段总数
    errors: dict[str, str] = {}  # 文件名 → 失败原因


class ReindexOut(BaseModel):
    """索引重建结果：全量重建后的片段总数。"""

    chunk_count: int
