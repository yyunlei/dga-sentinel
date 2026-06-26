<!--
  Sync Impact Report
  ==================
  Version change: (new) → 1.0.0
  Modified principles: N/A (initial creation)
  Added sections: Core Principles (7), Security & Compliance, Quality Gates, Observability, Deliverables & Acceptance, Governance
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md — ✅ compatible (Constitution Check section exists)
    - .specify/templates/spec-template.md — ✅ compatible (Success Criteria section exists)
    - .specify/templates/tasks-template.md — ✅ compatible (Phase structure aligns)
  Follow-up TODOs: None
-->

# DGA 智能威胁检测平台 Constitution

## Core Principles

### I. 检测准确性优先 (Detection Accuracy First)

- 二分类模型（XGBoost）准确率 MUST >= 96%，多分类模型（CNN-Attention）准确率 MUST >= 93%
- 模型上线前 MUST 通过 A/B 测试验证，灰度流量 >= 5% 持续 >= 24 小时
- 特征工程变更 MUST 附带对比评估报告（precision/recall/F1 变化量）
- 误报率（FPR）MUST < 1%；漏报率（FNR）MUST < 5%
- 验证方式：查看 `scoring_service/models/registry.py` 中的模型指标记录；Prometheus `model_accuracy` 指标面板

### II. 亚秒级实时响应 (Sub-Second Real-Time Response)

- 单域名评分 API（`/score`）P95 延迟 MUST < 200ms
- DAG Pipeline 端到端处理延迟（Kafka 入 → ES 写入）MUST < 1000ms
- ES 聚合查询（含 `/alerts/grouped`）P95 MUST < 500ms
- Redis 缓存命中时评分延迟 MUST < 50ms
- 验证方式：Prometheus `http_request_duration_seconds` 直方图；Grafana 延迟面板

### III. 微服务解耦 (Microservice Decoupling)

- 每个服务（Gateway / Scoring / DAG Engine / Agent Layer）MUST 独立部署、独立扩容
- 服务间通信 MUST 通过 HTTP/gRPC 或 Kafka，禁止直接数据库共享
- 共享代码 MUST 限于 `shared/` 目录（config、schemas、observability），禁止跨服务 import 业务逻辑
- 新增服务 MUST 提供 `/healthz` 和 `/readyz` 端点
- 验证方式：`docker-compose.yml` 中每个服务独立容器；`shared/` 目录仅含基础设施代码

### IV. 测试先行 (Test-First, NON-NEGOTIABLE)

- 新功能 MUST 先写测试（RED），再实现（GREEN），再重构（REFACTOR）
- 单元测试覆盖率 MUST >= 80%（`pytest --cov`）
- 每个 API 端点 MUST 有对应的集成测试（`tests/integration/`）
- 关键用户流程 MUST 有 E2E 测试（`tests/e2e/` 或 `tests/playwright/`）
- 模型推理路径 MUST 有回归测试（固定输入 → 固定输出断言）
- 验证方式：`pytest --cov=src --cov-report=term-missing`；CI 流水线中覆盖率门禁

### V. 全链路可观测 (Full-Stack Observability)

- 每个服务 MUST 输出结构化日志（structlog JSON 格式），包含 `trace_id`
- 每个 HTTP/gRPC 请求 MUST 携带 OpenTelemetry trace context
- Prometheus 指标 MUST 覆盖：请求延迟、错误率、模型推理耗时、缓存命中率、队列积压
- Grafana 告警规则 MUST >= 5 条，覆盖：服务宕机、延迟飙升、错误率突增、模型漂移、磁盘满
- 验证方式：`deploy/prometheus/alert_rules.yml` 规则数；Jaeger UI 可查看跨服务 trace

### VI. 安全纵深防御 (Defense in Depth)

- 所有非公开 API MUST 通过 JWT 认证（`gateway/middleware/auth.py`）
- 用户输入 MUST 在系统边界验证（Pydantic schema / Zod schema）
- ES 查询 MUST 使用参数化构建（禁止字符串拼接 query DSL）
- 密钥 MUST 通过环境变量注入，禁止硬编码（`.env` 文件不入 git）
- RBAC MUST 区分 analyst（只读）和 write（写操作）权限
- 审计日志 MUST 记录所有写操作（`gateway/middleware/audit.py`）
- 验证方式：`bandit -r gateway/ scoring_service/ agent_layer/`；未认证请求返回 401

### VII. YAGNI 与最小变更 (YAGNI & Minimal Change)

- 新功能 MUST 只改动直接相关的文件，禁止"顺便重构"
- 设计决策 MUST 记录在 `docs/plans/` 中，包含备选方案和选择理由
- 抽象 MUST 在第三次重复时才引入，禁止预防性抽象
- 每个 PR 的改动文件数 SHOULD <= 5（超过需说明理由）
- 验证方式：PR diff 审查；`docs/plans/` 目录中有对应设计文档

## Security & Compliance

- OWASP Top 10 MUST 作为安全基线，每次发版前检查
- SQL 注入防护：所有数据库查询 MUST 使用参数化查询（SQLAlchemy / ES DSL builder）
- XSS 防护：前端 MUST 使用 React 默认转义，禁止 `dangerouslySetInnerHTML`
- CSRF 防护：状态变更请求 MUST 验证 JWT token
- 限流：所有公开端点 MUST 配置速率限制（Redis 令牌桶）
- 密钥轮换：发现密钥泄露 MUST 在 1 小时内完成轮换
- 依赖扫描：`pip audit` 和 `npm audit` MUST 在 CI 中运行，CRITICAL 漏洞阻断发布
- 验证方式：`bandit` 静态扫描零 HIGH/CRITICAL；`npm audit` 零 CRITICAL

## Quality Gates

### CI 流水线门禁

| 门禁 | 工具 | 阈值 | 阻断级别 |
|------|------|------|----------|
| Python 代码格式 | black + isort | 零 diff | 阻断 |
| Python 静态分析 | ruff | 零 error | 阻断 |
| Python 类型检查 | mypy (strict) | 零 error | 警告 |
| Python 安全扫描 | bandit | 零 HIGH | 阻断 |
| Python 测试覆盖 | pytest --cov | >= 80% | 阻断 |
| TypeScript 编译 | tsc --noEmit | 零 error | 阻断 |
| 前端构建 | vite build | 成功 | 阻断 |
| 依赖漏洞 | pip audit + npm audit | 零 CRITICAL | 阻断 |

### 代码审查标准

- 每个 PR MUST 至少 1 人审查
- CRITICAL/HIGH 安全问题 MUST 在合并前修复
- 新增 API 端点 MUST 附带 Pydantic response_model
- 前端组件 MUST 使用 TypeScript strict mode

## Observability

### 指标（Metrics）

- 业务指标：检测总量、DGA 命中率、告警数、确认率
- 性能指标：API 延迟（P50/P95/P99）、模型推理耗时、缓存命中率
- 基础设施：CPU/内存使用率、Kafka 消费延迟、ES 索引大小、Redis 内存

### 日志（Logging）

- 格式：structlog JSON，字段包含 `timestamp`、`level`、`trace_id`、`service`、`message`
- 级别：生产环境 INFO，调试时 DEBUG
- 敏感数据：日志中禁止出现密钥、密码、完整 IP（脱敏为 `10.0.0.x`）

### 追踪（Tracing）

- 协议：OpenTelemetry（W3C Trace Context）
- 采样率：生产环境 10%，调试时 100%
- 后端：Jaeger 1.54+
- 跨服务调用 MUST 传播 trace context

### 告警（Alerting）

- 渠道：Grafana → 企业微信/邮件
- 响应 SLA：CRITICAL 15 分钟内响应，HIGH 1 小时内响应
- 告警规则 MUST 覆盖：服务不可用、延迟 > 2x 基线、错误率 > 5%、模型漂移 PSI > 0.2、磁盘 > 85%

## Deliverables & Acceptance

### 交付物清单

| 交付物 | 位置 | 验收标准 |
|--------|------|----------|
| 需求设计文档 | `docs/plans/YYYY-MM-DD-<topic>-design.md` | 包含背景、设计决策、API 设计、验证方案 |
| API 端点 | `gateway/routers/` | Pydantic response_model、JWT 认证、集成测试通过 |
| 前端页面 | `frontend/src/pages/` | TypeScript strict、Ant Design 组件、响应式布局 |
| 单元测试 | `tests/unit/` | 覆盖率 >= 80%、全部通过 |
| 集成测试 | `tests/integration/` | 每个 API 端点至少 1 个测试 |
| Docker 配置 | `docker-compose.yml` | `docker compose up` 所有服务健康 |
| 可观测性 | `deploy/prometheus/` + `deploy/grafana/` | 指标可查、告警规则生效 |

### 验收流程

1. 代码审查通过（CI 门禁全绿）
2. 功能验证：按设计文档中的验证方案逐项确认
3. 性能验证：关键 API P95 延迟在阈值内
4. 安全验证：`bandit` + `npm audit` 零 CRITICAL
5. 可观测性验证：Grafana 面板可查看新功能指标
6. 文档验证：设计文档已提交到 `docs/plans/`

## Governance

- 本宪法是 DGA 智能威胁检测平台的最高规范，所有开发活动 MUST 遵守
- 修订流程：提出修订 → 记录变更理由 → 更新版本号 → 提交到 `.specify/memory/constitution.md`
- 版本策略：MAJOR（原则删除/重定义）、MINOR（新增原则/章节）、PATCH（措辞/格式修正）
- 合规审查：每次 PR 审查 MUST 验证是否符合宪法原则
- 豁免机制：违反宪法原则 MUST 在 PR 中明确标注理由，并在 `docs/plans/` 中记录
- 运行时开发指导参见 `docs/design.md` 和 `docs/requirements.md`

**Version**: 1.0.0 | **Ratified**: 2026-02-19 | **Last Amended**: 2026-02-19
