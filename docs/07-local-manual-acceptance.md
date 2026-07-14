# 本地最终人工验收指南

## 目的与门禁

本指南供用户在 Windows、PowerShell 环境中执行本地人工验收。自动化测试、代码审查和代理验证不能替代用户的最终确认；只有用户完成“完整功能最终验收”并明确记录为通过，项目阶段 9 才能完成。

当前仓库已实现 PDF 解析、规则/AI 档案、JD 匹配、缓存旁路和完整前端交互。本节用于阶段 7 本地联调核验；最终签字仍须在阶段 2 至 8 全部完成后由用户执行。

## 一、阶段 7 本地联调核验

### 前置条件

- Windows 10/11 与 PowerShell。
- Python 3.12.13、Node.js 22、pnpm 10。
- Docker Desktop（仅在核验 Redis 时需要）。
- 从项目根目录执行命令。
- 后端 `.env` 中使用测试用 `AI_API_KEY`；不得写入或提交真实密钥。

### 启动服务

如需核验 Redis，在终端 1 执行：

```powershell
docker compose up -d redis
docker compose ps
```

在终端 2 启动后端：

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
# 如已启动 Redis，取消 .env 中 REDIS_URL 的注释。
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

在终端 3 启动前端：

```powershell
Set-Location frontend
pnpm install --frozen-lockfile
Copy-Item .env.example .env.local
pnpm dev
```

### 人工操作与预期结果

1. 打开 `http://127.0.0.1:8000/api/v1/health`。
   - 未启用 Redis 时，响应中的 `status` 为 `ok`、`dependencies.ai` 为 `configured`、`dependencies.redis` 为 `disabled`。
   - 启用 Redis 时，`dependencies.redis` 为 `up`。
   - 若使用空的 `AI_API_KEY`，接口返回 503 和 `status: unavailable`，这是可预期的配置检查结果。
2. 打开终端中 Vite 输出的本地地址（通常为 `http://localhost:5173`）。
   - 上传 `backend/tests/fixtures/resume-valid-3-pages.pdf` 并解析，页面展示候选人档案和规则降级提示。
   - 输入不少于 20 字符的固定 JD，页面展示综合分、分项分、关键词和降级说明。
   - 点击“重新分析”后文件、档案、JD 和结果全部清空。
3. 打开浏览器开发者工具。
   - Console 没有未处理异常，请求仅发往配置的 API 域名。
   - 成功和错误响应均可读取 `X-Request-ID`，日志不包含简历正文、联系方式或 JD。

自动 smoke 可在 `frontend` 目录运行 `pnpm test:e2e`，它会启动本地 FastAPI 与 Vite，并使用脱敏 fixture 和规则降级完成主流程。

完成以上步骤后只能记录“阶段 7 本地联调核验通过”，不得代替项目最终人工验收。

## 二、完整功能最终验收

本节仅在阶段 2 至 8 的实现、自动化测试、联调和部署复审均完成后执行。届时应使用脱敏测试 PDF、固定测试 JD 和专用测试凭据，不使用真实简历或生产密钥。

### 验收前置条件

- 后端与前端质量检查、测试和构建均已通过。
- PDF 上传/解析、AI 信息提取、JD 匹配评分、错误恢复和缓存功能均已实现。
- `backend/tests/fixtures/` 中的验收 PDF 已确认脱敏。
- 后端 `.env` 配置可用的测试 AI 凭据；按验收范围启用或禁用 Redis。
- `VITE_API_BASE_URL=http://localhost:8000/api/v1`，前后端均已按上一节方式启动。
- 浏览器缓存已清理，开发者工具的 Console 与 Network 面板已打开。

### 必做人工操作与预期结果

| 编号 | 人工操作 | 预期结果 |
| --- | --- | --- |
| M-01 | 打开本地前端首页 | 页面和静态资源完整，控制台无未处理异常 |
| M-02 | 上传一份三页脱敏文本型 PDF | 只接受单个 PDF；显示三页解析结果和结构化候选人档案 |
| M-03 | 核对姓名、电话、邮箱、地址及扩展字段 | 值可在原文中定位；缺失字段显示“未提取到”等中性文案或 `null`，不虚构信息 |
| M-04 | 输入固定且不少于 20 字符的 JD 并提交 | 展示关键词、总分、分项分、匹配项、缺失项和原文证据 |
| M-05 | 用文档中的公式手工复算评分 | 分项均为 0 至 100 的整数，总分与公式及 0.5 向上舍入规则一致 |
| M-06 | 重复相同 PDF 与 JD | 业务结果一致；启用 Redis 时可观察到缓存命中，禁用或故障时业务仍可继续 |
| M-07 | 上传伪装、扫描、加密、损坏或超限 PDF | 显示可理解且可恢复的中文错误，不泄露堆栈或内部配置 |
| M-08 | 提交过短 JD、模拟 AI 超时或 Redis 不可用 | 表单阻止无效输入；降级结果有明确提示，Redis 故障不阻断核心流程 |
| M-09 | 点击“重新分析”并仅用键盘重走主流程 | 文件、快照、JD 和评分被清除；主要操作可通过键盘完成 |
| M-10 | 检查 Network、Console 和服务日志 | 请求仅发往配置的 API；无未处理异常；日志不含简历正文、联系方式、JD、密钥或原始模型响应 |

任何必做项失败都表示最终人工验收未通过。修复后应重新执行受影响项目及完整主流程，再由用户重新确认。

## 三、失败记录模板

```text
验收日期：
验收环境（Windows/Python/Node/pnpm/Docker/浏览器版本）：
代码版本（分支与 commit）：
失败编号：
操作步骤：
预期结果：
实际结果：
Console/Network/request_id：
截图或日志位置（不得包含密钥或个人信息）：
是否阻断最终验收：是 / 否
修复版本：
复测结果：通过 / 未通过
```

## 四、用户签字确认

以下内容必须由用户本人在本地完成最终测试后填写；代理或自动化结果不得代签。

```text
验收结论：通过 / 未通过
验收日期：
验收代码版本（commit）：
未通过项（无则填“无”）：
用户确认人：
确认说明：我已在本地完成本指南“完整功能最终验收”的全部必做项，并确认上述结果真实。
```

只有“验收结论”为“通过”、未通过项已清零且用户明确确认后，才允许将 `docs/00-project-checklist.md` 的阶段 9 标记为完成。
