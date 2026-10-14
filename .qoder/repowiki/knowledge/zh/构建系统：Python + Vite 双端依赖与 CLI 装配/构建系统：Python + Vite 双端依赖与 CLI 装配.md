---
kind: build_system
name: 构建系统：Python + Vite 双端依赖与 CLI 装配
category: build_system
scope:
    - '**'
---

## 1. 使用的系统与工具

仓库采用**双端独立依赖管理**，没有统一的顶层构建脚本（Makefile / build.sh / Dockerfile / CI 配置均不存在）：

- **Python 后端**：通过 `requirements.txt` 声明运行时依赖，由 Python 虚拟环境（`.venv/`）安装；入口为 `main.py`，使用 `argparse` 提供 `chat` / `evaluate` / `serve` 三个子命令。
- **前端 Web UI**：位于 `web_ui/`，基于 Vite + React + TypeScript，依赖通过 `package.json` 管理，构建产物输出到 `web_ui/dist/`。

## 2. 关键文件

- `requirements.txt`：后端依赖清单，固定 major 版本区间（如 `langchain>=1.0,<2.0`、`fastapi>=0.115,<1.0`、`uvicorn>=0.30,<1.0`），并引入 `python-dotenv` 加载 `.env`。
- `main.py`：唯一进程入口，负责解析 CLI、装配 Agent、启动 FastAPI 服务；同时作为 chat/evaluate/serve 三模式的调度器。
- `web_ui/package.json`：定义 `dev` / `build` / `preview` 三个 npm script，其中 `build` 先执行 `tsc` 再 `vite build`。
- `web_ui/vite.config.ts`：Vite 构建配置（未读取，但存在）。
- `web_ui/tsconfig.json`：TypeScript 编译配置。
- `.env.example`：环境变量模板（`.env` 被 `.gitignore` 排除）。

## 3. 架构与约定

- **无统一构建编排**：仓库根目录没有 Makefile、Dockerfile、CI YAML、release 脚本或版本发布流程。前后端各自维护自己的依赖与构建。
- **可选前端集成**：`main.py` 中 `_WEB_UI_DIST = Path(__file__).resolve().parent / "web_ui" / "dist"` 指向前端构建产物；当 `web_ui/dist` 存在时，FastAPI 会一并托管 SPA 静态资源，否则仅提供 `/api` REST 接口。注释明确说明“未执行 npm run build 时 serve 仅提供 /api，不托管页面”。
- **延迟导入以解耦依赖**：`run_server` 内部才 `import uvicorn` 和 `web_api.app`，使得 `chat` / `evaluate` 子命令不需要安装 fastapi/uvicorn 也能运行。
- **评测模式独立短路**：`evaluate` 子命令直接调用 `run_evaluation()`，按全部通过返回退出码 0、否则返回 1，适合作为离线回归测试入口。
- **模型配置来自 .env**：`create_real_model` 从 `MODEL_API_KEY` / `MODEL_NAME` / `MODEL_BASE_URL` 等环境变量读取 OpenAI 兼容模型的连接信息，缺省 `MODEL_API_KEY` 时抛出 `ValueError` 提示用户配置或使用 `--mock`。

## 4. 约定与约束

- **依赖版本约束**：`requirements.txt` 对每个包使用 `>=X,<Y` 的 major 版本区间（例如 `langchain>=1.0,<2.0`、`fastapi>=0.115,<1.0`），避免上游大版本升级破坏兼容性。
- **前端构建产物必须预先生成**：`serve` 模式下若 `web_ui/dist` 不存在，则只暴露 API 而不提供前端页面——这是代码逻辑强制的行为，而非建议。
- **环境变量隔离**：`.env` 被 `.gitignore` 忽略，`.env.example` 仅作为模板；真实模型凭据不得提交到版本库。
- **无容器化与 CI**：仓库未发现 Dockerfile、docker-compose、GitHub Actions / GitLab CI 等自动化构建与部署配置。
- **无统一打包分发**：没有 `setup.py` / `pyproject.toml` / `pyinstaller` / `poetry` 等打包脚本，项目以源码 + `.venv` 方式直接运行。
- **npm 构建顺序**：`web_ui/package.json` 的 `build` 脚本固定为先 `tsc` 再 `vite build`，TypeScript 类型检查是构建的前置步骤。