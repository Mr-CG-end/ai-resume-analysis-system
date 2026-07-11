# 阶段 4：JD 关键词与匹配评分实施计划

## 目标与边界

本阶段实现 `POST /api/v1/matches`：校验前端回传的 `ResumeSnapshot` 与 20 至 10,000 字符 JD，确定性提取技能/职责关键词，计算技能分和总分，并使用 AI 评估有原文证据的经历相关性。AI 未配置或预期失败时稳定退回职责关键词覆盖率。

不在本阶段实现 Redis 缓存、完整前端交互、跨请求存储、向量检索或模型生成总分。

## 关键词与确定性评分

- JD 先做 NFKC，原始规范化长度超过 10,000 返回 `JD_TOO_LONG`，strip 后少于 20 返回 `JD_TOO_SHORT`，内部换行和空白保留。
- 冻结 v1 中英文技能/职责词典；ASCII 别名使用字母数字边界匹配，CJK 仅使用至少两个汉字的固定短语。alias 合并为 canonical，按 JD 首次命中位置稳定排序。
- 公开 `jd_keywords` 只包含技能 canonical；职责关键词仅用于经历评分。技能和职责均为空返回 `JD_KEYWORDS_NOT_FOUND`。
- `matched_keywords` 只依据 `cleaned_text`，不得相信结构化 profile 中没有原文证据的技能。
- 所有分数使用 `Decimal` 和 `ROUND_HALF_UP`：技能分为技能覆盖率；规则经历分为职责覆盖率，无对应分母时为 0；总分固定为 `0.6 * skill + 0.4 * experience`。

## AI 与响应契约

- 内部 AI Schema 仅返回 0 至 100 的 `experience_relevance` 和最多 5 条、每条最多 500 字符的简历原文 evidence；不得返回总分、summary、method 或 warnings。
- AI 请求沿用 OpenAI 兼容 `/chat/completions`、两次尝试、每次最多 60 秒、`Accept-Encoding: identity`、解压前拒绝压缩响应和 1 MiB body 上限。JD 与简历均作为 JSON 编码的不可信数据。
- evidence 必须是 `cleaned_text` 精确子串，保持顺序并去重。若没有有效 evidence，整次 AI 评分无效并降级。
- 有效 AI 分数和证据时 `method=hybrid`、`degraded=false`；否则 `method=rule_fallback`、`degraded=true`、warning 为 `ai_matching_fallback`。
- summary 由服务端固定模板生成，不使用模型文本，不回显 JD、简历或 PII；阶段 4 固定 `cached=false`。

## API 与错误

- 新增严格 `MatchRequest`、`MatchResponse`、`ScoreBreakdown` 和 `MatchEvidence`；`match_id` 为 canonical `mat_{uuid4}`。
- `ResumeSnapshot` 继续复用阶段 3 严格模型。嵌套快照校验失败返回 `422 INVALID_RESUME_SNAPSHOT`；其他请求校验仍使用统一错误结构。
- 匹配日志仅记录 request ID、耗时、关键词/证据数量、method、model、degraded、cached，不记录 JD、cleaned_text、profile、证据正文、ID 或密钥。

## 并行实施与验收

1. JD/评分：关键词词典、边界匹配、Decimal 评分、规则降级和单元测试。
2. AI 匹配：严格 Schema、OpenAI 兼容客户端、证据过滤、安全响应限制和单元测试。
3. API/契约：公共模型、错误映射、`/matches` 路由、OpenAPI、隐私和集成测试。

集成后运行 Ruff、mypy、后端全量测试与覆盖率、基础设施、前端和 Compose；实现、AI 安全与 API/交付三路终审的 Critical/Important 必须清零。