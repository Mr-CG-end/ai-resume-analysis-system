# 阶段 2：PDF 上传、校验与解析实施计划

## 目标与边界

本阶段完成可信的 multipart 单文件适配、PDF 三重类型校验、大小与页数限制、PyMuPDF 多页文本提取、保守文本清洗、内容哈希和统一错误映射。所有功能必须能在无 AI、无 Redis、无网络环境下确定性测试。

`POST /api/v1/resumes` 的成功响应按正式契约必须包含真实 `CandidateProfile`。该能力属于阶段 3，因此本阶段只交付可复用上传适配和内部 `ParsedPdf` 结果，不挂载会返回临时或虚假成功响应的公共路由。阶段 3 直接复用本阶段组件组装完整 `ResumeSnapshot`。

不在本阶段实现：AI 调用与规则档案降级、缓存、JD、匹配评分、OCR、密码破解、复杂双栏视觉恢复、前端完整上传交互。

## 验收矩阵

| 能力 | 验收标准 |
| --- | --- |
| 单文件协议 | 缺失、错字段名返回 `FILE_REQUIRED`；重复或额外文件返回 `MULTIPLE_FILES_NOT_ALLOWED` |
| 文件大小 | 10 MB 接受，10 MB + 1 字节返回 `413 PDF_TOO_LARGE`，不进入 PyMuPDF |
| 文件类型 | 扩展名、`application/pdf`、起始 `%PDF-` 任一不符均返回 `415` |
| PDF 结构 | 加密、损坏、31 页、无文本分别映射稳定 `422` 错误；30 页接受 |
| 文本上限 | 清洗结果超过 100,000 字符返回 `422 PDF_TEXT_TOO_LONG`，不得静默截断 |
| 多页提取 | 三页按页序合并；`page_count`、`character_count`、SHA-256 正确 |
| 文本清洗 | 归一 CRLF/NBSP/水平空白；删除跨页高频边界页眉页脚；不重排正文 |
| 资源与隐私 | UploadFile 和 PyMuPDF 文档在所有路径关闭；日志/响应不含正文、文件名、PII 或内部异常 |
| 契约一致性 | 所有预期错误使用统一 JSON，响应头、正文和日志使用同一 request ID |

## 实施步骤

### 1. 依赖、限制与测试资料

- 在运行依赖中加入 `PyMuPDF` 和 `python-multipart`，同步哈希锁、基础设施校验与 Docker 安装验证。
- 配置 `MAX_PDF_BYTES=10485760`、`MAX_PDF_PAGES=30`、`MAX_RESUME_CHARS=100000`。
- 提交不含真实个人信息的 canonical PDF fixtures；大文件和 30/31 页边界在测试中动态生成。

### 2. 领域错误与 PDF 服务

- 定义强类型业务错误，不依赖 FastAPI。
- 校验顺序固定为：大小 → 扩展名 → MIME → 文件头 → 结构 → 加密 → 页数 → 逐页提取 → 清洗后文本有效性与字符上限。
- 使用 `pymupdf.open(stream=..., filetype="pdf")` 上下文管理器；仅映射已知 PyMuPDF 数据错误，不吞掉未知编程错误。
- `clean_pages()` 为纯函数；只删除多页首尾区域的高频重复行和明确页码，不全局改写正文。

### 3. multipart 适配与统一错误

- 使用 `request.form()` 显式检查全部文件 part，不依赖单个 `UploadFile` 参数折叠重复字段。
- 以固定块读取到 `MAX_PDF_BYTES + 1`；`Content-Length` 只用于明显超大总包快速拒绝，不替代精确文件边界。
- 所有 UploadFile 在 `finally` 或表单上下文退出时关闭。
- 为业务错误、请求验证错误和框架 HTTP 错误提供安全统一 JSON；客户端断连继续传播。

### 4. 测试与审查

- 单元测试覆盖校验边界、解析、清洗、哈希、资源关闭和异常短路。
- 测试应用覆盖 multipart 缺失/重复、统一错误、request ID、隐私和客户端断连；正式应用暂不挂载成功路由。
- 运行 Ruff、mypy、pytest+coverage、基础设施校验、前端回归、Compose 和 `linux/amd64` Docker 构建（若本机 daemon 可用）。
- 至少进行实现规范、API 契约和安全三类独立审查；Critical/Important 清零后更新总清单。

## 提交拆分

1. `test(pdf): 添加脱敏夹具与解析失败用例`
2. `feat(pdf): 实现安全校验与文本清洗`
3. `feat(api): 添加上传适配与统一业务错误`
4. `build(api): 锁定 PDF 运行依赖`
5. `docs: 更新 PDF 解析阶段状态`

