# 智能简历分析系统

本仓库包含 FastAPI 后端、React/Vite 前端及配套工程规范。前后端在本机直接运行；Docker Compose 仅提供可选的 Redis 7 缓存。

## 环境要求

- Python 3.12.13
- Node.js 22 与 pnpm 10
- Docker Desktop（仅在需要 Redis 缓存时使用）

## 本地开发

Redis 是可选依赖。需要验证缓存时，在仓库根目录执行：

```bash
docker compose up -d redis
docker compose ps
```

后端在本机运行：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端在另一个终端运行：

```powershell
cd frontend
pnpm install --frozen-lockfile
Copy-Item .env.example .env.local
pnpm dev
```

当前后端骨架的健康检查只读取 `AI_API_KEY`，仅在启用缓存时配置 `REDIS_URL`。CORS 白名单以及 `AI_BASE_URL`、`AI_MODEL` 等模型供应商配置将在下一项 API 集成任务中实现；当前版本尚未实现这些能力。前端 `.env.local` 只配置公开的 `VITE_API_BASE_URL`，不得包含任何密钥。

## 验证

激活后端虚拟环境后，在仓库根目录执行以下命令；它们同时适用于 PowerShell 和 POSIX shell：

```bash
python -m pytest tests/test_infrastructure.py -v
python scripts/validate_infrastructure.py
docker compose config
```

后端质量检查：

```bash
cd backend
ruff format --check .
ruff check .
mypy app
pytest
```

前端质量检查：

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test --run
pnpm build
```

## 部署分工

- 后端：`backend/Dockerfile` 构建固定的 Python 3.12.13 slim-bookworm 镜像，使用带哈希的 `backend/requirements.lock` 安装生产依赖，服务监听 `0.0.0.0:9000`，供阿里云 Function Compute 自定义容器部署。镜像发布和 FC 配置由部署人员执行。
- 前端：`.github/workflows/pages.yml` 从 `frontend/` 构建并上传 Pages artifact，仓库子路径由 `VITE_BASE_PATH` 注入，公开 API 地址由仓库变量 `VITE_API_BASE_URL` 注入。
- CI：`.github/workflows/ci.yml` 在 push 和 pull request 上检查后端 pytest/Ruff/mypy 以及前端 lint/typecheck/test/build。

这些文件提供可重复的构建和部署流程，不表示当前版本已经发布到线上。项目进度见 [`docs/00-project-checklist.md`](docs/00-project-checklist.md)，完整需求、架构、测试和部署约束见 [`docs/`](docs/)。
