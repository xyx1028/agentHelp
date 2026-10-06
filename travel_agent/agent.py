"""Agent 编排：模型、工具节点和会话状态。"""

from dataclasses import dataclass
from typing import Any, Iterable

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from .config import AgentSettings
from .memory import trim_messages
from .tools import READ_ONLY_TOOLS, ReadOnlyToolExecutor


@dataclass(frozen=True)
class AgentTurn:
    """一轮 Agent 调用的可观测结果，评测和后续接口都可复用。"""

    answer: str
    messages: list[Any]


class TravelAssistantAgent:
    """旅行助手的应用层 Agent；后续替换工具、记忆或模型时以此为装配入口。"""

    def __init__(
        self,
        model: Any,
        tools: Iterable[BaseTool] = READ_ONLY_TOOLS,
        settings: AgentSettings | None = None,
    ):
        self._model = model
        self.settings = settings or AgentSettings()
        self._history: list[Any] = []
        self._tool_executor = ReadOnlyToolExecutor(tools, self.settings.tool_timeout_seconds)
        self._graph = self._build_graph()

    @property
    def history(self) -> list[Any]:
        """返回当前进程内的裁剪后会话历史。"""
        return list(self._history)

    def reset_conversation(self) -> None:
        """清空当前会话；未来接数据库或 checkpointer 时可替换这里。"""
        self._history = []

    def ask(self, question: str) -> AgentTurn:
        """执行一轮问答，并在内存中保存长度受限的会话历史。"""
        input_messages = trim_messages(self._history, self.settings.max_history_messages) + [("user", question)]
        result = self._graph.invoke({"messages": input_messages})
        messages = result["messages"]
        self._history = trim_messages(messages, self.settings.max_history_messages)
        answer = next(
            item.content
            for item in reversed(messages)
            if item.type == "ai" and not item.tool_calls
        )
        return AgentTurn(answer=answer, messages=messages)

    def _build_graph(self):
        builder = StateGraph(MessagesState)
        builder.add_node("assistant", self._assistant_node)
        builder.add_node("tools", self._tools_node)
        builder.add_edge(START, "assistant")
        builder.add_conditional_edges("assistant", tools_condition, {"tools": "tools", END: END})
        builder.add_edge("tools", "assistant")
        return builder.compile()

    def _assistant_node(self, state: MessagesState):
        context = trim_messages(state["messages"], self.settings.max_history_messages)
        if len(context) != len(state["messages"]):
            print(f"[Memory] 历史 {len(state['messages'])} 条，裁剪后向模型传入 {len(context)} 条。")
        print("[LangGraph] 正在执行 assistant 节点")
        try:
            response = self._model.invoke([SystemMessage(content=self.settings.system_prompt)] + context)
        except Exception as error:
            response = AIMessage(content=f"模型调用失败：{type(error).__name__}：{error}")
        return {"messages": [response]}

    def _tools_node(self, state: MessagesState):
        return {"messages": self._tool_executor.execute_tool_calls(state["messages"][-1].tool_calls)}
