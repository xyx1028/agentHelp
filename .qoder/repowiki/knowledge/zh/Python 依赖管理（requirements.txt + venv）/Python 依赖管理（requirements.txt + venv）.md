---
kind: dependency_management
name: Python 依赖管理（requirements.txt + venv）
category: dependency_management
scope:
    - '**'
source_files:
    - requirements.txt
    - .venv/
    - README.md
---

## 1. 使用的系统/方案

本项目采用最基础的 Python 依赖管理方式：
- 使用 `pip` 作为包安装器。
- 通过根目录的 `requirements.txt` 声明第三方依赖。
- 使用 `.venv/` 虚拟环境隔离运行依赖，未启用任何锁定文件（无 `requirements.lock`、`poetry.lock`、`Pipfile.lock`）。
- 未发现私有 PyPI 源、`pip.conf`/`pip.ini`、`PYPI_URL` 等私有仓库配置。

## 2. 关键文件

- `requirements.txt`：唯一依赖清单，仅声明 4 个顶层库。
- `.venv/`：由 `python -m venv` 生成的虚拟环境目录（当前为空或尚未初始化）。
- `README.md`：在“快速开始”部分给出 `python -m pip install -r requirements.txt` 的安装命令，是官方推荐的安装入口。

## 3. 架构与约定

- 依赖版本约束采用“宽松主版本区间”写法：`langchain>=1.0,<2.0`、`langgraph>=1.0,<2.0`、`langchain-openai>=1.0,<2.0`、`python-dotenv>=1.0,<2.0`。即允许任意次补丁/小版本升级，但锁定在主版本 1.x 内，避免跨大版本的破坏性更新。
- 没有子项目或多模块结构，所有依赖集中在单一 `requirements.txt`，不存在按模块拆分依赖清单的模式。
- 没有 vendoring（如 `vendor/`、`third_party/`）策略；所有第三方代码均通过 pip 从 PyPI 拉取。
- 没有 CI 中的依赖缓存或锁定步骤（仓库中未见 `.github/workflows/` 等 CI 配置）。

## 4. 约定与约束

- **依赖声明位置**：所有第三方依赖统一写在根级 `requirements.txt`，未见其他 `requirements*.txt` 或 `setup.py`/`pyproject.toml` 形式的声明。（来源：仓库扫描未发现其他依赖清单）
- **版本范围**：已声明的依赖均采用 `>=X.0,<Y.0` 的主版本区间约束，确保兼容同一主版本下的最新补丁和小版本。（来源：`requirements.txt` 内容）
- **安装方式**：官方文档指定通过 `python -m pip install -r requirements.txt` 安装依赖。（来源：`README.md` 第 117 行）
- **无锁定文件**：仓库未提交任何 lockfile，因此不同时间 `pip install` 可能解析到不同的具体版本，存在可重现性问题。（事实观察）
- **无私有源/认证**：未发现 `pip.conf`、`PYPI_URL`、`.netrc` 或环境变量中的私有仓库配置，默认使用公共 PyPI。（事实观察）