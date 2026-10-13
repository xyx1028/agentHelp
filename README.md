# LangChain + LangGraph 通用 Agent 平台

项目已将工具、记忆和评测拆为独立模块。当前的 RAG、天气、短期记忆和进程内长期记忆都是可替换实现；Agent 只依赖它们的稳定边界。

```text
                 ToolRegistry
           ┌─────────┼─────────┐
           ↓         ↓         ↓
      bind_tools   Prompt   Tool Executor

Agent ──→ AgentMemory ──→ ShortTermMemory（会话窗口）
                  └────→ LongTermMemory（用户偏好/约束）

EvaluationRunner ──→ 可注入 CaseExecutor ──→ Agent / 模型 / 后端 fixture
```

Agent 根据上下文决定是否调用工具。`tools` 节点只是 LangGraph 对所有 `tool_calls` 的统一执行位置，并不代表 RAG、天气或记忆是强制流程。

## 目录结构

```text
agent_platform/
├── agent.py                    # LangGraph 编排、模型绑定与记忆组合
├── config.py                   # 通用 Agent / Memory 配置
├── rag.py                      # RAG 领域实现：加载、分块、检索
├── weather.py                  # 天气领域客户端：地理编码、预报请求
├── tools/
│   ├── registry.py             # ToolRegistration / ToolRegistry
│   ├── factory.py              # 默认工具唯一注册位置
│   ├── executor.py             # 白名单、超时和错误处理
│   ├── rag.py                  # RAG Tool 适配层
│   └── weather.py              # 天气 Tool 适配层
├── memory/
│   ├── models.py               # Scope、Record、Query、Settings
│   ├── contracts.py            # 短期/长期存储和 Writer 契约
│   ├── short_term.py           # 消息窗口和进程内短期实现
│   ├── long_term.py            # 进程内长期记忆实现
│   ├── writer.py               # 显式授权的偏好/约束提取策略
│   └── service.py              # AgentMemory 组合门面
└── evaluation/
    ├── models.py               # Case、Execution、Result、Report、Suite
    ├── cases.py                # 固定离线回归案例
    ├── fakes.py                # 无网络模型和工具替身
    ├── executors.py            # 默认离线 CaseExecutor
    └── runner.py               # 通用评测运行器和控制台报告器
web_api/
├── app.py                      # FastAPI 装配、CORS、SPA 静态托管
├── schemas.py                  # Pydantic 请求/响应模型
├── sessions.py                 # 进程内会话注册表
└── routes/chat.py              # 会话 CRUD 与消息收发
web_ui/                         # React 18 + TypeScript + Vite 前端
├── src/api.ts                  # HTTP 调用唯一封装
├── src/views/ChatView.tsx      # 聊天主视图（会话列表 + 消息流）
└── src/components/ConversationList.tsx
knowledge/
└── knowledge_base.md
```

## 工具架构

工具通过 `ToolRegistry` 注册。它是模型 `bind_tools()`、系统 Prompt 工具目录、执行白名单和工具超时策略的唯一来源；`AssistantAgent` 会用同一注册表绑定模型，避免 Schema 与执行器漂移。

当前工具：

| 工具 | 职责 | 适配层 |
| --- | --- | --- |
| `search_knowledge` | 本地 RAG，返回带 `[source:...]` 的知识资料 | `tools/rag.py` |
| `get_weather_forecast` | 查询未来 1–7 天天气、温度和降水概率 | `tools/weather.py` |

新增工具只需在 `tools/` 新建适配层并在 `tools/factory.py` 注册；工具 docstring 会自动进入模型可见目录，无需修改 `AgentSettings.system_prompt`。

兼容期内，旧的 `READ_ONLY_TOOLS` 仍可导入但会发出弃用警告；请改用 `build_default_tool_registry(settings).tools`。

天气查询运行时使用 Open-Meteo 的地理编码和预报接口，不需要 API Key。实现依据 [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api) 和 [Forecast API](https://open-meteo.com/en/docs)。

## 记忆架构

### 短期记忆

`ShortTermMemory` 按 `MemoryScope(tenant_id, user_id, conversation_id)` 隔离消息窗口。默认 `InMemoryShortTermMemory` 只在当前进程存在，窗口从合法的人类/系统消息边界开始，避免留下孤立工具结果。

`AgentMemory.turn(scope)` 串行化同一会话的完整“读历史 → 运行 Agent → 写历史”过程，避免并发请求互相覆盖；不同 scope 可以并发执行。

### 长期记忆

`LongTermMemory` 按 `MemoryOwner(tenant_id, user_id)` 隔离，因此同一用户的偏好可跨不同 `conversation_id` 召回。默认 `InMemoryLongTermMemory` 是完整可运行的开发 adapter：支持 upsert、检索、隔离和清理，但**进程重启后会丢失**。

默认 `ExplicitPreferenceWriter` 仅保存以“请记住”或“帮我记住”明确授权的、长度受限的用户偏好/约束；它不会保存模型回答、工具 observation、天气结果、系统消息或普通提问。长期记忆以序列化的**低权限用户数据**注入模型，不会提升为 SystemMessage，也不能充当事实资料或实时信息的依据。

```python
from agent_platform import AgentSettings
from agent_platform.memory import AgentMemory, MemoryScope

settings = AgentSettings()
shared_memory = AgentMemory.in_memory(settings.memory)
first_scope = MemoryScope(user_id="u-1", conversation_id="c-1")
second_scope = MemoryScope(user_id="u-1", conversation_id="c-2")

# 两个 Agent 共享 shared_memory 时，长期偏好可跨会话使用；短期消息仍隔离。
# 注入共享 memory 时必须显式传入 memory_scope，避免默认作用域泄露。
```

`reset_conversation()` 仅清短期消息；`clear_long_term_memory()` 清当前用户长期记忆；`clear_all_memory()` 两者都清。

未来接 SQLite、Redis 或向量库时，只需实现 `LongTermMemory` 契约并注入 `AgentMemory`，无需修改 Agent、ToolRegistry 或图结构。

## 评测架构

`EvaluationSuite`、`EvaluationCase`、`EvaluationExecution`、`EvaluationResult` 和 `EvaluationReport` 将案例定义、实际执行、断言和报告分离。`EvaluationRunner` 接收可注入的 `CaseExecutor`：默认 `OfflineToolCaseExecutor` 使用 fakes；未来的记忆、真实模型、不同后端 benchmark 可实现自己的执行器，而不必改 runner。

当前 `DEFAULT_OFFLINE_TOOL_SUITE` 保留原有 10 条离线工具回归场景，覆盖：RAG 命中/未命中、天气、超时、错误和无需工具。

```bash
python main.py evaluate
```

该命令保持返回码语义，并输出结构化结果的控制台视图。评测套件的公共 API 统一从 `agent_platform.evaluation` 包导入：`OFFLINE_TOOL_CASES`、`run_evaluation()` 以及 suite、executor、fakes。

## 安装与运行

需要 Python 3.10+：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Python 侧新增 fastapi / uvicorn 两个 Web 依赖（已在 requirements.txt 中）；仅当需要构建前端界面时，额外要求 Node.js 18+。

离线运行：

```bash
python main.py chat --mock
python main.py chat --mock --mock-scenario weather "杭州明天天气怎么样？"
python main.py evaluate
```

记忆作用域可从 CLI 显式指定（当前为进程内隔离）：

```bash
python main.py chat --mock --user-id u-1 --conversation-id c-1 "请记住我喜欢慢节奏行程"
```

真实模型：

```bash
cp .env.example .env
python main.py chat "杭州西湖适合怎样安排？"
python main.py chat "杭州明天天气怎么样？"
```

配置 `MODEL_API_KEY` 后，模型会根据动态工具目录和对话上下文选择是否调用工具。

## Web 界面

多会话聊天界面，演示短期记忆按会话隔离、长期记忆按用户跨会话共享：

```bash
# 前端：首次或前端改动后构建；开发调试时也可 npm run dev（Vite 代理 /api 到 8000）
cd web_ui && npm install && npm run build && cd ..

# 后端：真实模型需配置 .env；离线体验加 --mock
python main.py serve --mock
```

打开 http://127.0.0.1:8000：左侧新建/切换/删除会话，每个会话对应独立的
`conversation_id`（短期历史互不可见）；在任意会话里说「请记住…」，
其他会话提问时即可召回同一条长期记忆。接口文档见 http://127.0.0.1:8000/docs。