# LangChain + LangGraph 最小 Agent Demo

这是在原来单轮 `START → chatbot → END` 之上扩展的可运行版本：

```text
START → assistant ──（模型有 tool_calls）──→ tools（只读）→ assistant → END
                  └────（没有 tool_calls）────────────────────────→ END
```

它只实现四件面试时可讲清楚、可实际验证的事：

1. **只读工具**：`travel_guide(city)` 只读取内置示例旅行资料；真实模型通过 `bind_tools()` 自己决定是否调用。工具节点白名单拒绝未知工具。
2. **多轮记忆 + 裁剪**：同一次进程中保存对话历史，但最多把最近 6 条、且从用户消息开始的历史带回模型，避免上下文无限增长或留下孤立工具结果。
3. **失败处理**：工具超时、工具报错、模型调用异常都会变成一条可见 observation/回复，图不会直接崩溃；模型可据此说明失败而不是编造答案。
4. **小型评测**：`--evaluate` 跑 10 个离线案例，记录预期工具、实际工具和最终回答证据。

> `--mock` 的预置 `AIMessage(tool_calls=...)` 是为离线稳定验证“模型请求工具 → 程序执行 → observation 回给模型”的链路；它不证明真实模型已联网或会做出同样选择。

## 安装

需要 Python 3.10+。如果系统默认 `python3` 是 3.9，请使用已经安装的 `python3.11`、`python3.12` 等创建虚拟环境。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 先离线跑通

```bash
python main.py --mock
```

预期会看到：`assistant` 请求 `travel_guide`、工具返回带“证据”的 observation、第二次 `assistant` 给出最终回复。

下面三条分别验证普通路径、超时和工具错误：

```bash
python main.py --mock --mock-scenario happy
python main.py --mock --mock-scenario timeout
python main.py --mock --mock-scenario error
```

多传几个问题即可在一个进程内看到历史被裁剪：

```bash
python main.py --mock "第一问" "第二问" "第三问" "第四问"
```

`--mock` 首轮固定走两步“工具调用 + 最终回复”；后续提问会重复固定最终回复。它的用途是观察状态流动与裁剪，不是根据问题生成真实旅行答案。

## 运行 10 个评测样例

```bash
python main.py --evaluate
```

每一项输出都会含有：预期工具、实际调用工具、最终回复证据和汇总通过数。它检查的是离线链路与日志字段，不替代真实模型的质量评测。

## 调用真实模型

```bash
cp .env.example .env
```

在 `.env` 填写 `MODEL_API_KEY`；默认 OpenAI。如使用 DeepSeek，同时按示例改 `MODEL_NAME` 与 `MODEL_BASE_URL`：

```bash
python main.py "帮我安排杭州一天的旅行路线" "再推荐一个雨天方案"
```

真实调用时，`bind_tools(READ_ONLY_TOOLS)` 会把工具 Schema 发给模型。模型没有发起 `tool_calls` 就直接结束；若发起了 `travel_guide`，则经历 `assistant → tools → assistant`。真实 API 尚需你配置 Key 后实际请求，离线 mock 不能替代该验证。

## 可继续扩展的代码结构

`main.py` 是应用启动入口；核心类命名为 `TravelAssistantAgent`，后面继续搭建时优先在 `travel_agent/` 中扩展：

```text
travel_agent/
├── agent.py       # TravelAssistantAgent：图编排、会话与 ask()
├── config.py      # AgentSettings：Prompt、历史长度、工具超时
├── tools.py       # 工具定义、白名单与 ReadOnlyToolExecutor
├── memory.py      # 历史裁剪策略
├── mocks.py       # 离线模型替身
└── evaluation.py  # 10 条离线评测集
```

后续新增一个工具时，把工具定义放进 `tools.py`，再注册到 `READ_ONLY_TOOLS`；新增数据库记忆、checkpointer 或接口层时，不需要把逻辑重新塞回启动入口。

官方文档：[LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)、[LangChain 工具调用](https://docs.langchain.com/oss/python/langchain/tools)。
