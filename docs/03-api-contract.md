# REST API 契约

## 契约原则

API 基础路径为 `/api/v1`，请求和响应使用 UTF-8。除文件上传外，所有请求体使用 `application/json`；所有成功响应和错误响应都必须符合本文件定义。新增可选字段可以保持向后兼容，删除字段、修改类型或改变评分含义需要升级 API 版本。

每个请求通过响应头 `X-Request-ID` 返回追踪标识。客户端可以主动发送同名请求头；缺失时由服务端生成。日志与错误响应必须使用同一标识。

## 公共类型

### `DocumentMetadata`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `filename` | string | 是 | 原始文件名，仅用于界面展示 |
| `page_count` | integer | 是 | 1 至 30 |
| `character_count` | integer | 是 | 清洗后文本字符数 |

### `CandidateProfile`

| 字段 | 类型 | 必填 | 缺失值 |
| --- | --- | --- | --- |
| `name` | string 或 null | 是 | `null` |
| `phone` | string 或 null | 是 | `null` |
| `email` | string 或 null | 是 | `null` |
| `address` | string 或 null | 是 | `null` |
| `job_intention` | string 或 null | 是 | `null` |
| `expected_salary` | string 或 null | 是 | `null` |
| `years_of_experience` | number 或 null | 是 | `null` |
| `education` | `Education[]` | 是 | `[]` |
| `projects` | `Project[]` | 是 | `[]` |

核心字段和加分字段都固定出现在响应中，便于前端使用稳定类型。字段未在简历中出现时必须返回缺失值，不能省略，也不能补造。

### `Education`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `school` | string 或 null | 学校名称 |
| `degree` | string 或 null | 学位或学历原文 |
| `major` | string 或 null | 专业 |
| `start_date` | string 或 null | `YYYY-MM`，无法确认时为 `null` |
| `end_date` | string 或 null | `YYYY-MM`、`present` 或 `null` |

### `Project`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string 或 null | 项目名称 |
| `role` | string 或 null | 候选人在项目中的角色 |
| `description` | string 或 null | 原文压缩后的职责说明 |
| `technologies` | string[] | 项目中明确出现的技术 |

### `ResumeSnapshot`

```json
{
  "resume_id": "res_550e8400-e29b-41d4-a716-446655440000",
  "document": {
    "filename": "resume.pdf",
    "page_count": 3,
    "character_count": 4260
  },
  "cleaned_text": "清洗后的简历文本",
  "profile": {
    "name": "张三",
    "phone": "13800138000",
    "email": "demo@example.com",
    "address": null,
    "job_intention": "Python 后端开发",
    "expected_salary": "15k-20k",
    "years_of_experience": 2.5,
    "education": [],
    "projects": []
  },
  "warnings": ["address_not_found"],
  "degraded": false,
  "cached": false
}
```

`cleaned_text` 最大为 100,000 字符。`resume_id` 用于前端关联，不表示服务端已经持久化该快照。

## 创建简历分析

### `POST /api/v1/resumes`

请求类型为 `multipart/form-data`，字段名固定为 `file`，且只能出现一个文件。前端校验只用于改善体验，服务端必须重复执行全部校验。

成功时返回 `201 Created`，响应体为 `ResumeSnapshot`。示例：

```json
{
  "resume_id": "res_550e8400-e29b-41d4-a716-446655440000",
  "document": {
    "filename": "resume.pdf",
    "page_count": 3,
    "character_count": 4260
  },
  "cleaned_text": "张三 Python 后端工程师……",
  "profile": {
    "name": "张三",
    "phone": "13800138000",
    "email": "demo@example.com",
    "address": null,
    "job_intention": "Python 后端开发",
    "expected_salary": null,
    "years_of_experience": 2.5,
    "education": [],
    "projects": []
  },
  "warnings": ["address_not_found", "expected_salary_not_found"],
  "degraded": false,
  "cached": false
}
```

| 状态码 | 错误代码 | 场景 |
| --- | --- | --- |
| `400` | `FILE_REQUIRED` | 未提供文件 |
| `400` | `MULTIPLE_FILES_NOT_ALLOWED` | 同时提交多份文件 |
| `413` | `PDF_TOO_LARGE` | 文件大于 10 MB |
| `415` | `UNSUPPORTED_MEDIA_TYPE` | 扩展名、MIME 或文件头不是有效 PDF |
| `422` | `PDF_PAGE_LIMIT_EXCEEDED` | PDF 超过 30 页 |
| `422` | `PDF_ENCRYPTED` | PDF 已加密且不能解析 |
| `422` | `PDF_CORRUPTED` | PDF 结构损坏 |
| `422` | `PDF_NO_EXTRACTABLE_TEXT` | 扫描件或没有有效文本 |

AI 故障但规则降级成功时仍返回 `201`，并设置 `degraded=true`。只有 PDF 解析等不可降级的核心步骤失败时才返回错误。

## 创建岗位匹配结果

### `POST /api/v1/matches`

请求体：

```json
{
  "resume_snapshot": {
    "resume_id": "res_550e8400-e29b-41d4-a716-446655440000",
    "document": {
      "filename": "resume.pdf",
      "page_count": 3,
      "character_count": 4260
    },
    "cleaned_text": "张三 Python 后端工程师……",
    "profile": {
      "name": "张三",
      "phone": "13800138000",
      "email": "demo@example.com",
      "address": null,
      "job_intention": "Python 后端开发",
      "expected_salary": null,
      "years_of_experience": 2.5,
      "education": [],
      "projects": []
    },
    "warnings": ["address_not_found"],
    "degraded": false,
    "cached": false
  },
  "job_description": "招聘 Python 后端实习生，需要 RESTful API 与 Redis 项目经验。"
}
```

成功时返回 `201 Created`：

```json
{
  "match_id": "mat_550e8400-e29b-41d4-a716-446655440001",
  "resume_id": "res_550e8400-e29b-41d4-a716-446655440000",
  "jd_keywords": ["Python", "RESTful API", "Redis", "Serverless"],
  "matched_keywords": ["Python", "RESTful API", "Redis"],
  "missing_keywords": ["Serverless"],
  "scores": {
    "skill_match": 75,
    "experience_relevance": 80,
    "overall": 77
  },
  "evidence": [
    {
      "dimension": "experience",
      "text": "负责简历解析与匹配服务"
    }
  ],
  "summary": "技能覆盖较好，项目经历与岗位职责相关。",
  "method": "hybrid",
  "warnings": [],
  "degraded": false,
  "cached": false
}
```

`method` 只能为 `hybrid` 或 `rule_fallback`。证据 `text` 必须能在 `resume_snapshot.cleaned_text` 中找到；无法验证的模型证据不能返回。

评分精度统一为整数：

```text
skill_match = decimal_round_half_up(matched_skill_count / jd_skill_count × 100)
overall = decimal_round_half_up(0.6 × skill_match + 0.4 × experience_relevance)
```

`decimal_round_half_up` 表示十进制 0.5 向上取整，不使用 Python 内置 `round` 的银行家舍入规则。

| 状态码 | 错误代码 | 场景 |
| --- | --- | --- |
| `400` | `JD_TOO_SHORT` | 去除空白后少于 20 字符 |
| `400` | `JD_TOO_LONG` | 超过 10,000 字符 |
| `422` | `INVALID_RESUME_SNAPSHOT` | 快照缺字段、类型错误或文本超限 |
| `422` | `JD_KEYWORDS_NOT_FOUND` | 无法从 JD 提取可用于评分的关键词 |

AI 失败且规则评分可用时返回成功响应，并设置 `method=rule_fallback`、`degraded=true`。

## 健康检查

### `GET /api/v1/health`

健康检查不发起付费 AI 请求，只检查配置是否存在；Redis 可以执行短超时 `PING`。成功响应：

```json
{
  "status": "ok",
  "version": "0.1.0",
  "dependencies": {
    "ai": "configured",
    "redis": "up"
  }
}
```

Redis 禁用或不可用时，整体状态为 `degraded`，HTTP 状态仍为 `200`，因为缓存不是核心依赖。AI 未配置时返回 `503`，状态为 `unavailable`。

## 统一错误结构

```json
{
  "error": {
    "code": "PDF_NO_EXTRACTABLE_TEXT",
    "message": "PDF 中未检测到可解析文本，请上传文本型 PDF。",
    "request_id": "req_550e8400-e29b-41d4-a716-446655440002",
    "details": {}
  }
}
```

`message` 面向最终使用者，不包含堆栈、供应商响应或内部路径。`details` 只提供安全且可操作的约束信息，例如 `max_bytes` 和 `actual_bytes`。

## 警告代码

| 代码 | 含义 |
| --- | --- |
| `name_not_found` | 未找到姓名 |
| `phone_not_found` | 未找到电话 |
| `email_not_found` | 未找到邮箱 |
| `address_not_found` | 未找到地址 |
| `job_intention_not_found` | 未找到求职意向 |
| `expected_salary_not_found` | 未找到期望薪资 |
| `years_of_experience_uncertain` | 无法可靠计算工作年限 |
| `ai_extraction_fallback` | 档案提取已使用规则降级 |
| `ai_matching_fallback` | 经历评分已使用规则降级 |
| `cache_unavailable` | Redis 不可用，已跳过缓存 |

警告用于说明部分结果或基础设施状态，不替代 HTTP 错误。前端应展示降级类警告，普通缺失字段可以在对应字段附近显示“未识别”。
