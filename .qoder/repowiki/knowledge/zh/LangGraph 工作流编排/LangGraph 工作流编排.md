---
kind: external_dependency
name: LangGraph 工作流编排
slug: langgraph
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

### 角色
用于构建 Agent 的有向图编排，其中 tools 节点是 LangGraph 对所有 tool_calls 的统一执行位置；RAG、天气或记忆并非强制流程，而是由 Agent 根据上下文决定是否调用工具。

### 集成方式
- AssistantAgent 使用 LangGraph 定义图结构，ToolRegistry 作为 bind_tools 与执行白名单的唯一来源。
- 依赖版本约束在 requirements.txt：langgraph>=1.0,<2.0。