---
kind: configuration_system
name: AgentSettings + .env + CLI 参数三层配置体系
category: configuration_system
scope:
    - '**'
source_files:
    - agent_platform/config.py
    - agent_platform/memory/models.py
    - main.py
    - .env.example
---

## 1. 采用的方式

仓库采用「Python dataclass 不可变设置对象 + python-dotenv 环境变量 + argparse CLI 参数」的三层组合：
- 运行时可调参数集中在 `agent_platform/config.py` 中的 `AgentSettings`（以及 `memory/models.py` 中的 `MemorySettings`）两个 frozen dataclass；
- 外部凭据与模型地址通过 `.env` 文件注入，由 `main.py` 调用 `dotenv.load_dotenv()` 加载；
- 运行模式、租户/用户/会话隔离标识通过 `argparse` 命令行参数传入。

没有使用 YAML/TOML/JSON 配置文件，也没有引入 Pydantic Settings、Dynaconf 等第三方配置框架。

## 2. 关键文件

- `agent_platform/config.py` — `AgentSettings` 定义，集中所有 Agent 级运行时参数（system_prompt、tool_timeout、rag_top_k/chunk_size、memory 子设置），并提供 `build_system_prompt(tool_catalog)` 方法。
- `agent_platform/memory/models.py` — `MemorySettings`、`MemoryScope`、`MemoryOwner` 等不可变数据类，承载记忆子系统参数与作用域边界。
- `main.py` — 应用启动入口，负责 `load_dotenv()`、解析 CLI、根据 `--mock` / `--evaluate` 分支装配模型、工具注册表、记忆作用域并构造 `AssistantAgent`。
- `.env.example` — 模板文件，声明 `MODEL_API_KEY`、`MODEL_NAME`、`MODEL_BASE_URL` 三个环境变量。

## 3. 架构与设计约定

### 3.1 不可变设置对象 + Fail Fast 校验
`AgentSettings` 和 `MemorySettings` 均使用 `@dataclass(frozen=True)`，并在 `__post_init__` 中做范围校验（如 `max_history_messages < 1`、`long_term_context_max_characters < 80`）。这保证了非法配置在构造阶段即抛出 `ValueError`，而非在运行时静默出错。

### 3.2 新旧字段双向同步
`AgentSettings` 保留了旧字段 `max_history_messages`，但实际窗口值统一保存在 `memory.short_term_max_messages`。`__post_init__` 中若未显式传 `memory`，则按旧字段构造 `MemorySettings`；若传了自定义 `MemorySettings`，则将 `max_history_messages` 反向同步为 `memory.short_term_max_messages`，保证两条配置路径结果一致。

### 3.3 系统 Prompt 动态拼装
`AgentSettings.build_system_prompt(tool_catalog)` 将当前已注册工具的目录注入到 system prompt 末尾，新增工具时无需手动维护 prompt 文本。

### 3.4 环境变量命名约定
模型相关变量以 `MODEL_` 前缀组织：
- `MODEL_API_KEY`：必填，缺失时在 `create_real_model()` 中抛 `ValueError("请在 .env 中配置 MODEL_API_KEY...")`；
- `MODEL_NAME`：默认 `gpt-4.1-mini`；
- `MODEL_BASE_URL`：默认 `https://api.openai.com/v1`。

这些变量通过 `os.getenv` 读取，不经过 pydantic 验证。

### 3.5 CLI 参数作为运行期开关
`main.py` 暴露以下参数：
- `question`（位置参数，默认 `["杭州有什么可玩的？"]`）；
- `--mock`：切换离线 mock 模式；
- `--mock-scenario`：choices 为 `happy|weather|timeout|error|no-tool`，默认 `happy`；
- `--evaluate`：独立短路流程，直接执行评测套件并以退出码 0/1 返回；
- `--tenant-id` / `--user-id` / `--conversation-id`：记忆隔离标识，默认分别为 `local` / `default` / `default`。

### 3.6 记忆作用域作为配置
`MemoryScope(tenant_id, user_id, conversation_id)` 本身是一个不可变配置对象，由 CLI 参数构造，用于决定短期消息窗口与长期记忆的隔离边界。其 `__post_init__` 要求三个字段非空。

## 4. 约定与约束

- **Fail Fast**：所有 settings dataclass 在 `__post_init__` 中对数值下限做校验，非法值立即抛 `ValueError`（见 `AgentSettings`、`MemorySettings`、`MemoryOwner`、`MemoryScope`、`MemoryRecord`、`MemoryQuery` 的 `__post_init__`）。
- **.env 不进版本库**：`.env.example` 是模板，注释明确“不要提交 .env”；`main.py` 注释也写明“该文件不进版本库”。
- **真实模式依赖 API Key**：若未设置 `MODEL_API_KEY` 且未使用 `--mock` / `--evaluate`，启动时会抛错并被 `parser.error` 捕获。
- **温度固定为 0**：`create_real_model()` 硬编码 `temperature=0`，使工具路由可复现。
- **超时分层**：`AgentSettings.tool_timeout_seconds`（默认 0.3s）作用于工具执行器层，`network_tool_timeout_seconds`（默认 7.0s）覆盖网络类工具，`weather_request_timeout_seconds`（默认 6.0s）是 HTTP 请求级超时，三者语义不同。
- **RAG 参数集中管理**：`rag_top_k`（默认 3）与 `rag_chunk_size`（默认 260，注释说明下限 80）集中在 `AgentSettings`，供 RAG 模块消费。
- **CLI 仅控制运行模式，settings 控制行为**：`--mock` / `--evaluate` 切换装配分支，而具体的超时、窗口、检索条数等通过 `AgentSettings` 注入，二者解耦。

## 5. 适用性判断

本仓库虽无传统配置文件（YAML/TOML），但存在明确的运行时配置抽象（`AgentSettings` / `MemorySettings`）、环境变量契约（`.env.example` + `MODEL_*` 前缀）与 CLI 参数体系，构成一套完整的轻量级配置系统，因此本类别适用。