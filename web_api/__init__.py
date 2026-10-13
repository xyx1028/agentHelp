"""Web API 子系统：把 AssistantAgent 暴露为多会话 JSON 接口。

FastAPI 应用由 app.create_app 装配，路由按资源域拆在 routes/ 下；
前端每个会话对应一个 MemoryScope(conversation_id)，短期窗口按会话隔离、
长期记忆按同一 tenant+user 跨会话共享（记忆子系统的既有边界，无改动）。
"""
