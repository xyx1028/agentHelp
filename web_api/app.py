"""FastAPI 应用装配：注入 Agent 与会话注册表、挂路由、托管前端构建产物。

create_app 是唯一装配点：依赖（AssistantAgent、ConversationRegistry）
由入口 web.py 构造后传入，应用本身不关心模型是真实还是 mock。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from agent_platform.agent import AssistantAgent

from .routes.chat import build_chat_router
from .sessions import ConversationRegistry

# Vite 开发服务器来源；仅开发期跨域需要，生产单进程托管时同源、此配置无害。
_DEV_SERVER_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


class SPAStaticFiles(StaticFiles):
    """静态托管并对未知路径回退 index.html，保证前端路由（如 /c/<id>）刷新后仍可访问。"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            # 只有 404 才回退到 SPA 入口；其他错误照常抛出，避免掩盖真实问题。
            if error.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def create_app(
    agent: AssistantAgent,
    registry: ConversationRegistry,
    *,
    tenant_id: str,
    user_id: str,
    static_dir: Path | None = None,
) -> FastAPI:
    """装配完整应用；static_dir 指向 npm run build 产物时才托管前端页面。"""
    app = FastAPI(title="Agent Platform Web API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_DEV_SERVER_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(build_chat_router(agent, registry, tenant_id=tenant_id, user_id=user_id))
    if static_dir is not None and static_dir.is_dir():
        # 挂在根路径且放在路由注册之后，让 /api 路由优先匹配。
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="web-ui")
    return app
