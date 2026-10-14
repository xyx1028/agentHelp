"""Agent 编排：模型、工具注册表、记忆门面和会话状态。

一轮问答的核心链路（见 AssistantAgent.ask）：
按作用域加锁 → 加载短期历史 + 召回长期记忆 → LangGraph「assistant ⇄ tools」
循环 → 写回短期窗口并提取长期记忆。模型、工具、记忆均经构造函数注入，可独立替换。
"""

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from .config import AgentSettings
from .memory import AgentMemory, MemoryScope
from .rag import build_knowledge_base
from .tools import ReadOnlyToolExecutor, ToolRegistry, build_default_tool_registry


class AgentState(MessagesState):
    """图内状态；长期记忆 context 是临时输入，不会写入会话消息。"""

    memory_context: str


@dataclass(frozen=True)
class AgentTurn:
    """一轮 Agent 调用的可观测结果，评测和后续接口都可复用。"""

    answer: str
    messages: list[Any]
    memory_context: str = ""


class AssistantAgent:
    """通用助手平台的应用层 Agent；工具、短期记忆和长期记忆都通过可替换边界注入。"""

    def __init__(
        self,
        model: Any,
        settings: AgentSettings | None = None,
        *,
        tool_registry: ToolRegistry | None = None,
        memory: AgentMemory | None = None,
        memory_scope: MemoryScope | None = None,
    ):
        # 共享记忆必须显式指定作用域：缺省时每个 Agent 各建各的，从根上防止跨用户串数据。
        if memory is not None and memory_scope is None:
            raise ValueError("注入共享 memory 时必须显式提供 memory_scope，避免跨用户或跨会话泄露。")

        self.settings = settings or AgentSettings()
        # 工具注册表是模型绑定、Prompt 工具目录和执行器超时三方的唯一事实来源。
        if tool_registry is not None:
            self.tool_registry = tool_registry
        else:
            # 未注入注册表时按子系统 Settings 现场装配默认组合：
            # 知识库由 rag.factory 装配，工具组合根只负责持有它。
            self.tool_registry = build_default_tool_registry(
                self.settings.tools,
                knowledge_base=build_knowledge_base(self.settings.rag),
            )

        # 绑定工具 Schema 后，模型才能在回复中发起结构化工具调用。
        self._model = self.tool_registry.bind_model(model)
        self.memory = memory or AgentMemory.in_memory(self.settings.memory)
        self.memory_scope = memory_scope or MemoryScope.local()
        # 系统 Prompt 启动时按当前工具目录渲染一次，之后随实例复用。
        self._system_prompt = self.settings.build_system_prompt(self.tool_registry.prompt_catalog())
        self._tool_executor = ReadOnlyToolExecutor(self.tool_registry, self.settings.tools.default_timeout_seconds)
        self._graph = self._build_graph()

    @property
    def history(self) -> list[Any]:
        """返回当前作用域的短期会话历史，不包含合成的长期记忆 context。"""
        return self.memory.load_conversation(self.memory_scope)

    def reset_conversation(self) -> None:
        """清空当前会话的短期上下文，保留同一用户的长期偏好。"""
        self.memory.reset_conversation(self.memory_scope)

    def clear_long_term_memory(self) -> None:
        """显式删除当前用户跨会话的长期记忆。"""
        self.memory.clear_long_term_memory(self.memory_scope)

    def clear_all_memory(self) -> None:
        """同时删除当前会话短期历史和当前用户长期记忆。"""
        self.memory.clear_all_memory(self.memory_scope)

    def ask(self, question: str, *, memory_scope: MemoryScope | None = None) -> AgentTurn:
        """执行一轮问答，并串行更新当前会话的短期窗口和长期偏好存储。

        流程：turn() 加锁串行化 → 读短期历史、按问题召回长期记忆 → 驱动
        LangGraph 循环直到模型不再调用工具 → 写回记忆 → 取最终答复返回。
        """
        scope = memory_scope or self.memory_scope
        with self.memory.turn(scope):
            # 1. 短期历史延续上下文；长期记忆按当前问题召回，以不可信数据身份注入。
            history = self.memory.load_conversation(scope)
            memory_context = self.memory.recall_context(scope, question)
            # 2. 跑图：assistant 与 tools 节点可能往返多轮，直到模型直接回答。
            input_messages = history + [HumanMessage(content=question)]
            result = self._graph.invoke({"messages": input_messages, "memory_context": memory_context})
            messages = list(result["messages"])
            # 3. 写回：全量消息覆盖短期窗口，本轮新增消息交给 writer 提取长期记忆。
            new_messages = messages[len(history):]
            self.memory.record_turn(scope, messages, new_messages)
            # 4. 最终答复 = 最后一条不带工具调用的 AI 消息。
            answer = next(
                item.content
                for item in reversed(messages)
                if item.type == "ai" and not item.tool_calls
            )
        return AgentTurn(answer=answer, messages=messages, memory_context=memory_context)

    def _build_graph(self):
        """编译 LangGraph 状态图：assistant →（有工具调用则 tools→assistant，否则结束）。"""
        builder = StateGraph(AgentState)
        builder.add_node("assistant", self._assistant_node)
        builder.add_node("tools", self._tools_node)
        builder.add_edge(START, "assistant")
        builder.add_conditional_edges("assistant", tools_condition, {"tools": "tools", END: END})
        builder.add_edge("tools", "assistant")
        return builder.compile()

    def _assistant_node(self, state: AgentState):
        """调用模型产出下一步：可能直接回答，也可能携带一轮工具调用。"""
        # 送入模型前按窗口策略裁剪以控制 token 成本；完整消息仍保留在图状态里。
        context = self.memory.trim_for_model(state["messages"])
        if len(context) != len(state["messages"]):
            print(f"[Memory] 历史 {len(state['messages'])} 条，裁剪后向模型传入 {len(context)} 条。")
        prompt_messages = [SystemMessage(content=self._system_prompt)]
        memory_context = state.get("memory_context", "")
        if memory_context:
            # 记忆保持为低权限用户数据，绝不提升为 SystemMessage。
            prompt_messages.append(HumanMessage(content=memory_context))
        print("[LangGraph] 正在执行 assistant 节点")
        try:
            response = self._model.invoke(prompt_messages + context)
        except Exception as error:
            # 模型故障降级为一条普通答复，让图正常收尾而不是整体崩溃。
            response = AIMessage(content=f"模型调用失败：{type(error).__name__}：{error}")
        return {"messages": [response]}

    def _tools_node(self, state: AgentState):
        """执行上一条 AI 消息携带的全部工具调用，把 observation 写回消息流。"""
        return {"messages": self._tool_executor.execute_tool_calls(state["messages"][-1].tool_calls)}
