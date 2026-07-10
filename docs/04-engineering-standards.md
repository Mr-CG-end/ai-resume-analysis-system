# 工程开发规范

## 适用范围

本规范约束后端、前端、测试、配置和 Git 协作。项目交付时间只有 24 小时，规范的目标是让错误尽早暴露，而不是建立复杂流程。任何新增抽象、依赖或基础设施都需要直接服务于已确认需求。

## 技术基线

Python 3.12.13 是本地开发、CI 与生产镜像的统一解释器版本。

| 层次 | 基线 |
| --- | --- |
| Python | 3.12.13，开发、CI 与生产镜像使用同一精确版本 |
| 后端 | FastAPI、Pydantic v2、PyMuPDF、redis-py |
| Node.js | 22 LTS |
| 前端 | React、TypeScript strict、Vite、pnpm |
| 后端测试 | pytest、pytest-asyncio、httpx |
| 前端测试 | Vitest、Testing Library，保留一个 Playwright 线上冒烟流程 |
| Python 质量工具 | Ruff、mypy |
| 前端质量工具 | ESLint、Prettier、TypeScript compiler |

依赖必须写入 `backend/pyproject.toml` 或 `frontend/package.json` 并提交锁文件。不得在代码中依赖未声明的本机全局包。

## 单仓库结构

```text
backend/
  app/
    api/routes/          # HTTP 路由和状态码映射
    core/                # 配置、日志、错误和中间件
    schemas/             # API 与 AI 输出模型
    services/            # PDF、AI、匹配和缓存用例
    main.py              # FastAPI 应用装配
  tests/
    unit/
    integration/
    fixtures/
  pyproject.toml
  Dockerfile
frontend/
  src/
    api/                 # HTTP 客户端
    components/          # 无业务状态的通用组件
    features/resume-analysis/
    types/               # 与 API 契约一致的 TypeScript 类型
  tests/
  package.json
  vite.config.ts
docs/
docker-compose.yml       # 仅用于本地 Redis
.github/workflows/
```

路由文件只负责协议适配。PDF 清洗、AI 调用、评分和缓存逻辑必须放入独立服务，使单元测试无需启动 Web 服务即可运行。

## Python 规范

- 公共函数和服务方法必须有参数及返回值类型。
- Pydantic Schema 使用明确字段，不把业务响应退化为 `dict[str, Any]`。
- 对可预期失败使用项目错误类型，由统一异常处理器映射为 API 错误；禁止在路由中散落宽泛的 `except Exception`。
- 文件、PDF 文档对象和网络客户端使用上下文管理器或 `finally` 释放。
- AI Prompt 与输出 Schema 分离；Prompt 需要版本常量，版本变化同步更新缓存版本。
- 评分函数保持纯函数，同一输入必须产生同一总分。
- Ruff 负责格式化和静态检查，mypy 对 `app/` 执行严格类型检查。

建议质量命令：

```bash
cd backend
ruff format --check .
ruff check .
mypy app
pytest
```

## TypeScript 与界面规范

- 开启 `strict`，不得以 `any` 逃避 API 类型建模。
- API 类型集中在 `src/types/`，字段名与 API 契约完全一致。
- 网络请求集中在 `src/api/`；组件不直接拼接后端 URL。
- 业务状态集中在 `features/resume-analysis/`，避免把整页流程写入一个超大组件。
- 按钮在请求期间禁用，重复提交不会产生并发分析。
- 错误信息必须可读且可恢复，不能只输出状态码或控制台错误。
- 颜色不能作为评分和错误状态的唯一提示；表单控件必须关联可见标签。
- 不使用 Local Storage 或 Session Storage 保存 `resume_snapshot`。

建议质量命令：

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## 配置与环境变量

后端配置由 Pydantic Settings 统一读取，生产环境缺少必需配置时在启动阶段失败。建议变量如下：

| 变量 | 必需 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `APP_ENV` | 否 | `development` | `development`、`test` 或 `production` |
| `APP_VERSION` | 否 | `0.1.0` | 健康检查和日志版本 |
| `CORS_ORIGINS` | 是 | 无 | 逗号分隔的允许来源 |
| `MAX_PDF_BYTES` | 否 | `10485760` | 10 MB 文件上限 |
| `MAX_PDF_PAGES` | 否 | `30` | 页数上限 |
| `MAX_RESUME_CHARS` | 否 | `100000` | 清洗文本上限 |
| `AI_BASE_URL` | 是 | 无 | AI API 地址 |
| `AI_API_KEY` | 是 | 无 | AI 密钥 |
| `AI_MODEL` | 是 | 无 | 模型名称 |
| `AI_TIMEOUT_SECONDS` | 否 | `20` | 单次模型调用超时 |
| `REDIS_URL` | 否 | 无 | 缺失时禁用缓存 |
| `CACHE_TTL_SECONDS` | 否 | `86400` | 24 小时 TTL |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |

前端只允许使用 `VITE_API_BASE_URL`。它是公开配置，不是秘密；任何密钥不得使用 `VITE_` 前缀。仓库提交 `.env.example`，忽略 `.env`、`.env.local` 和所有真实凭据。

## API 与错误变更规则

API 实现必须以 `docs/03-api-contract.md` 为基线。新增字段默认设为可选或提供稳定缺失值；字段删除、重命名、类型变化、状态码变化或评分公式变化都属于破坏性变更，需要同步修改需求、API 契约、前端类型和测试。

错误代码使用大写蛇形命名，面向程序保持稳定；中文错误信息可以优化，但不能泄露内部异常、文件路径、供应商响应或密钥。

## 日志与隐私

日志采用一行一个 JSON 对象，最少包含：

```json
{
  "timestamp": "2026-07-10T10:00:00Z",
  "level": "INFO",
  "request_id": "req_xxx",
  "event": "resume_parsed",
  "duration_ms": 1320,
  "page_count": 3,
  "cached": false,
  "degraded": false
}
```

允许记录文件大小、页数、字符数、耗时、状态码、缓存命中和模型名称。禁止记录完整简历、完整 JD、电话、邮箱、地址、AI 密钥、Redis URL 和模型原始响应。

## Git 与评审规范

- 默认分支保持可构建、可测试。
- 使用短生命周期功能分支；单个提交只处理一个可说明的目标。
- 提交信息采用“英文 Conventional Commits 前缀 + 中文主题”，例如 `feat(api): 新增简历上传接口`、`test(match): 覆盖降级评分场景`、`docs: 补充部署规范`。
- 不提交构建产物、虚拟环境、真实 `.env`、PDF 个人简历和缓存文件。
- API 或评分变更必须在同一提交中更新对应文档和测试。
- 合并前检查 diff，确认没有调试日志、密钥、个人数据和无关格式化改动。

## 完成定义

一个功能只有同时满足以下条件才算完成：实现与需求编号一致；成功和失败路径均有测试；后端或前端质量命令通过；API 字段与文档一致；不记录个人信息；README 或相关文档已更新；本地或线上验证路径可重复执行。
