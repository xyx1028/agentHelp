---
kind: external_dependency
name: OpenAI 模型服务
slug: openai-api
category: external_dependency
category_hints:
    - auth_protocol
scope:
    - '**'
---

### 角色
作为可选的真实模型后端，通过 langchain-openai 接入 OpenAI Chat Completions。默认走 mock 模式，设置 MODEL_API_KEY 后启用真实模型。

### 集成方式
- 通过 python-dotenv 加载 .env 中的 MODEL_API_KEY。
- 配置项由 AgentSettings 管理，模型选择依据动态工具目录和对话上下文决定是否需要调用外部工具。