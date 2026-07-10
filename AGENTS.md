# Repository Guidelines

## Project Structure & Module Organization

This repository is currently documentation-first. Read `docs/01-requirements.md` through `docs/06-deployment-specification.md` in order before implementing changes. The planned monorepo layout is:

- `backend/app/`: FastAPI routes, schemas, configuration, and services.
- `backend/tests/`: unit, integration, and sanitized PDF fixtures.
- `frontend/src/`: API client, shared components, feature state, and TypeScript types.
- `frontend/tests/`: component and browser tests.
- `docs/`: requirements, architecture, API, engineering, testing, and deployment contracts.

Keep HTTP concerns in route modules and PDF, AI, matching, and cache logic in focused services.

## Build, Test, and Development Commands

After scaffolding, use these standard commands:

```bash
docker compose up -d redis       # optional local cache
cd backend && uvicorn app.main:app --reload --port 8000
cd backend && ruff check . && mypy app && pytest
cd frontend && pnpm dev
cd frontend && pnpm lint && pnpm typecheck && pnpm test --run && pnpm build
```

The frontend and backend run directly on the host; Docker is required locally only for Redis. Production backend images target `linux/amd64` for Alibaba Function Compute.

## Coding Style & Naming Conventions

Use Python 3.11+, typed function signatures, Pydantic v2 models, Ruff formatting, and mypy. Python modules and functions use `snake_case`; classes use `PascalCase`. TypeScript runs in strict mode, uses `camelCase` for values and `PascalCase` for components/types, and is checked by ESLint and Prettier. Do not use `Any` or `any` to bypass API modeling.

Keep API field names identical to `docs/03-api-contract.md`. Update schemas, frontend types, tests, and documentation together when the contract changes.

## Testing Guidelines

Backend tests use pytest, pytest-asyncio, and httpx; frontend tests use Vitest, Testing Library, and one Playwright smoke flow. Name tests by behavior, such as `test_rejects_scan_only_pdf`. Core services and scoring branches target at least 80% coverage. AI responses and Redis failures must be mocked deterministically; never depend on live model wording in automated tests.

## Commit & Pull Request Guidelines

No Git history exists yet. Use an English Conventional Commits prefix followed by a concise Chinese subject: `feat(api): 新增简历上传接口`, `fix(match): 拒绝无法验证的匹配证据`, or `docs: 说明缓存降级策略`. Keep commits focused. Pull requests must reference requirement IDs, describe verification commands, note API changes, and include screenshots for UI changes. Never commit secrets, `.env` files, real resumes, or PII-bearing logs.

## Architecture & Security Notes

Preserve the stateless two-stage flow: the client returns `resume_snapshot` with the job description, while Redis remains optional. Log request IDs and timings, not resume text, contact details, job descriptions, credentials, or raw model responses.
