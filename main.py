"""旅行 Agent 的应用启动入口；核心实现位于 travel_agent 包。

三种运行模式：
- 真实模式：读取 .env 中的模型配置，走完整的「模型 + 工具 + 记忆」链路；
- --mock：使用离线预置的模型与工具替身，无需 API Key 或网络即可体验流程；
- --evaluate：运行离线工具回归评测套件，全部通过返回退出码 0，否则为 1。
"""

import argparse
import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from travel_agent.agent import TravelAssistantAgent
from travel_agent.config import AgentSettings
from travel_agent.evaluation import create_mock_model, create_mock_tool_registry, run_evaluation
from travel_agent.memory import AgentMemory, MemoryScope
from travel_agent.tools import build_default_tool_registry


def create_real_model():
    """创建未绑定的真实模型；TravelAssistantAgent 会以 ToolRegistry 统一绑定工具。

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


def main():
    """启动流程：加载配置 → 解析参数 → 组装工具/模型/记忆 → 逐问题执行问答。"""
    load_dotenv()  # 从 .env 读取模型配置（该文件不进版本库）
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="*", default=["帮我安排杭州一天的旅行路线"])
    parser.add_argument("--mock", action="store_true", help="使用离线预置工具调用，无需 API Key 或网络")
    parser.add_argument("--mock-scenario", choices=["happy", "weather", "timeout", "error", "no-tool"], default="happy")
    parser.add_argument("--evaluate", action="store_true", help="运行 10 个离线工具评测样例")
    parser.add_argument("--tenant-id", default="local", help="记忆租户标识；当前仅用于进程内隔离")
    parser.add_argument("--user-id", default="default", help="记忆用户标识；当前仅用于进程内隔离")
    parser.add_argument("--conversation-id", default="default", help="短期会话标识；当前仅用于进程内隔离")
    args = parser.parse_args()

    # 评测模式是独立的短路流程：跑完回归套件直接按通过与否退出。
    if args.evaluate:
        raise SystemExit(0 if run_evaluation() else 1)

    settings = AgentSettings()
    # mock 与真实模式共用同一个 Agent，仅替换工具注册表与模型两个注入点。
    tool_registry = (
        create_mock_tool_registry(args.mock_scenario, settings)
        if args.mock
        else build_default_tool_registry(settings)
    )
    try:
        model = create_mock_model(args.mock_scenario) if args.mock else create_real_model()
    except ValueError as error:
        parser.error(str(error))

    # 记忆作用域决定短期历史与长期偏好的隔离边界；CLI 各标识默认仅进程内隔离。
    memory_scope = MemoryScope(
        tenant_id=args.tenant_id,
        user_id=args.user_id,
        conversation_id=args.conversation_id,
    )
    agent = TravelAssistantAgent(
        model,
        settings=settings,
        tool_registry=tool_registry,
        memory=AgentMemory.in_memory(settings.memory),
        memory_scope=memory_scope,
    )
    # 依次提问：同一 Agent 实例内的多个问题共享短期会话窗口与长期记忆。
    for question in args.question:
        print(f"\n用户：{question}")
        turn = agent.ask(question)
        print(f"助手：{turn.answer}")
        print(f"[Memory] 本轮结束后保存 {len(agent.history)} 条短期消息。")


if __name__ == "__main__":
    main()
