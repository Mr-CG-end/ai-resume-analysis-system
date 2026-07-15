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

Compose 将宿主机 `127.0.0.1:16379` 映射到容器内 Redis 的标准端口 6379；启用缓存时在 `backend/.env` 配置 `REDIS_URL=redis://127.0.0.1:16379/0`。

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

复制后的 `.env` 默认将 `AI_API_KEY`、`AI_BASE_URL` 和 `AI_MODEL` 留空，使用真实模型前需在本地填写这三项（不得提交）。后端仅在三项均为非空值时将 AI 健康状态报告为可用；单次模型调用默认超时 20 秒，可通过 `AI_TIMEOUT_SECONDS` 调整为大于 0 且不超过 60 秒。模型接口采用 OpenAI 兼容的 `/chat/completions` 协议，响应解压后最多接收 1 MiB。仅在启用缓存时配置 `REDIS_URL`；缓存 TTL 默认 86,400 秒，可通过 `CACHE_TTL_SECONDS` 调整。Redis 连接、读取、坏数据或写入失败都会旁路为缓存未命中，不阻断业务。`CORS_ORIGINS` 使用逗号分隔的精确来源，默认仅允许 `http://localhost:5173`，拒绝空值和 `*`。前端 `.env.local` 只配置公开的 `VITE_API_BASE_URL`，不得包含任何密钥。

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
pytest --cov=app --cov-report=term-missing
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

## 第三方许可

生产 PDF 解析依赖 pypdf 6.14.2，测试 fixture 生成器使用开发依赖 ReportLab 5.0.0；二者均按 BSD-3-Clause 许可使用。ReportLab 不进入生产锁或后端镜像。归属与许可来源见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)、[pypdf LICENSE](https://github.com/py-pdf/pypdf/blob/6.14.2/LICENSE) 和 [ReportLab 官方许可说明](https://docs.reportlab.com/developerfaqs/#licensing)。

这些文件提供可重复的构建和部署流程，不表示当前版本已经发布到线上。项目进度见 [`docs/00-project-checklist.md`](docs/00-project-checklist.md)，完整需求、架构、测试和部署约束见 [`docs/`](docs/)。项目完整功能完成后，最终由用户按 [`docs/07-local-manual-acceptance.md`](docs/07-local-manual-acceptance.md) 在本地执行人工验收并确认结果；阶段 7 自动化联调不能替代最终人工验收。
