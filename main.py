"""旅行 Agent 的应用启动入口；核心实现位于 travel_agent 包。"""

import argparse
import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from travel_agent.agent import TravelAssistantAgent
from travel_agent.evaluation import run_evaluation
from travel_agent.mocks import create_mock_model
from travel_agent.tools import READ_ONLY_TOOLS


def create_real_model():
    """创建绑定只读工具的真实模型；凭据仍从 .env 读取。"""
    api_key = os.getenv("MODEL_API_KEY")
    if not api_key:
        raise ValueError("请在 .env 中配置 MODEL_API_KEY，或使用 --mock / --evaluate 体验流程。")
    raw_model = init_chat_model(
        os.getenv("MODEL_NAME", "gpt-4.1-mini"),
        model_provider="openai",
        api_key=api_key,
        base_url=os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1"),
        temperature=0,
        timeout=30,
        max_retries=1,
    )
    return raw_model.bind_tools(READ_ONLY_TOOLS)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="*", default=["帮我安排杭州一天的旅行路线"])
    parser.add_argument("--mock", action="store_true", help="使用离线预置工具调用，无需 API Key 或网络")
    parser.add_argument("--mock-scenario", choices=["happy", "timeout", "error", "no-tool"], default="happy")
    parser.add_argument("--evaluate", action="store_true", help="运行 10 个离线评测样例")
    args = parser.parse_args()

    if args.evaluate:
        raise SystemExit(0 if run_evaluation() else 1)

    try:
        model = create_mock_model(args.mock_scenario) if args.mock else create_real_model()
    except ValueError as error:
        parser.error(str(error))

    agent = TravelAssistantAgent(model)
    for question in args.question:
        print(f"\n用户：{question}")
        turn = agent.ask(question)
        print(f"助手：{turn.answer}")
        print(f"[Memory] 本轮结束后保存 {len(agent.history)} 条消息。")


if __name__ == "__main__":
    main()
