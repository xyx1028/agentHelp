---
kind: external_dependency
name: LangChain 框架
slug: langchain
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

### 角色
作为 Agent 平台的核心运行时，提供 LLM 抽象、工具绑定（bind_tools）和 LangGraph 编排。Agent 通过 ToolRegistry 统一注册工具，避免 Schema 与执行器漂移。

### 集成方式
- 工具适配层（tools/rag.py、tools/weather.py）以 LangChain Tool 形态注册到 ToolRegistry。
- 依赖版本约束在 requirements.txt：langchain>=1.0,<2.0。

### 稳定约束
- 新增工具只需在 tools/ 下新建适配层并在 tools/factory.py 注册，docstring 自动进入模型可见目录，无需修改 AgentSettings.system_prompt。