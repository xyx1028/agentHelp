---
kind: error_handling
name: Agent 编排平台的错误处理策略
category: error_handling
scope:
    - '**'
source_files:
    - agent_platform/agent.py
    - agent_platform/tools/executor.py
    - main.py
    - agent_platform/memory/models.py
    - agent_platform/rag.py
    - agent_platform/evaluation/fakes.py
---

## 1. 总体方法

本仓库没有自定义异常类型、错误码或统一的 error 包。错误处理以 Python 内置 `ValueError` / `FileNotFoundError` / `TimeoutError` / `Exception` 为主，按「调用方职责」分层：

- **参数/配置校验** → 直接 `raise ValueError(...)`（构造期即失败）。
- **外部依赖故障**（模型调用、工具执行）→ 捕获后降级为文本消息，不向上传播，保证 LangGraph 图继续运行。
- **进程入口** → 通过 `argparse.parser.error()` 和 `SystemExit` 暴露给 CLI。

## 2. 关键文件与位置

| 文件 | 角色 |
|---|---|
| `agent_platform/agent.py` | Agent 层对模型调用的 try/except 降级 |
| `agent_platform/tools/executor.py` | 工具执行器的超时与异常兜底 |
| `main.py` | CLI 启动时的配置缺失处理 |
| `agent_platform/memory/models.py` | 记忆相关参数的 `ValueError` 校验 |
| `agent_platform/rag.py` | RAG 配置与知识库路径的 `ValueError` / `FileNotFoundError` |
| `agent_platform/tools/executor.py` | 工具未注册、超时的白名单与降级 |
| `agent_platform/evaluation/fakes.py` | mock 场景下的 `ValueError` 断言 |

## 3. 架构与约定

### 3.1 参数校验集中在构造函数
所有需要约束的参数在 `__init__` 中立即检查，失败时抛出带中文说明的 `ValueError`：

- `AssistantAgent.__init__`：共享 memory 必须显式提供 `memory_scope`，防止跨用户泄露（第 48–49 行）。
- `ReadOnlyToolExecutor.__init__`：默认工具超时必须 > 0（第 21–22 行）。
- `MemoryScope` / `LongTermMemoryConfig` / `ShortTermMemoryConfig`：tenant_id、user_id、conversation_id、limit、max_characters 等字段校验（`memory/models.py`）。
- `RagSettings`：chunk_size ≥ 80、top_k ≥ 1（`rag.py`）。

这些是**构造期不变量**，一旦违反，对象无法被创建。

### 3.2 运行时错误降级而非传播
两个关键节点把下游异常吞掉并转为「可观测文本」：

- **模型调用**（`agent.py:_assistant_node`，第 132–137 行）：捕获 `Exception`，返回一条 `AIMessage(content=f"模型调用失败：{type(error).__name__}：{error}")`，让 LangGraph 正常结束而不是整张图崩溃。
- **工具执行**（`tools/executor.py:execute_tool_calls` + `_call_safely`）：
  - 未注册工具：白名单拒绝，返回 `"工具错误：不允许调用 {name}；当前只允许已注册的只读工具。"`
  - 超时：`ThreadPoolExecutor` + `future.result(timeout=...)` 捕获 `TimeoutError`，cancel 工作线程后返回 `"工具超时：...超过 N 秒，已停止等待。请说明暂时无法查询。"`
  - 其他异常：捕获 `Exception`，返回 `"工具错误：{name} 返回 {type(error).__name__}：{error}。请说明查询失败，不要编造结果。"`

注释明确表达了设计意图：「工具未注册、超时、抛异常都不向上抛出，而是变成文本 observation 交还给模型，由模型向用户说明——保证 LangGraph 图不会因单个工具的故障整体崩溃。」

### 3.3 进程入口的错误暴露
`main.py` 中：
- `create_real_model()` 缺少 `MODEL_API_KEY` 时 `raise ValueError(...)`。
- `main()` 用 `try/except ValueError` 捕获后调用 `parser.error(str(error))`，让 argparse 输出用法信息并以非零退出。
- 评测模式通过 `run_evaluation()` 返回值决定 `SystemExit(0|1)`。

### 3.4 无全局错误类型
仓库中没有 `class XxxError(Exception)` 形式的自定义异常，也没有错误码枚举。所有业务语义通过 `ValueError` 的 message 表达（如 "tenant_id 和 user_id 都不能为空"、"知识库没有可检索内容"、"模拟知识库不可用"）。测试侧通过匹配 message 字符串来断言（见 `evaluation/cases.py` 中的 `assert str(e) == ...`），因此 message 文案属于契约的一部分。

## 4. 观察到的约定与约束

- **构造期参数校验使用 `ValueError`**：所有 `memory/models.py`、`rag.py`、`tools/executor.py`、`agent.py` 中的参数约束都走此路径，message 使用中文描述。
- **LangGraph 图内异常不得上抛**：模型调用与工具执行两处均用 `try/except Exception` 降级为文本消息，这是保证图稳定性的硬性约定（代码注释与实现双重体现）。
- **工具调用一律只读且带超时**：`ReadOnlyToolExecutor` 强制每个工具调用在独立线程中限时执行，超时后 cancel 并返回固定格式的 observation。
- **CLI 配置缺失通过 argparse 报告**：`main.py` 将 `ValueError` 转交给 `parser.error()`，而不是直接 `sys.exit(1)`。
- **评测模式以退出码区分成功/失败**：`SystemExit(0 if run_evaluation() else 1)`。
- **没有 panic/recover 等价物**：Python 无 panic，仓库也未使用 `try/finally` 做资源清理以外的 recover 逻辑（仅 `executor._call_safely` 的 `finally: executor.shutdown(...)` 用于线程池释放）。
- **没有统一日志框架**：错误与状态通过 `print` 输出（如 `[Memory]`、`[LangGraph]`、`[Tool]` 前缀），不属于结构化日志系统。