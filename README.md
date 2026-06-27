<div align="left">

# 🛡️ DGA 智能威胁检测平台

**基于多模型融合与多 Agent 协作的企业级 DNS 安全分析平台**

实时检测 DGA（域名生成算法）恶意域名 · DAG 流式编排 · LLM 智能研判 · 数据漂移闭环

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?logo=typescript&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

---

## 📑 目录

- [项目简介](#-项目简介)
- [核心特性](#-核心特性)
- [界面预览](#-界面预览)
- [架构概览](#-架构概览)
- [技术栈](#-技术栈)
- [快速开始](#-快速开始)
- [配置说明](#-配置说明)
- [API 文档](#-api-文档)
- [项目结构](#-项目结构)
- [测试](#-测试)
- [运维手册](#-运维手册)
- [许可证](#-许可证)

---

## 📖 项目简介

**DGA 智能威胁检测平台** 是一套面向企业级 DNS 安全场景的全栈解决方案。它从海量 DNS 查询流量中实时识别由 DGA（Domain Generation Algorithm）生成的恶意域名——这类域名常被僵尸网络与 C2（命令控制）通道用于隐蔽通信。

平台融合 **机器学习推理**、**流式 Pipeline 编排** 与 **LLM 多 Agent 协作**，实现从"检测 → 研判 → 处置 → 反馈"的完整安全闭环，并通过自然语言"问数"与安全知识库降低分析师的使用门槛。

---

## ✨ 核心特性

- **🎯 实时 DGA 检测** — XGBoost（二分类）+ TensorFlow CNN-Attention（家族多分类）多模型融合，对 DNS 查询做毫秒级风险评分，识别 40+ 恶意家族
- **🔀 DAG 编排引擎** — 基于 LangGraph StateGraph 的可视化 YAML Pipeline，支持 stream / batch 双模式，节点可拖拽编排（接入 / 转换 / 推理 / 过滤 / 输出）
- **🤖 A2A 多 Agent 协作** — Triage 分诊、ThreatIntel 情报富化、Explain 解释、Response 处置四类 Agent 经 Redis Pub/Sub 消息总线协同研判
- **🔧 MCP 工具服务** — 通过 Model Context Protocol 为 Agent 提供 ES 查询、模型信息、威胁情报等统一工具接口
- **💬 问数（NL2SQL）** — 自然语言提问自动生成 StarRocks SQL，返回查询结果、图表与 AI 解读
- **📚 安全知识库（RAG）** — 检索增强问答，结合 MITRE ATT&CK 等知识给出带来源引用的安全解答
- **📉 数据漂移监控** — PSI 指标实时检测特征分布偏移，自动产出重训练 / 重设基线的运营建议
- **🏢 多租户支持** — JWT 认证 + RBAC 三角色 + 租户级阈值配置 + 速率限制
- **📊 全链路可观测** — Prometheus 指标 + Grafana 仪表盘 + Jaeger 分布式追踪 + structlog 结构化日志

---

## 📸 界面预览

> 前端基于 React 19 + Ant Design 5，深色主题，ECharts 可视化。

| 实时监控仪表盘 | 域名检测 |
| :---: | :---: |
| ![实时监控仪表盘](docs/screenshots/01-dashboard.png) | ![域名检测](docs/screenshots/02-detection.png) |
| 今日检测量 / 命中率 / QPS 趋势 / 家族分布 / 实时告警流 | 单条/批量域名评分 + 恶意家族识别 + LLM 解释 |

| 告警中心 | 问数 · 自然语言转 SQL |
| :---: | :---: |
| ![告警中心](docs/screenshots/03-alerts.jpg) | ![问数 NL2SQL](docs/screenshots/04-alerts-nl2sql.jpg) |
| 多维筛选 / 严重度·家族·Pipeline 分布 / 按域名聚合 | 自然语言提问 → StarRocks SQL → 结果 + 图表 + AI 解读 |

| 安全知识库 · RAG 问答 | 告警详情 · 多 Agent 研判 |
| :---: | :---: |
| ![知识库 RAG](docs/screenshots/05-knowledge-rag.jpg) | ![告警详情](docs/screenshots/06-alert-detail.jpg) |
| 检索增强问答，结合 MITRE 等知识库给出带来源引用的解答 | Triage → Explain → Response 处置时间线 / 四维分析 / 关联告警 |

| 告警快速详情 | 模型管理 · A/B 灰度 |
| :---: | :---: |
| ![告警详情抽屉](docs/screenshots/07-alert-detail-drawer.jpg) | ![模型管理](docs/screenshots/08-models.jpg) |
| 列表内抽屉式速览：事件 ID / 风险分 / 家族 / 处置时间线 | 多版本 + A/B 灰度 / 性能对比 / 一键上线回滚 |

| Pipeline 管理 | DAG 可视化编排 |
| :---: | :---: |
| ![Pipeline 列表](docs/screenshots/09-pipeline.jpg) | ![DAG 可视化编排](docs/screenshots/10-pipeline-editor.jpg) |
| 多 Pipeline 状态总览 / stream·batch 模式 / 版本管理与回放 | 拖拽式节点编排，YAML 双向同步 |

| 分析报表 | Agent 监控 · A2A |
| :---: | :---: |
| ![分析报表](docs/screenshots/11-reports.jpg) | ![Agent 监控](docs/screenshots/12-agent-monitor.jpg) |
| 30 天趋势 / Top 域名·主机 / 告警热力图 | 多 Agent 调用指标 / 执行历史 / A2A 消息流 |

| 运营建议 · 闭环决策 |
| :---: |
| ![运营建议](docs/screenshots/13-recommendations.jpg) |
| 漂移特征 PSI 排行 + 建议类型分布可视化 / 阈值·漂移·黑白名单建议 / 分析师确认·忽略闭环 |

---

## 🏗️ 架构概览

平台从五个视角呈现完整架构，自上而下逐层细化——**是什么 → 用什么造 → 职责怎么分 → 数据怎么流 → 怎么部署**。

### 总体架构

六大分层全景：外部世界（DNS 流量源 / 分析师）→ 展示层（Web 控制台）→ 接入层（API Gateway）→ 计算层（Scoring / DAG / Agent）→ 数据层（Kafka / ES / StarRocks / Redis / PG）→ 观测层（Prometheus / Grafana / Jaeger）。

![总体架构图](docs/architecture/01-overall-architecture.png)

### 技术架构

L1–L6 分层技术栈全景，体现"分层解耦、异步优先、双协议通信、数据引擎按职责分工"的关键决策。

![技术架构图](docs/architecture/02-tech-stack.png)

### 逻辑架构

七大领域的职责与能力边界：① 展示域 ② 业务编排域 ③ 检测域 ④ Agent 智能分析域 ⑤ 知识与工具域 ⑥ 反馈闭环域 ⑦ 可观测域。

![逻辑架构图](docs/architecture/03-logical-architecture.png)

### 数据流程

一条 DNS 查询的完整数据生命线，贯穿五大数据流：**实时流 / 告警流 / 分析流 / 响应流 / 反馈流**。

![数据流程图](docs/architecture/04-data-flow.png)

### 部署拓扑

基于 Docker Compose 的单机部署：**14 容器 / 4 阶段串联启动**（基础设施 → 后端依赖 → 业务服务 → 用户界面），含健康检查、持久化映射与端口一览。

![部署拓扑图](docs/architecture/05-deployment-topology.png)

<details>
<summary>点击展开：组件级 Mermaid 依赖图</summary>

```mermaid
graph TB
    subgraph 前端["Frontend (React 19)"]
        FE[Dashboard / Detection / Alerts / Models / Pipeline / Reports]
    end
    subgraph 网关["API Gateway (FastAPI)"]
        GW["/api/score · /api/explain · /api/query · /api/rag"]
        MW[JWT 认证 · 速率限制 · CORS · 审计]
    end
    subgraph 计算["计算层"]
        SCORE["Scoring Service<br/>XGBoost + CNN-Attention"]
        DAG["DAG Engine<br/>LangGraph StateGraph"]
        AGENT["Agent Layer<br/>Triage·Explain·Intel·Response"]
    end
    subgraph 存储["Storage Layer"]
        PG[(PostgreSQL)]
        REDIS[(Redis)]
        ES[(Elasticsearch)]
        KAFKA[(Kafka)]
        SR[(StarRocks)]
    end
    subgraph 观测["Observability"]
        PROM[Prometheus] --> GRAF[Grafana]
        JAEGER[Jaeger]
    end
    前端 -->|HTTP| 网关
    网关 --> SCORE
    网关 --> AGENT
    KAFKA --> DAG --> SCORE
    DAG -->|写入| ES
    DAG -->|告警| KAFKA
    DAG -->|分析| SR
    AGENT <-->|A2A| REDIS
    网关 --- PG
    PROM -.采集.-> 网关
```

</details>

### 架构模式

| 模式 | 应用位置 | 价值 |
|------|----------|------|
| **Event-Driven** | Kafka → DAG Engine → Sinks | 适合实时 DNS 流处理 |
| **Layered（分层）** | business：api（HTTP）→ services（业务编排）→ repositories（数据访问） | 关注点分离，单向依赖（测试强制） |
| **Microservices** | Gateway / Scoring / DAG / Agent 独立容器（依赖按服务拆分） | 职责清晰，独立扩展，镜像精简 |
| **CQRS** | ES（查询）+ StarRocks（分析）+ Kafka（写入） | 读写分离，适合告警场景 |
| **Multi-Agent** | Triage → Explain → ThreatIntel → Response | 适合智能分析任务 |

---

## 🛠️ 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| API 网关 | FastAPI + Uvicorn | REST API、WebSocket、中间件 |
| 评分服务 | gRPC + Protobuf | 高性能模型推理通信 |
| ML 模型 | XGBoost / TensorFlow / scikit-learn | 二分类 + 家族多分类 DGA 检测 |
| 告警可解释 | DeepSeek LLM（ExplainAgent） | 自然语言告警解释与研判 |
| DAG 编排 | LangGraph | 有向无环图 Pipeline 编排 |
| Agent / LLM | LangChain + LangGraph / DeepSeek | A2A 多 Agent 协作、告警解释 |
| 前端 | React 19 + TypeScript 5.7 + Vite 6 | SPA 单页应用 |
| UI / 图表 | Ant Design 5 + ECharts 5 | 企业级组件库 + 数据可视化 |
| 状态管理 | Zustand | 轻量级状态管理 |
| 消息队列 | Kafka (KRaft) | DNS 日志流、告警分发 |
| 搜索引擎 | Elasticsearch 8 | 事件存储与全文检索 |
| 缓存 / 总线 | Redis 7 | 评分缓存、Checkpoint、A2A 消息总线 |
| 关系数据库 | PostgreSQL 16 | 用户、租户、模型元数据 |
| OLAP | StarRocks 3 | 大规模分析查询 |
| 可观测 | Prometheus + Grafana + Jaeger + structlog | 指标 / 仪表盘 / 追踪 / 日志 |
| 部署 / 质量 | Docker Compose + Ruff + mypy + pytest | 一键部署 + Lint / 类型 / 测试 |

---

## 🚀 快速开始

### 环境要求

- **Docker** >= 24.0 且 Docker Compose V2
- **Python** >= 3.12（本地开发）
- **Node.js** >= 20（前端开发）
- 内存 >= 12 GB、磁盘 >= 30 GB（完整栈）

### 一键启动

```bash
# 1. 克隆仓库
git clone https://github.com/yyunlei/dga-sentinel.git && cd dga-sentinel

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填入 DEEPSEEK_API_KEY（用于告警解释与问数）

# 3. 一键启动（构建 + 分阶段健康检查 + 数据播种 + 状态报告）
scripts/platform.sh up

# 4. 查看所有服务状态
scripts/platform.sh status
```

> `scripts/platform.sh` 是平台运维脚本，支持 `up / down / restart / status / seed / check / logs`，详见 [运维手册](#-运维手册)。

### 服务访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端控制台 | http://localhost:13001 | React 管理界面 |
| API 网关 | http://localhost:8000 | REST API |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| Grafana | http://localhost:3001 | 监控仪表盘（admin / admin） |
| Jaeger | http://localhost:16686 | 分布式追踪 |
| Prometheus | http://localhost:9090 | 指标查询 |
| Elasticsearch | http://localhost:9200 | 搜索引擎 |

### 开发模式

开发模式降低资源占用，适合本地调试：

```bash
# ES 内存降至 256m，Kafka 日志保留 24h
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 如需 StarRocks（默认关闭以节省资源）
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile full up -d
```

### 本地开发（不使用 Docker）

```bash
# 后端 —— 依赖按服务分组（见 pyproject 的 optional-dependencies），网关只需 base：
pip install -e ".[dev]"                  # business/gateway：base + 开发工具（无 ML/LLM 重依赖）
PYTHONPATH=src uvicorn business.main:app --reload --port 8000

# 跑其它服务时按需安装对应组：
#   pip install -e ".[scoring]"          # scoring：TensorFlow + XGBoost（Intel-Mac 无 TF wheel，建议用 Docker）
#   pip install -e ".[dag]"              # dag：LangGraph
#   pip install -e ".[agents]"           # agents：LangChain 全家桶 + RAG embedding

# 前端
cd frontend && npm install && npm run dev
```

---

## ⚙️ 配置说明

所有配置通过 `.env` 提供（参考 `.env.example`）。关键项：

| 变量 | 说明 | 默认 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek LLM 密钥（告警解释 / 问数必需） | — |
| `JWT_SECRET` | JWT 签名密钥（**生产必须修改**） | `change-me-in-production` |
| `RATE_LIMIT_PER_MINUTE` | 网关速率限制 | `600` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka 地址 | `localhost:9092` |
| `ES_HOSTS` | Elasticsearch 地址 | `http://localhost:9200` |
| `PG_DSN` | PostgreSQL 连接串 | `postgresql://dga:***@localhost:5432/dga_platform` |
| `REDIS_URL` | Redis 地址 | `redis://localhost:6379/0` |
| `STARROCKS_HOST` / `STARROCKS_PORT` | StarRocks 地址 / 端口 | `localhost` / `9030` |
| `MODEL_BINARY_PATH` / `MODEL_MULTI_PATH` | 二分类 / 多分类模型路径 | `artifacts/...` |

---

## 📡 API 文档

完整交互式文档见 `http://localhost:8000/docs`（Swagger UI）。核心接口：

### `POST /api/score` — 域名评分

对一个或多个域名进行 DGA 风险评分（批量最多 1000 条）。

```json
// 请求
{ "domains": ["abc123xyz.com", "google.com"], "tenant_id": "default" }

// 响应
{
  "trace_id": "a1b2c3...",
  "results": [
    { "domain": "abc123xyz.com", "score": 0.92, "is_dga": true,
      "family": "conficker", "family_confidence": 0.85, "model_version": "v2.1.0" }
  ]
}
```

### `POST /api/explain` — 告警解释

对单个域名生成 LLM 自然语言解释（字符特征 / 熵值 / 家族匹配 / 网络行为四维分析）。

```json
{ "domain": "abc123xyz.com", "score": 0.92, "family": "conficker" }
```

### `POST /api/query` — 问数（NL2SQL）

自然语言提问 → 自动生成 StarRocks SQL → 返回数据 + 解读。

```json
{ "question": "统计最近 24 小时的告警总数", "db_type": "starrocks" }
```

### `POST /api/rag/query` — 安全知识库问答

检索增强问答，返回带来源引用的安全解答。

### gRPC 接口

评分服务通过 gRPC 暴露（端口 `50051`）：

```protobuf
service ScoringService {
  rpc Score (ScoreRequest) returns (ScoreResponse);
  rpc HealthCheck (HealthRequest) returns (HealthResponse);
}
```

---

## 📂 项目结构

```text
dga-sentinel/
├── src/                        # 所有 Python 源码（PYTHONPATH=src，pyproject package-dir=src）
│   ├── common/                 # （原 shared/）公共模块
│   │   ├── config.py  constants.py  observability.py  schemas.py
│   │   ├── features/           # （原 scoring_service/features/）特征提取（entropy, lexical, ngram, nxdomain）
│   │   └── utils/              # 通用工具（es_compat.py, time.py）
│   ├── business/               # （原 gateway/）API 网关（FastAPI）
│   │   ├── main.py             # 应用入口
│   │   ├── api/                # （原 routers/）瘦路由，只做 HTTP（score, explain, alerts, models, dag, query, rag, health）
│   │   ├── services/           # 业务编排（detection, alert, realtime, model, pipeline, report, agent_monitor, operations）
│   │   ├── repositories/       # 数据访问（pg_repo, es_repo, starrocks_repo, scoring_client, model_repo, pipeline_repo, operations_repo, agent_client）
│   │   ├── middleware/         # 中间件（auth, rate_limit, tracing, tenant, security）
│   │   └── schemas/            # Pydantic 数据模型
│   ├── ai/                     # AI 模块
│   │   ├── scoring/            # （原 scoring_service/）评分服务
│   │   │   ├── main.py         # 服务入口，HTTP /readyz + /models + /score
│   │   │   ├── grpc_server.py  # gRPC 服务端
│   │   │   ├── models/         # ML 模型（binary, multi, ensemble, registry）
│   │   │   ├── drift.py        # 数据漂移检测（PSI）
│   │   │   └── proto/          # Protobuf 定义与生成代码
│   │   └── agents/             # （原 agent_layer/）LangGraph 多智能体
│   │       ├── __main__.py     # 瘦入口
│   │       ├── orchestrator.py # A2A 消息总线与 Agent 生命周期
│   │       ├── pipeline.py  consumer.py  mcp_app.py  fc_bridge.py  fc_security.py
│   │       ├── agents/         # 4 个 Agent（triage, explain, threat_intel, response）
│   │       ├── a2a/            # A2A 协议与 Redis 消息总线
│   │       └── mcp/            # MCP 工具服务（es_query, model_info, threat_intel）
│   └── dag/                    # （原 dag_engine/）DAG 编排引擎（LangGraph）
│       ├── engine.py           # StateGraph 编排核心
│       ├── loader.py           # YAML Pipeline 加载器
│       ├── runtime.py          # Stream / Batch 运行时
│       ├── checkpoint.py       # Redis 断点续传
│       ├── nodes/              # 节点实现（ingest, transform, infer, filter, sink）
│       └── pipelines/          # YAML Pipeline 配置文件
├── frontend/                   # 前端（React 19 + TypeScript + Ant Design）
│   └── src/
│       ├── pages/              # 页面（Dashboard, Detection, Alerts, Models, Pipeline, Reports, AgentMonitor, Recommendations）
│       ├── components/         # 组件（charts, common, dag-editor）
│       ├── stores/             # Zustand 状态管理
│       ├── services/           # API 调用层
│       ├── hooks/              # 自定义 Hooks
│       └── theme/              # 暗色主题
├── legacy/                     # 旧 Flask 单体（app.py, predict.py, static/, templates/）
├── research/                   # 训练/研究用（statistics/, dga_generate/ ~40 DGA 家族实现）
├── deploy/                     # 部署配置
│   ├── grafana/                # Grafana 仪表盘与数据源
│   ├── prometheus/             # Prometheus 采集配置
│   └── init-scripts/           # 数据库初始化脚本（PostgreSQL, StarRocks）
├── scripts/                    # 运维与工具脚本
│   ├── platform.sh             # 一键启动 & 健康检查 & 数据验证
│   ├── seed_data.py            # 数据播种（PG / ES / Redis）
│   ├── setup_pipelines.py      # Pipeline 初始化
│   └── simulate_traffic.py     # 流量模拟器
├── tests/                      # 单元 / 集成 / 端到端 / Playwright 测试（unit/integration/e2e/playwright）
├── artifacts/                  # 训练好的模型文件
├── docs/                       # 文档（architecture 架构图、screenshots 截图）
├── docker-compose.yml          # 生产编排
├── docker-compose.dev.yml      # 开发覆盖
└── pyproject.toml              # Python 项目配置（package-dir = src，pythonpath = ["src"]）
```

---

## 🧪 测试

```bash
# 全部测试
pytest

# 分类运行
pytest tests/unit          # 单元测试
pytest tests/integration   # 集成测试
pytest tests/e2e           # 端到端测试

# 覆盖率
pytest --cov

# 代码质量
ruff check .               # Lint
mypy .                     # 类型检查
```

---

## 🔧 运维手册

平台运维统一通过 `scripts/platform.sh` 编排 14 容器全链路：

| 命令 | 作用 |
|------|------|
| `scripts/platform.sh up` | 构建并分阶段启动全栈（含健康检查 + 数据播种） |
| `scripts/platform.sh down` | 停止并清理所有容器 |
| `scripts/platform.sh restart` | 重启全栈 |
| `scripts/platform.sh status` | 查看所有服务运行状态 |
| `scripts/platform.sh seed` | 初始化 / 播种演示数据 |
| `scripts/platform.sh check` | 健康检查（依赖就绪、端口可达） |
| `scripts/platform.sh logs` | 查看聚合日志 |

**启动顺序**（4 阶段，依赖健康检查串联）：

1. **基础设施** — Kafka / Elasticsearch / Redis / PostgreSQL / Prometheus / Jaeger / StarRocks-FE
2. **后端依赖** — StarRocks-BE / Grafana
3. **业务服务** — Scoring / Gateway / DAG Engine / Agent Layer
4. **用户界面** — Frontend

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

<div align="center">

**DGA 智能威胁检测平台** · 让 DNS 安全分析更智能、更高效

</div>
