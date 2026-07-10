# 测试与验收规范

## 测试目标

测试需要证明三件事：必选流程可以在线完成；AI 和 Redis 发生异常时系统行为仍然确定；接口字段、评分公式和隐私要求没有因实现细节发生漂移。测试不追求覆盖每个框架分支，而是优先覆盖题目评分点和最可能导致演示失败的路径。

## 测试分层

| 层次 | 关注点 | 外部依赖策略 |
| --- | --- | --- |
| 后端单元测试 | PDF 清洗、字段降级、关键词归一、评分公式、缓存键 | 不启动 FastAPI，不连接网络 |
| 后端集成测试 | 路由、状态码、Schema、异常映射、缓存旁路 | AI 与 Redis 使用可控替身 |
| 前端组件测试 | 文件预检、状态切换、结果展示、错误恢复 | 模拟 API 响应 |
| 契约测试 | JSON 字段和 TypeScript 类型与 API 契约一致 | 使用固定成功和失败样例 |
| 端到端测试 | 上传、查看档案、提交 JD、查看评分 | 本地服务和线上环境各执行一次 |
| 部署冒烟测试 | 健康检查、CORS、公开地址、静态资源路径 | 真实 FC 与 GitHub Pages |

AI 测试不得依赖线上模型的自然语言稳定性。集成测试使用固定 JSON 响应模拟正常、超时、非 JSON 和字段错误；线上只保留少量脱敏样例做人工冒烟验证。

## 测试资料

`backend/tests/fixtures/` 应包含以下脱敏资料：

| 文件 | 用途 |
| --- | --- |
| `resume-valid-3-pages.pdf` | 验证多页顺序和完整档案 |
| `resume-missing-address.pdf` | 验证固定字段和 `null` 语义 |
| `resume-repeated-header.pdf` | 验证重复页眉页脚清洗 |
| `resume-scan-only.pdf` | 验证无可提取文本错误 |
| `resume-encrypted.pdf` | 验证加密 PDF 错误 |
| `resume-corrupted.pdf` | 验证损坏 PDF 错误 |
| `not-a-pdf.pdf` | 验证文件头校验 |

测试资料不得包含真实候选人姓名、电话、邮箱、地址或求职信息。需要展示联系方式时使用 `13800138000` 和 `demo@example.com` 等明确的示例值。

## 后端关键测试矩阵

| 编号 | 场景 | 预期结果 | 对应需求 |
| --- | --- | --- | --- |
| T-PDF-000 | 未上传文件或一次提交多个文件 | 分别返回 `FILE_REQUIRED` 和 `MULTIPLE_FILES_NOT_ALLOWED` | FR-PDF-001 |
| T-PDF-000A | multipart 缺少 boundary、字段超限或语法损坏 | `400 MALFORMED_MULTIPART`，不回显解析器消息 | FR-PDF-001 |
| T-PDF-001 | 上传三页文本 PDF | `201`，页数为 3，文本顺序正确 | FR-PDF-002 |
| T-PDF-002 | 扩展名为 PDF、文件头不是 PDF | `415 UNSUPPORTED_MEDIA_TYPE` | FR-PDF-003 |
| T-PDF-003 | 文件大于 10 MB | `413 PDF_TOO_LARGE`，不调用 AI | FR-PDF-004 |
| T-PDF-004 | PDF 超过 30 页 | `422 PDF_PAGE_LIMIT_EXCEEDED` | FR-PDF-004 |
| T-PDF-005 | 扫描件没有有效文本 | `422 PDF_NO_EXTRACTABLE_TEXT` | FR-PDF-006 |
| T-PDF-006 | 加密或损坏 PDF | 返回对应 `422`，不泄露内部异常 | FR-PDF-006 |
| T-PDF-007 | 清洗后文本超过 100,000 字符 | `422 PDF_TEXT_TOO_LONG`，不静默截断 | FR-PDF-005 |
| T-PDF-008 | 单流、累计内容流或原始文本超过资源预算 | `422 PDF_PROCESSING_LIMIT_EXCEEDED`，不误报业务字符上限 | NFR-PERF-001 |
| T-CLEAN-001 | 多页重复页眉页脚 | 重复内容被清理，主体顺序不变 | FR-PDF-005 |
| T-CLEAN-002 | 两行短页重复正文标题 | 标题保留；仅明确页码可以删除 | FR-PDF-005 |
| T-PROFILE-001 | 简历包含四个核心字段 | 四个字段提取正确 | FR-AI-001 |
| T-PROFILE-002 | 简历不包含地址 | `address=null` 且包含警告 | FR-AI-001/002 |
| T-PROFILE-003 | AI 返回非 JSON | 重试一次后规则降级，接口不崩溃 | FR-API-002 |
| T-PROFILE-004 | AI 生成原文不存在的信息 | Schema 校验或证据检查拒绝该值 | FR-AI-002 |
| T-PROFILE-101 | 简历包含求职意向和期望薪资 | 返回原文值，缺失项保持 `null` | FR-AI-101 |
| T-PROFILE-102 | 任职日期存在重叠区间 | 去重计算工作年限；日期不足时返回 `null` | FR-AI-102 |
| T-PROFILE-103 | 简历包含教育和项目经历 | 返回结构化数组，缺失时为空数组 | FR-AI-103 |
| T-JD-001 | JD 小于 20 字符 | `400 JD_TOO_SHORT` | FR-JD-001 |
| T-JD-002 | JD 含重复和大小写不同技能 | 关键词归一后只保留一项 | FR-JD-002 |
| T-MATCH-001 | 3/4 个技能匹配 | `skill_match=75` | FR-MATCH-001 |
| T-MATCH-002 | 技能分 75、经历分 80 | `overall=77` | FR-MATCH-003 |
| T-MATCH-003 | AI 返回越界分数 | 输出被拒绝或限制到 0 至 100 | FR-MATCH-002 |
| T-MATCH-004 | AI 证据不在简历文本中 | 不返回虚假证据，结果降级或警告 | FR-MATCH-002 |
| T-MATCH-005 | AI 超时两次 | 规则评分成功，`method=rule_fallback` | FR-API-002 |
| T-MATCH-101 | AI 返回经历相关性和证据 | 分数在 0 至 100，证据可以在简历原文中定位 | FR-MATCH-101 |
| T-CACHE-001 | 相同 PDF 第二次上传 | 命中解析缓存，业务结果一致 | FR-CACHE-101 |
| T-CACHE-002 | 相同快照和 JD 第二次评分 | 命中评分缓存，业务结果一致 | FR-CACHE-102 |
| T-CACHE-003 | Redis 连接失败 | 请求成功，`cached=false` 并产生安全警告 | FR-CACHE-103 |
| T-PRIVACY-001 | 检查请求日志 | 不包含正文、电话、邮箱、地址或密钥 | NFR-SEC-002 |
| T-API-001 | 校验成功和失败 fixture | 所有响应字段、类型和统一错误结构符合契约 | FR-API-001 |

评分函数需要参数化测试，至少覆盖 0、边界小数、50、99.5 和 100，并固定 Python `round` 可能产生银行家舍入的问题。实现应使用明确的“0.5 向上”规则或 Decimal 量化，使 API 示例中的 76.5 稳定得到 77。

## 前端关键测试矩阵

| 编号 | 场景 | 预期结果 | 对应需求 |
| --- | --- | --- | --- |
| T-UI-001 | 选择非 PDF 文件 | 上传前显示格式错误，不发送请求 | FR-UI-002 |
| T-UI-002 | 选择超过 10 MB 的文件 | 显示大小限制，不发送请求 | FR-UI-002 |
| T-UI-003 | 简历解析中 | 上传与重复提交控件禁用，显示明确状态 | FR-UI-002 |
| T-UI-004 | 核心字段缺失 | 对应位置显示“未识别”，页面不报错 | FR-UI-001 |
| T-UI-005 | 填写有效 JD 并评分 | 展示总分、分项、匹配项、缺失项和证据 | FR-UI-001/FR-UI-101 |
| T-UI-006 | 返回降级结果 | 展示降级提示，不影响查看结果 | FR-UI-101 |
| T-UI-007 | 后端返回统一错误 | 使用中文可操作信息，允许重试或重新上传 | FR-UI-002 |
| T-UI-008 | 点击重新分析 | 清除文件、快照、JD 和评分结果 | FR-UI-001 |
| T-UI-009 | 仅使用键盘操作 | 可以完成文件选择后的主要表单操作 | NFR-UX-001 |
| T-UI-010 | GitHub Pages 子路径部署 | 刷新首页和加载静态资源均正常 | NFR-COMPAT-001 |

## 非功能测试矩阵

| 编号 | 场景 | 预期结果 | 对应需求 |
| --- | --- | --- | --- |
| T-NFR-001 | AI 单次调用超过 20 秒 | 请求取消；只允许一次受控重试 | NFR-PERF-001 |
| T-NFR-002 | 扫描仓库和前端构建产物 | 不包含 AI/Redis 密钥或真实 `.env` | NFR-SEC-001 |
| T-NFR-003 | 成功及异常解析 PDF | 原始上传和临时文件都被释放 | NFR-SEC-003 |
| T-NFR-004 | Redis 超时、拒绝连接或返回坏数据 | 视为缓存未命中，业务继续执行 | NFR-REL-001 |
| T-NFR-005 | 服务端生成错误响应 | 响应、响应头和日志使用同一 `request_id` | NFR-REL-002 |

阶段 3 将正式挂载 `POST /api/v1/resumes`。当前路由基础分支先验收公共 Schema、PDF 原始文件名传递和既有 multipart 适配回归；待档案提取服务接线后，再执行 T-PDF-001 的公共端点 `201` 验收。该成功响应必须同时证明：文件元数据来自本次解析结果、档案字段完整、清洗文本未截断、降级警告语义正确且 `cached=false`。

## API 契约测试

契约测试使用固定 JSON fixture 验证：所有 `CandidateProfile` 字段始终存在；数组不会变成 `null`；模型拒绝额外字段和无效年月；`resume_id` 是带 `res_` 前缀的 UUIDv4；文件页数、字符数和 `cleaned_text` 遵守边界；错误结构包含 `code`、`message` 和 `request_id`；分数是 0 至 100 的整数；`method` 只出现允许值；新增后端字段不会导致前端解析失败。

如果实现生成 OpenAPI 文档，应在 CI 中保存或比较规范快照。任何接口字段变动都必须同步修改 `docs/03-api-contract.md`、Pydantic Schema、TypeScript 类型和契约 fixture。

## 本地验证命令

项目脚手架完成后，完整验证命令固定为：

```bash
cd backend
ruff format --check .
ruff check .
mypy app
pytest --cov=app --cov-report=term-missing
```

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test --run
pnpm build
```

覆盖率用于发现遗漏，不作为替代场景测试的数字目标。后端核心服务和评分函数的分支覆盖率应达到 80%，API 错误映射必须逐项测试。

## 线上验收脚本

公开部署后按固定顺序执行：

1. 打开前端地址，确认无需登录且静态资源完整。
2. 调用后端 `/api/v1/health`，确认服务可用且不泄露配置。
3. 上传三页脱敏 PDF，核对页数、姓名、电话、邮箱和缺失字段。
4. 输入固定 JD，核对关键词、证据和评分公式。
5. 重复相同操作，确认缓存命中或 Redis 旁路行为符合配置。
6. 上传伪装 PDF 和扫描 PDF，确认错误信息可理解。
7. 在浏览器开发者工具中确认请求只发送到配置的 API 域名，控制台无未处理异常。
8. 从干净环境按照 README 运行 `curl` 示例，确认接口字段与文档一致。

## 发布门槛

发布前必须满足：全部 P0 测试通过；后端静态检查、类型检查和测试通过；前端 lint、类型检查、测试和构建通过；公开端到端流程完成；README 中仓库、前端和后端地址可访问；仓库不包含真实密钥和个人简历；日志抽查未发现个人信息。

P1 测试允许在 README 中明确标为未完成，但不能以模拟数据或固定响应伪装为已实现能力。
