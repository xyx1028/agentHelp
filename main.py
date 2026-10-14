"""通用 Agent 平台的唯一进程入口；核心实现位于 agent_platform 包。

子命令：
- chat：命令行问答，真实模式读取 .env 模型配置，--mock 用离线替身体验；
- evaluate：运行离线工具回归评测套件，全部通过返回退出码 0，否则为 1；
- serve：启动 FastAPI Web 服务，提供多会话聊天界面（web_ui 构建产物存在时一并托管）；
- ingest / reindex：向量知识库的文档灌入与索引重建，完成后退出。
"""

import argparse
from dataclasses import replace
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from agent_platform.agent import AssistantAgent
from agent_platform.config import AgentSettings
from agent_platform.evaluation import create_mock_model, create_mock_tool_registry, run_evaluation
from agent_platform.memory import AgentMemory, MemoryScope
from agent_platform.rag import KnowledgeBase, LlamaIndexKnowledgeBase, RagSettings, build_knowledge_base
from agent_platform.tools import build_default_tool_registry

# 前端构建产物目录；未执行 npm run build 时 serve 仅提供 /api，不托管页面。
_WEB_UI_DIST = Path(__file__).resolve().parent / "web_ui" / "dist"


def create_real_model():
    """创建未绑定的真实模型；AssistantAgent 会以 ToolRegistry 统一绑定工具。

    模型名、API Key、Base URL 均取自 .env；temperature=0 让工具路由可复现，
    timeout/max_retries 限制模型故障时的等待时间。工具不在此处绑定，
    而由 Agent 统一从 ToolRegistry 注入，保证与 Prompt 工具目录一致。
    """
    api_key = os.getenv("MODEL_API_KEY")
    if not api_key:
        raise ValueError("请在 .env 中配置 MODEL_API_KEY，或使用 --mock / --evaluate 体验流程。")
    return init_chat_model(
        os.getenv("MODEL_NAME", "gpt-4.1-mini"),
        model_provider="openai",
        api_key=api_key,
        base_url=os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1"),
        temperature=0,
        timeout=30,
        max_retries=1,
    )


def _load_settings() -> AgentSettings:
    """构造运行配置：.env 中的 RAG_* 变量覆盖 RagSettings 默认值。

    仅覆盖非机密项；embedding 的 key 与端点在装配知识库时单独读取注入，
    避免机密进入可打印的配置对象。
    """
    overrides = {}
    for env_key, field_name in (
        ("RAG_BACKEND", "backend"),
        ("RAG_EMBEDDING_PROVIDER", "embedding_provider"),
        ("RAG_EMBEDDING_MODEL", "embedding_model"),
    ):
        value = os.getenv(env_key)
        if value:
            overrides[field_name] = value
    # 先构造子系统配置再组合：RagSettings 的 Fail Fast 校验在 replace 时即生效。
    rag_settings = replace(RagSettings(), **overrides) if overrides else RagSettings()
    return AgentSettings(rag=rag_settings)


def build_agent(args: argparse.Namespace) -> tuple[AssistantAgent, KnowledgeBase | None]:
    """按启动参数装配模型、工具注册表与记忆，供 chat 与 serve 子命令复用。

    mock 与真实模式共用同一个 Agent，仅替换工具注册表与模型两个注入点。
    返回的 Agent 持有共享 AgentMemory：调用方可在 ask() 时传入不同
    MemoryScope 实现多会话短期隔离、同用户长期记忆共享（serve 即如此）。
    同时返回知识库后端供 Web 管理路由使用；mock 模式的知识库封装在替身
    注册表内部，无管理意义，返回 None。
    """
    settings = _load_settings()
    # mock 与真实模式共用同一个 Agent，仅替换工具注册表与模型两个注入点。
    if args.mock:
        tool_registry = create_mock_tool_registry(args.mock_scenario, settings)
        knowledge_base = None
    else:
        # 真实模式按 RAG_BACKEND 装配检索后端；embedding 机密仅在此处从 .env 读取注入。
        knowledge_base = build_knowledge_base(
            settings.rag,
            embedding_api_key=os.getenv("EMBEDDING_API_KEY"),
            embedding_base_url=os.getenv("EMBEDDING_BASE_URL"),
        )
        tool_registry = build_default_tool_registry(settings.tools, knowledge_base=knowledge_base)
    model = create_mock_model(args.mock_scenario) if args.mock else create_real_model()
    # 记忆作用域决定短期历史与长期偏好的隔离边界；缺省标识仅进程内隔离。
    memory_scope = MemoryScope(
        tenant_id=args.tenant_id,
        user_id=args.user_id,
        conversation_id=args.conversation_id,
    )
    agent = AssistantAgent(
        model,
        settings=settings,
        tool_registry=tool_registry,
        memory=AgentMemory.in_memory(settings.memory),
        memory_scope=memory_scope,
    )
    return agent, knowledge_base


def build_parser() -> argparse.ArgumentParser:
    """构造子命令解析器；mock 与记忆标识等参数为 chat/serve 所共用，集中在一处注册。"""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_args(p: argparse.ArgumentParser) -> None:
        """注册 chat/serve 共用的装配参数；evaluate 自成离线体系，不需要这些。"""
        p.add_argument("--mock", action="store_true", help="使用离线预置工具调用，无需 API Key 或网络")
        p.add_argument("--mock-scenario", choices=["happy", "weather", "timeout", "error", "no-tool"], default="happy")
        p.add_argument("--tenant-id", default="local", help="记忆租户标识；长期记忆按 tenant+user 归属")
        p.add_argument("--user-id", default="default", help="记忆用户标识；serve 下同一用户的各会话共享长期记忆")

    chat = subparsers.add_parser("chat", help="命令行问答")
    chat.add_argument("question", nargs="*", default=["杭州有什么可玩的？"])  # 默认问题命中内置演示知识库，便于开箱验证 RAG 链路
    chat.add_argument("--conversation-id", default="default", help="短期会话标识；仅用于进程内隔离")
    add_common_args(chat)

    subparsers.add_parser("evaluate", help="运行 10 个离线工具评测样例")

    ingest = subparsers.add_parser("ingest", help="把指定文档（MD/TXT/PDF/DOCX）灌入向量知识库后退出")
    ingest.add_argument("files", nargs="+", metavar="FILE", help="待灌入的文档路径")

    subparsers.add_parser("reindex", help="清空并重建向量索引后退出")

    serve = subparsers.add_parser("serve", help="启动 Web 服务（多会话聊天界面）")
    serve.add_argument("--host", default="127.0.0.1", help="监听地址")
    serve.add_argument("--port", type=int, default=8000, help="监听端口；Vite 代理默认指向 8000")
    add_common_args(serve)
    return parser


def run_chat(args: argparse.Namespace, agent: AssistantAgent) -> None:
    """CLI 问答：同一 Agent 实例内的多个问题共享短期会话窗口与长期记忆。"""
    for question in args.question:
        print(f"\n用户：{question}")
        turn = agent.ask(question)
        print(f"助手：{turn.answer}")
        print(f"[Memory] 本轮结束后保存 {len(agent.history)} 条短期消息。")


def run_server(args: argparse.Namespace, agent: AssistantAgent, knowledge_base: KnowledgeBase | None) -> None:
    """启动 Web 服务；Web 依赖延迟导入，让 chat/evaluate 不需要 fastapi/uvicorn。"""
    import uvicorn

    from web_api.app import create_app
    from web_api.sessions import ConversationRegistry

    app = create_app(
        agent,
        ConversationRegistry(),
        tenant_id=args.tenant_id,
        user_id=args.user_id,
        static_dir=_WEB_UI_DIST,
        knowledge_base=knowledge_base,
    )
    uvicorn.run(app, host=args.host, port=args.port)


def main() -> None:
    """启动流程：加载配置 → 解析子命令 →（评测/索引维护短路）→ 装配 Agent → 分发执行。"""
    load_dotenv()  # 从 .env 读取模型配置（该文件不进版本库）
    parser = build_parser()
    args = parser.parse_args()

    # 评测是独立的短路流程：跑完回归套件直接按通过与否退出。
    if args.command == "evaluate":
        raise SystemExit(0 if run_evaluation() else 1)

    # 索引维护同样是短路流程：灌入/重建后打印索引规模并退出，不进入问答。
    if args.command in ("ingest", "reindex"):
        knowledge_base = build_knowledge_base(
            _load_settings().rag,
            embedding_api_key=os.getenv("EMBEDDING_API_KEY"),
            embedding_base_url=os.getenv("EMBEDDING_BASE_URL"),
            force_rebuild=args.command == "reindex",
        )
        if not isinstance(knowledge_base, LlamaIndexKnowledgeBase):
            parser.error("ingest/reindex 需要向量后端（RAG_BACKEND=vector）。")
        added = knowledge_base.ingest([Path(item) for item in args.files]) if args.command == "ingest" else 0
        print(f"知识库索引片段总数：{knowledge_base.chunk_count}（本次新增 {added}）。")
        return

    if args.command == "serve":
        # build_agent 要求 conversation_id 占位；Web 端每个会话在 ask 时各自覆盖 scope。
        args.conversation_id = "web-placeholder"
    try:
        agent, knowledge_base = build_agent(args)
    except ValueError as error:
        parser.error(str(error))

    if args.command == "serve":
        run_server(args, agent, knowledge_base)
    else:
        run_chat(args, agent)


if __name__ == "__main__":
    main()
