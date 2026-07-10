# 阶段 3：AI 候选人信息提取实施计划

## 目标与边界

本阶段正式挂载 `POST /api/v1/resumes`：复用阶段 2 的安全 PDF 上传解析，调用 OpenAI 兼容接口提取带原文证据的候选人档案，并在 AI 未配置或预期失败时稳定降级。自动化测试只使用合成 PDF 和 Mock HTTP，不访问真实模型、Redis 或网络。

不在本阶段实现缓存、JD 关键词、匹配评分、完整前端上传流程或生产 CORS；这些能力分别留到阶段 4 至 7。

## 公共契约

- `ParsedPdf` 增加经过扩展名校验的 `filename`，供 `DocumentMetadata` 使用，不写入日志。
- 新增 `DocumentMetadata`、`Education`、`Project`、`CandidateProfile`、`ResumeSnapshot` Pydantic 模型；所有契约字段固定出现，缺失标量为 `null`、数组为 `[]`。
- `POST /api/v1/resumes` 成功返回 `201`；`resume_id` 为 `res_{uuid4}`，`cached=false`，AI 降级时 `degraded=true`。
- 配置增加 `AI_BASE_URL`、`AI_MODEL`、`AI_TIMEOUT_SECONDS=20`；AI 三元组不完整时健康检查返回 503，但上传接口执行规则降级并返回 201。

## AI、证据与降级

- 使用运行时 `httpx.AsyncClient` 请求 `{AI_BASE_URL.rstrip('/')}/chat/completions`，发送 `response_format={"type":"json_object"}`、`temperature=0` 和版本化 Prompt。
- 内部严格 Schema 为每个值携带原文 evidence，并额外返回有证据的就业起止月份；模型不得直接决定工作年限。
- evidence 必须是 `cleaned_text` 精确子串；普通值经 NFKC、空白折叠和大小写归一后必须存在于 evidence。电话按数字、邮箱按大小写不敏感规则复核；无效字段逐项清除，不因单个字段幻觉丢弃其他合法字段。
- 超时、传输错误、408/429/5xx、非 JSON、响应形状或 Schema 错误最多重试一次；其他 4xx 直接降级；未知编程异常继续返回 500。
- AI 最终失败或未配置时，仅按确定性规则提取最早出现的电话和邮箱，其余字段使用缺失值，附加固定缺失警告和 `ai_extraction_fallback`。
- 工作年限仅使用证据可定位的 `YYYY-MM` 区间；倒序或不完整区间丢弃，重叠/相邻月份合并，包含起止月份，按 `Decimal(ROUND_HALF_UP)` 保留一位小数。

## 并行实施

1. Schema/规则：公共和内部 Pydantic 模型、证据过滤、电话邮箱降级、任职区间算法及单元测试。
2. AI 客户端/配置：OpenAI 兼容 HTTP、重试分类、Prompt、配置和健康检查、运行依赖锁及测试。
3. 路由/契约：文件名元数据、公共 `/resumes` 路由、依赖注入、响应组装、隐私日志、API 文档和集成测试。

三路使用隔离工作树，主分支按 Schema/规则 → AI 客户端 → 路由顺序集成。集成后执行实现、API/隐私和交付三路独立终审。

## 验收

- AI 有效响应生成完整 `ResumeSnapshot`；幻觉字段被逐项清除。
- 非 JSON、Schema 错误、超时两次、非重试 4xx 和缺少配置均产生确定的规则降级，不泄露模型响应或凭据。
- PDF 失败不调用 AI；公共路由使用统一错误与 request ID；成功和失败日志均不含文件名、正文、联系方式、证据或模型原始响应。
- Ruff、mypy、后端全量测试与覆盖率、基础设施、生产哈希锁、前端回归和 Compose 全部通过。
