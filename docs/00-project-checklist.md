# 项目总阶段任务清单

> 最后更新：2026-07-14
>
> 当前分支：`main`
>
> 当前重点：阶段 8 已完成，准备阶段 9 提交材料与最终检查

## 状态说明

- ✅ 已完成：实现、验证和审查均已通过。
- 🔄 进行中：正在实现、修复或等待审查。
- ⬜ 未开始：尚未进入实施。
- ⛔ 阻塞：需要用户输入、外部权限或环境恢复。

## 总阶段

| 阶段 | 状态 | 完成标准 |
| --- | --- | --- |
| 0. 题目解析与需求基线 | ✅ | 需求、设计、API、工程、测试和部署文档完成，并通过独立审查 |
| 1. 项目工程骨架 | ✅ | 后端、前端、Redis、Docker、CI、Pages 骨架通过最终全分支复审，并完成分支交付 |
| 2. PDF 上传、校验与解析 | ✅ | 单 PDF、多页文本提取、清洗、限制和统一错误均有测试 |
| 3. AI 候选人信息提取 | ✅ | 核心字段、扩展字段、Schema 校验、重试和规则降级完成 |
| 4. JD 关键词与匹配评分 | ✅ | 关键词、证据、分项分、总分公式和 AI 降级完成 |
| 5. Redis 缓存与可靠性 | ✅ | 解析/评分缓存、24 小时 TTL、故障旁路和隐私策略完成 |
| 6. 完整前端交互 | ✅ | 使用 Ant Design 6 完成上传、档案、JD、评分和错误恢复流程 |
| 7. 联调与端到端验收 | ✅ | API 契约、浏览器主流程、异常场景和日志隐私验证通过 |
| 8. 线上部署 | ✅ | FastAPI 发布到阿里云 FC，React 发布到 GitHub Pages |
| 9. 提交材料与最终检查 | ⬜ | README、脱敏样例、线上地址、仓库状态和演示流程完整，且用户本地人工验收确认通过 |

## 当前阶段明细：项目工程骨架

- [x] 建立 GitHub 公开仓库并连接 `origin/main`。
- [x] 建立隔离分支 `feat/project-foundation` 和实施计划。
- [x] 完成 FastAPI 配置、健康检查和 `X-Request-ID`。
- [x] 完成 React/Vite/TypeScript 最小可访问骨架。
- [x] 完成 Redis-only Compose 和 FC Dockerfile。
- [x] 完成 CI、基础设施契约测试和 GitHub Pages 工作流。
- [x] 固定 Python 3.12.13 和带哈希的生产依赖锁。
- [x] 完成后端、前端、基础设施 fresh 全量验证，后端生成 pytest-cov 覆盖率报告。
- [x] 修复最终审查提出的集成、安全和可复现性问题。
- [x] 最终全分支复审通过。
- [x] 选择本地快进合并到 `main` 的交付方式并完成合并。

## 最近验证记录

- 代码版本：`738039f`（`feat/project-foundation`）。
- 后端：14 项测试通过，覆盖率 98%；Ruff、mypy 通过。
- 基础设施：24 项测试、配置校验和 Compose 解析通过。
- 前端：lint、typecheck、测试和生产构建通过。
- 独立最终复审：Approved，Critical / Important / Minor 均为 0。
- 分支交付：`feat/project-foundation` 已快进合并到本地 `main`。
- 环境限制：本机验证使用 Python 3.12.3；CI 与生产镜像固定 Python 3.12.13，Docker 镜像实建和托管 CI 仍由后续交付验证。

## 当前阶段明细：PDF 上传、校验与解析

- [x] 完成 PDF 服务、上传协议、安全与依赖三路并行分析。
- [x] 锁定阶段边界：不以空档案伪装阶段 3，不提前改变正式 `/resumes` 成功契约。
- [x] 编写阶段 2 实施计划和验收矩阵。
- [x] 添加 pypdf、multipart 运行依赖与可复现哈希锁，ReportLab 仅保留为开发依赖。
- [x] 完成 7 个脱敏 PDF fixtures、语义再生成门禁和边界数据生成器。
- [x] 完成文件校验、pypdf 严格解析、多页提取、资源限制和保守清洗。
- [x] 完成 multipart 适配、统一错误映射、断连处理和资源释放。
- [x] 完成后端、基础设施、前端、Compose、哈希锁及 Linux wheel 回归验证。
- [x] 完成 PDF 核心、API 契约和供应链三路独立终审，Critical / Important / Minor 均为 0。

## 阶段 2 验证记录

- 功能基线：`cc25620`（`codex/pdf-upload-parsing`）。
- 后端：72 项测试通过，覆盖率 98%；Ruff format/check、mypy 通过。
- 基础设施：38 项测试通过，配置校验与 Compose 解析通过；全仓无 PyMuPDF、fitz、AGPL 或 Artifex 残留。
- 依赖：生产哈希锁在空虚拟环境安装和导入通过，CPython 3.12 Linux x86_64 wheel 解析通过；ReportLab 仅为开发依赖。
- 前端：lint、typecheck、Vitest 和生产构建通过。
- 独立终审：PDF 核心、上传/API、供应链交付均为 Approved。
- 环境记录：本机 Python 为 3.12.3，CI/镜像固定 3.12.13；阶段 3 已补做 `linux/amd64` 镜像实建、依赖隔离和容器健康检查。托管 GitHub Actions 尚未触发，须在推送后补验。

## 当前阶段明细：AI 候选人信息提取

- [x] 完成阶段 3 只读设计核对并锁定接口、证据、重试与降级边界。
- [x] 编写阶段 3 实施计划和验收矩阵。
- [x] 完成公共响应与内部证据 Schema，并限制模型响应字段和集合大小。
- [x] 完成逐字段证据过滤、电话邮箱规则降级和有统一证据的工作年限计算。
- [x] 完成 OpenAI 兼容客户端、两次调用预算、1 MiB 响应上限和安全错误分类。
- [x] 完成 AI 配置、健康检查、httpx 生产依赖与可复现哈希锁。
- [x] 正式挂载 `POST /api/v1/resumes`，完成真实档案、降级响应和隐私日志。
- [x] 完成后端、基础设施、前端、生产锁、Compose 和 `linux/amd64` 容器回归。
- [x] 完成领域证据、AI 安全和 API/交付三路独立终审，Critical / Important / Minor 均为 0。

## 阶段 3 验证记录

- 功能基线：`b625978`（`codex/ai-profile-extraction`）。
- 后端：174 项测试通过，覆盖率 97%；Ruff format/check、mypy 通过；全部 AI 测试使用 MockTransport，无真实网络请求。
- API：公开 `POST /api/v1/resumes` 以合成 PDF 验证 `201 ResumeSnapshot`、缺配置降级、AI 失败降级、PDF 失败短路、request ID 和隐私日志。
- 依赖与基础设施：38 项测试、配置校验、Compose 解析通过；生产哈希锁在空环境安装并导入 httpx 0.28.1、pypdf 6.14.2。
- 前端：lint、typecheck、Vitest 和生产构建通过。
- 容器：Docker 29.5.3 实建 `linux/amd64` 镜像；镜像不含 ReportLab/fitz，临时容器 `/api/v1/health` 返回 `ok`。
- 独立终审：领域证据、AI 安全、API/交付均为 Approved。
- 外部待办：托管 GitHub Actions 需推送后触发；真实 AI Key 与个人简历只在后续本地人工验收中由用户配置和测试。

## 当前阶段明细：JD 关键词与匹配评分

- [x] 完成中英文技能与职责关键词的 NFKC 规范化、别名去重和边界匹配。
- [x] 完成技能覆盖率、职责规则分和十进制 0.5 向上取整的 60/40 总分。
- [x] 完成 AI 经历相关性客户端、两次调用预算、原文证据验证和空白证据拒绝。
- [x] 完成 `hybrid` / `rule_fallback` 决策不变量和安全固定 summary。
- [x] 正式挂载 `POST /api/v1/matches`，完成 JD 错误、快照错误、OpenAPI 和隐私日志。
- [x] 完成阶段 4 定向测试、后端全量测试、Ruff 和 mypy 验证。
- [x] 完成阶段 4 最终独立复审并清零 Critical / Important / Minor。

## 阶段 4 验证记录

- 功能基线：`deed219`（`codex/jd-match-scoring`）。
- 后端：221 项测试通过，覆盖率 96%；Ruff format/check、mypy 通过。
- API：真实 `POST /api/v1/matches` 覆盖 AI 成功、缺配置、AI 失败、JD 三类错误、快照校验、OpenAPI、request ID 和隐私日志。
- 安全：纯空白 AI 证据被拒绝；未知编程异常不会伪装成规则降级；响应证据必须能在 `cleaned_text` 精确定位。
- 独立终审：匹配决策、公共路由、证据与错误契约均为 Approved，Critical / Important / Minor 均为 0。

## 当前阶段明细：Redis 缓存与可靠性

- [x] 完成版本化解析/评分键、稳定 SHA-256、严格 JSON Schema 校验和 24 小时 TTL。
- [x] 完成 Redis 禁用模式、0.5 秒超时、连接/读取/解码/坏数据/写入/关闭异常旁路。
- [x] 在 pypdf 解析前查询 PDF 字节缓存，相同 PDF 命中时跳过解析和 AI。
- [x] 完成稳定快照与规范化 JD 的匹配缓存，排除请求级 ID、文件名和 `cached` 状态。
- [x] 命中时重新生成请求级 ID；缓存证据重新定位；正常与降级结果保持原有业务语义。
- [x] 完成缓存命中、坏数据重算、TTL、隐私与故障单元/集成测试。
- [x] 完成后端、基础设施和前端全量自动化回归。
- [x] 完成阶段 5 最终独立复审并清零 Critical / Important / Minor。

## 阶段 5 验证记录

- 集成基线：`7b09237`；最终加固：`7b883ad`（`codex/cache-reliability`）。
- 后端：266 项测试通过，覆盖率 96%；Ruff format/check、mypy 通过。
- 缓存：相同 PDF 第二次请求在 pypdf 前命中；相同业务快照与 JD 第二次评分不调用 AI；命中生成新 ID 并设置 `cached=true`。
- 可靠性：Redis 禁用、超时、拒绝连接、非 UTF-8、坏 JSON、错误类型和写入/关闭失败均安全旁路；日志不记录 URL、键或载荷。
- 基础设施：38 项测试和配置校验通过。
- 前端：lint、typecheck、Vitest（1 项）和生产构建通过。
- 独立终审：功能/契约复审与缓存安全复审均为 Approved，Critical / Important / Minor 均为 0；定向安全复测 95 项通过。

## 当前阶段明细：完整前端交互

- [x] 完成 PDF 上传预检、候选人档案、JD 表单、评分结果与错误恢复交互。
- [x] 完成严格 API 类型和运行时响应守卫、页面 reducer、AbortController 与完整重置。
- [x] 完成桌面及 390px 移动布局、键盘主流程、可见标签与 `aria-live` 状态。

## 阶段 6 验证记录

- 功能基线：`4e5a947`（`codex/frontend-workflow`），已快进合并并推送 `main`。
- 后端：266 项测试通过；Ruff、mypy 通过。基础设施：38 项测试和配置校验通过。
- 前端：ESLint、typecheck、Vitest（45 项）、生产构建与 `antd lint` 通过。
- 浏览器：桌面和 390px 移动布局、PDF 选择、错误恢复与无加载期 Console 异常均已检查。

## 当前阶段明细：联调与端到端验收

- [x] 新增显式 CORS 白名单、预检与成功/4xx/5xx 响应测试。
- [x] 新增 FastAPI 与 Vite 双服务 Playwright smoke。
- [x] 验证真实脱敏 PDF、规则降级、JD 评分、重置和 Console 状态。
- [x] 验证浏览器请求仅发往配置 API，且可读取 `X-Request-ID`。
- [x] 完成全量自动化门禁、隐私复审和最终阶段记录。

## 阶段 7 验证记录

- 后端：278 项测试通过，含 12 项 CORS 配置、成功/4xx/5xx、OPTIONS 和非白名单定向测试；Ruff 与 mypy 通过。
- 基础设施：38 项测试和配置校验通过。
- 前端：ESLint、typecheck、Vitest（45 项）、生产构建与 `antd lint` 通过。
- 浏览器：Playwright smoke 通过真实脱敏三页 PDF、规则降级档案、JD 评分、重置、API 来源、`X-Request-ID` 与 Console 检查。
- 隐私：复审未发现日志记录简历正文、JD、联系方式、密钥或缓存键。

## 当前阶段明细：线上部署

- [x] 构建并验证 `linux/amd64` 后端生产镜像。
- [x] 将 FastAPI 自定义容器发布到阿里云函数计算，监听端口 9000，函数超时 120 秒。
- [x] 生产 AI 保持 `Qwen/Qwen3.5-9B`，关闭扩展思考，并将 `AI_TIMEOUT_SECONDS` 设置为 60 秒。
- [x] GitHub Pages 工作流发布 React 前端，首页、JavaScript 和 CSS 资源公开可访问。
- [x] 完成线上健康检查、复杂跨页简历解析和岗位匹配冒烟。

## 阶段 8 验证记录

- 提交 `45f8c89` 的 GitHub CI 与 Pages 工作流均成功，公开首页和 2 个构建资源均返回 `200`。
- FC `/api/v1/health` 返回 `status=ok`，AI 为 `configured`，Redis 按可选配置保持 `disabled`。
- 经授权的 2 页复杂简历在线解析返回 `201`，耗时 17.66 秒且 `degraded=false`；4 个项目的顺序、日期、角色、描述、技术栈和亮点数量均符合验收要求，不存在跨项目标题串入或描述重复。
- 岗位匹配在线返回 `201`，耗时 5.74 秒，使用 `hybrid` 方法且 `degraded=false`；本次固定 JD 的总分为 98、技能分为 100、经历相关分为 95。
- 真实简历、解析正文、模型原始响应和联系方式均未写入仓库或验收日志。

## 更新规则

每完成一个阶段，必须同时更新本文件的状态、勾选对应明细，并记录实际验证结果。实现完成但尚未审查时保持 `🔄`；只有测试与审查均通过后才能标记为 `✅`。出现阻塞时标记为 `⛔`，并在当前重点中写明解除条件。

## 最终人工验收门禁

- 阶段 1 的骨架核验只证明工程链路可运行，不代表 PDF、AI、匹配或完整前端功能已经实现，也不能替代项目最终验收。
- 阶段 2 至 8 完成并通过自动化测试、联调和复审后，由用户按 [`07-local-manual-acceptance.md`](07-local-manual-acceptance.md) 在本地执行完整功能最终验收。
- 自动化测试、代理验证、代码审查和线上冒烟均不能代替用户确认，也不得由代理代签。
- 任一必做人工验收项失败时，阶段 9 保持 `⬜` 或 `🔄`；修复并复测后仍须由用户重新确认。
- 只有用户明确记录“验收结论：通过”后，才可将阶段 9 标记为 `✅`。本门禁不得提前勾选或以默认同意代替。
