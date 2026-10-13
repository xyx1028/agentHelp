"""通用 Agent 平台的唯一进程入口；核心实现位于 agent_platform 包。

子命令：
- chat：命令行问答，真实模式读取 .env 模型配置，--mock 用离线替身体验；
- evaluate：运行离线工具回归评测套件，全部通过返回退出码 0，否则为 1；
- serve：启动 FastAPI Web 服务，提供多会话聊天界面（web_ui 构建产物存在时一并托管）。
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from agent_platform.agent import AssistantAgent
from agent_platform.config import AgentSettings
from agent_platform.evaluation import create_mock_model, create_mock_tool_registry, run_evaluation
from agent_platform.memory import AgentMemory, MemoryScope
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


def build_agent(args: argparse.Namespace) -> AssistantAgent:
    """按启动参数装配模型、工具注册表与记忆，供 chat 与 serve 子命令复用。

    mock 与真实模式共用同一个 Agent，仅替换工具注册表与模型两个注入点。
    返回的 Agent 持有共享 AgentMemory：调用方可在 ask() 时传入不同
    MemoryScope 实现多会话短期隔离、同用户长期记忆共享（serve 即如此）。
    """
    settings = AgentSettings()
    tool_registry = (
        create_mock_tool_registry(args.mock_scenario, settings)
        if args.mock
        else build_default_tool_registry(settings)
    )
    model = create_mock_model(args.mock_scenario) if args.mock else create_real_model()
    # 记忆作用域决定短期历史与长期偏好的隔离边界；缺省标识仅进程内隔离。
    memory_scope = MemoryScope(
        tenant_id=args.tenant_id,
        user_id=args.user_id,
        conversation_id=args.conversation_id,
    )
    return AssistantAgent(
        model,
        settings=settings,
        tool_registry=tool_registry,
        memory=AgentMemory.in_memory(settings.memory),
        memory_scope=memory_scope,
    )


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


def run_server(args: argparse.Namespace, agent: AssistantAgent) -> None:
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
    )
    uvicorn.run(app, host=args.host, port=args.port)


def main() -> None:
    """启动流程：加载配置 → 解析子命令 → 分发到问答/评测/Web 服务。"""
    load_dotenv()  # 从 .env 读取模型配置（该文件不进版本库）
    parser = build_parser()
    args = parser.parse_args()

    # 评测是独立的短路流程：跑完回归套件直接按通过与否退出。
    if args.command == "evaluate":
        raise SystemExit(0 if run_evaluation() else 1)

    if args.command == "serve":
        # build_agent 要求 conversation_id 占位；Web 端每个会话在 ask 时各自覆盖 scope。
        args.conversation_id = "web-placeholder"
    try:
        agent = build_agent(args)
    except ValueError as error:
        parser.error(str(error))

    if args.command == "serve":
        run_server(args, agent)
    else:
        run_chat(args, agent)


if __name__ == "__main__":
    main()
