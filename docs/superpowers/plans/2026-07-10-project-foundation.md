# Project Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a tested FastAPI backend, a tested React/Vite frontend, and the local/CI/deployment foundation needed before resume-analysis features are added.

**Architecture:** Keep a monorepo with independent `backend/` and `frontend/` applications. The backend exposes versioned REST endpoints and runs directly in development; the frontend calls a configurable API base URL. Redis is optional and runs through Docker Compose. CI validates both applications, while a separate Pages workflow publishes the frontend.

**Tech Stack:** Python 3.12.13, FastAPI, Pydantic v2, pytest, Ruff, mypy; Node 22, React, TypeScript, Vite, Vitest, Testing Library, ESLint; Redis 7; GitHub Actions.

## Global Constraints

- Keep the public API prefix exactly `/api/v1`.
- `GET /api/v1/health` returns `status`, `version`, and dependency states without making a paid AI request.
- Redis is optional; its absence must report `disabled` or `down` without making the service unavailable.
- Local frontend and backend run directly on the host; Docker Compose starts Redis only.
- Use an English Conventional Commits prefix followed by a Chinese subject.
- Never commit credentials, real resumes, generated build output, or PII-bearing logs.
- Production backend images target `linux/amd64` and listen on `0.0.0.0:9000`.

---

### Task 1: FastAPI Backend Foundation

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/routes/__init__.py`
- Create: `backend/app/api/routes/health.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/health.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/.env.example`

**Interfaces:**
- Produces: `create_app() -> FastAPI` in `app.main` and module-level `app`.
- Produces: `GET /api/v1/health` with HTTP 200 and JSON `{status, version, dependencies: {ai, redis}}`.
- Configuration: `APP_VERSION`, `AI_API_KEY`, and optional `REDIS_URL` from environment.

- [ ] **Step 1: Write the failing health endpoint test**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_configured_dependencies(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.delenv("REDIS_URL", raising=False)
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "dependencies": {"ai": "configured", "redis": "disabled"},
    }
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `cd backend && python -m pytest tests/test_health.py -v`

Expected: collection/import failure because `app.main` does not exist.

- [ ] **Step 3: Implement the minimal typed application**

Create Pydantic response models, environment-backed settings, the health router, and `create_app()`. Settings must be loaded per request or through an explicitly clearable cache so tests can change environment values safely.

- [ ] **Step 4: Verify GREEN and quality checks**

Run: `cd backend && python -m pytest tests/test_health.py -v && ruff check . && mypy app`

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(api): 搭建后端健康检查骨架"
```

### Task 2: React Frontend Foundation

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/pnpm-lock.yaml`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/eslint.config.js`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/App.css`
- Create: `frontend/src/index.css`
- Create: `frontend/src/vite-env.d.ts`
- Create: `frontend/src/App.test.tsx`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/.env.example`

**Interfaces:**
- Reads public `VITE_API_BASE_URL` only; no credentials are allowed in frontend variables.
- Shows the product title, the three-step flow, and a disabled placeholder action that clearly says implementation continues with PDF upload.
- Vite `base` comes from `VITE_BASE_PATH`, defaulting to `/`.

- [ ] **Step 1: Scaffold the React TypeScript project and write a failing test**

The test must expect the heading `智能简历分析系统`, the flow labels `上传简历`, `提取信息`, `岗位匹配`, and an accessible primary action.

- [ ] **Step 2: Run the test and confirm RED**

Run: `cd frontend && pnpm test --run`

Expected: failure because the product-specific UI is not implemented.

- [ ] **Step 3: Implement the minimal responsive foundation**

Use semantic HTML, visible labels, keyboard-safe controls, and restrained styling. Do not add resume parsing, API calls, animations, routing, state libraries, or design-system dependencies in this task.

- [ ] **Step 4: Verify GREEN and build**

Run: `cd frontend && pnpm lint && pnpm typecheck && pnpm test --run && pnpm build`

Expected: all commands exit 0 and `dist/` is generated but ignored.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(web): 搭建前端项目骨架"
```

### Task 3: Local Infrastructure and CI

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/pages.yml`
- Modify: `README.md`

**Interfaces:**
- `docker compose up -d redis` starts Redis 7 with a health check and no application containers.
- Backend image runs `uvicorn app.main:app --host 0.0.0.0 --port 9000`.
- CI runs backend and frontend quality commands on pushes and pull requests.
- Pages builds `frontend/` and deploys its `dist/` artifact with repository-aware `VITE_BASE_PATH`.

- [ ] **Step 1: Add configuration assertions before production files**

Create a lightweight validation script or test that checks Compose contains only Redis, the Dockerfile exposes/runs port 9000, and workflow files include backend tests plus frontend lint, typecheck, tests, and build.

- [ ] **Step 2: Run validation and confirm RED**

Expected: missing-file assertions fail.

- [ ] **Step 3: Add the minimal Compose, image, workflows, and README commands**

Pin GitHub Actions to current major versions, use `pnpm install --frozen-lockfile`, and grant Pages only `contents: read`, `pages: write`, and `id-token: write` where needed.

- [ ] **Step 4: Run integration verification**

Run backend checks, frontend checks/build, `docker compose config`, and the configuration assertions.

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml backend/Dockerfile .github README.md
git commit -m "ci: 完善本地基础设施与自动检查"
```
