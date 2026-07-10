# 智能简历分析系统

本仓库用于实现《星使实习生笔试题》中的“AI 赋能的智能简历分析系统”。当前阶段已经完成需求拆解和技术设计，后续开发应以 `docs/` 中的文档为准。

## 文档索引

| 文档 | 用途 |
| --- | --- |
| [需求规格](docs/01-requirements.md) | 明确目标、范围、优先级和验收条件 |
| [系统设计](docs/02-system-design.md) | 说明架构边界、数据流、模块职责和关键决策 |
| [API 契约](docs/03-api-contract.md) | 固定接口、字段、状态码和评分口径 |
| [工程规范](docs/04-engineering-standards.md) | 约束目录、代码质量、配置、日志和 Git 协作 |
| [测试与验收规范](docs/05-testing-and-acceptance.md) | 定义测试分层、关键场景和发布门槛 |
| [部署规范](docs/06-deployment-specification.md) | 约束本地环境、阿里云 FC 和 GitHub Pages 部署 |

## 已确认的实现边界

系统采用两阶段同步流程：后端先解析 PDF 并返回 `resume_snapshot`，前端在内存中保存快照，再连同岗位描述提交评分。该方案不依赖 Serverless 实例内存，Redis 只用于缓存，故障时不影响核心流程。

本地开发不要求把前后端放入 Docker。前端与后端直接运行，Docker Compose 仅启动 Redis；后端发布到阿里云函数计算时使用自定义容器镜像，确保 PyMuPDF 等依赖在开发与生产环境中保持一致。

## 文档状态

- 版本：`0.1.0`
- 状态：需求与设计基线已确认
- 更新日期：2026-07-10
- 原始题目：[星使实习生笔试题](https://www.yuque.com/gorgearyang/kb/fzzqma9k1gngf7gv?singleDoc#)

